"""Sondage périodique de la batterie et du Shelly."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_EM_CANAL, CONF_SHELLY_HOST, DOMAIN, INTERVALLE_SONDAGE, PREFIXE
from .memoire import NB_PACKS_MAX, Memoire
from .shelly import ClientShelly, ErreurShelly
from .zendure import ClientZendure, ErreurZendure

_LOGGER = logging.getLogger(__name__)

# Script du Shelly arrêté depuis ce délai : batterie remise à 0 W.
DELAI_REPLI_S = 30


@dataclass
class Donnees:
    """Instantané de l'installation."""

    rapport: dict[str, Any] | None = None
    erreur_batterie: str | None = None
    shelly: dict[str, Any] = field(default_factory=dict)
    kvs: dict[str, Any] = field(default_factory=dict)
    script: dict[str, Any] | None = None
    memoire: Memoire | None = None

    @property
    def proprietes(self) -> dict[str, Any]:
        return (self.rapport or {}).get("properties") or {}

    @property
    def packs(self) -> list[dict[str, Any]]:
        return (self.rapport or {}).get("packData") or []

    @property
    def sn(self) -> str:
        return (self.rapport or {}).get("sn") or ""

    @property
    def produit(self) -> str:
        return (self.rapport or {}).get("product") or ""

    @property
    def batterie_joignable(self) -> bool:
        return self.rapport is not None

    @property
    def script_actif(self) -> bool:
        return bool((self.script or {}).get("running"))

    def vc(self, composant: str) -> Any:
        """Valeur d'un composant virtuel du Shelly, p. ex. « number:200 »."""
        bloc = self.shelly.get(composant)
        if isinstance(bloc, dict):
            return bloc.get("value")
        return None

    @property
    def canal_em(self) -> int:
        """Pince du Shelly suivie par la régulation, d'après son propre réglage."""
        try:
            return min(2, max(0, int(self.kvs.get("zendure_em", 0))))
        except (TypeError, ValueError):
            return 0

    @property
    def reseau(self) -> float | None:
        """Puissance au point de livraison, en watts. Positif = soutirage.

        Lue sur la pince que la régulation suit réellement : en afficher une
        autre donnerait un tableau de bord cohérent en apparence et faux en
        pratique.
        """
        bloc = self.shelly.get(f"em1:{self.canal_em}")
        if not isinstance(bloc, dict):
            return None
        valeur = bloc.get("act_power")
        try:
            return round(float(valeur), 1)
        except (TypeError, ValueError):
            return None


class CoordinateurZendure(DataUpdateCoordinator[Donnees]):
    """Interroge le Shelly puis la batterie, à chaque cycle."""

    def __init__(self, hass: HomeAssistant, entree) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=INTERVALLE_SONDAGE),
        )
        session = async_get_clientsession(hass)
        self.entree = entree
        # L'adresse modifiée dans les options prime sur celle de l'installation.
        self.shelly = ClientShelly(
            session, entree.options.get(CONF_SHELLY_HOST, entree.data[CONF_SHELLY_HOST]))
        self.zendure = ClientZendure(session, "")
        self._id_script: int | None = None
        self.memoire = Memoire()
        self._store: Store = Store(hass, 1, f"{DOMAIN}.{entree.entry_id}")
        self._script_arrete_depuis: float | None = None
        self._repli_fait = False

    async def _repli_si_script_arrete(self, donnees: Donnees, maintenant: float) -> None:
        """Remet la batterie à 0 W si le script du Shelly est arrêté depuis 30 s.

        La batterie n'a aucun chien de garde : script arrêté (plantage, mise à
        jour du firmware, « Run on startup » oublié), elle garde sa dernière
        consigne indéfiniment, 3000 W de décharge injectés compris. C'est le
        filet de l'automatisation de la version YAML. Il ne couvre pas le
        script vivant mais muet : celui-là, le script le couvre lui-même.
        """
        if donnees.script is None:
            # État du script inconnu (Shelly qui n'a pas répondu à cet appel) :
            # ne rien conclure, comme le capteur YAML devenu indisponible.
            return
        if donnees.script_actif:
            self._script_arrete_depuis = None
            self._repli_fait = False
            return
        if self._script_arrete_depuis is None:
            self._script_arrete_depuis = maintenant
        if self._repli_fait or maintenant - self._script_arrete_depuis < DELAI_REPLI_S:
            return
        if not donnees.batterie_joignable or not donnees.sn:
            return   # réessayé au relevé suivant
        p = donnees.proprietes
        if not p.get("outputLimit") and not p.get("inputLimit"):
            self._repli_fait = True   # déjà au repos : rien à corriger
            return
        try:
            await self.zendure.ecrire(
                donnees.sn, {"smartMode": 1, "outputLimit": 0, "inputLimit": 0})
        except ErreurZendure as err:
            _LOGGER.warning("script du Shelly arrêté : remise à 0 W impossible (%s)", err)
            return
        self._repli_fait = True
        _LOGGER.warning(
            "script de régulation du Shelly arrêté depuis %d s : batterie remise à 0 W",
            DELAI_REPLI_S)

    # -- mémoire (compteurs, statistiques, santé) ----------------------------

    async def async_charger_memoire(self) -> None:
        """Recharge la mémoire ; à la première installation, reprend le YAML."""
        self.memoire = Memoire.depuis_dict(await self._store.async_load())
        if not self.memoire.amorcee:
            reprises = self.memoire.amorcer(await _anciennes_valeurs(self.hass))
            if reprises:
                _LOGGER.info("valeurs reprises de la version YAML : %s", ", ".join(reprises))
            await self._store.async_save(self.memoire.en_dict())

    async def async_sauver_memoire(self) -> None:
        await self._store.async_save(self.memoire.en_dict())

    def reinitialiser_sante(self) -> None:
        self.memoire.reinitialiser_sante()
        self._store.async_delay_save(self.memoire.en_dict, 1)
        self.async_update_listeners()

    @property
    def id_script(self) -> int | None:
        """Identifiant du script de régulation sur le Shelly, s'il est connu."""
        return self._id_script

    @property
    def canal_em(self) -> int:
        """Pince du Shelly à lire. Le réglage du Shelly fait foi.

        Il est aussi mémorisé dans l'entrée de configuration, mais c'est le
        script qui régule : afficher une autre pince que celle qu'il suit
        donnerait un tableau de bord cohérent en apparence et faux en réalité.
        """
        if self.data and "zendure_em" in self.data.kvs:
            return self.data.canal_em
        valeur = self.entree.options.get(
            CONF_EM_CANAL, self.entree.data.get(CONF_EM_CANAL, 0))
        try:
            return min(2, max(0, int(valeur)))
        except (TypeError, ValueError):
            return 0

    async def _async_update_data(self) -> Donnees:
        donnees = Donnees()

        # 1. Le Shelly d'abord : c'est lui qui sait où est la batterie.
        try:
            donnees.shelly = await self.shelly.etat_complet() or {}
            donnees.kvs = await self.shelly.kvs_lire_tout()
        except ErreurShelly as err:
            # Sans le Shelly, il n'y a plus ni régulation ni découverte :
            # inutile de prétendre que le reste est à jour.
            raise UpdateFailed(f"Shelly injoignable : {err}") from err

        try:
            if self._id_script is None:
                script = await self.shelly.trouver_script()
                self._id_script = script.get("id") if script else None
            if self._id_script is not None:
                donnees.script = await self.shelly.appel(
                    "Script.GetStatus", {"id": self._id_script})
        except ErreurShelly as err:
            _LOGGER.debug("état du script indisponible : %s", err)

        # 2. La batterie, dont l'adresse est publiée par le script.
        ip = str(donnees.kvs.get("zendure_ip") or "").strip()
        if ip:
            self.zendure.hote = ip
        if self.zendure.hote:
            try:
                donnees.rapport = await self.zendure.rapport()
            except ErreurZendure as err:
                # Une batterie momentanément muette ne doit pas faire
                # disparaître les entités du Shelly : on dégrade par partie.
                donnees.erreur_batterie = str(err)
                _LOGGER.debug("batterie injoignable : %s", err)
        else:
            donnees.erreur_batterie = "adresse de la batterie pas encore découverte"

        await self._repli_si_script_arrete(donnees, dt_util.now().timestamp())

        self.memoire.mettre_a_jour(donnees, dt_util.now())
        donnees.memoire = self.memoire
        # Sauvegarde différée : écrire sur disque toutes les 5 s userait la
        # carte SD pour rien. Au pire, une coupure perd une minute de cumul.
        self._store.async_delay_save(self.memoire.en_dict, 60)
        return donnees

    async def ecrire_batterie(self, proprietes: dict[str, Any]) -> None:
        """Écrit des propriétés sur la batterie, numéro de série compris."""
        if not self.data or not self.data.sn:
            raise ErreurZendure("numéro de série inconnu : écriture refusée")
        await self.zendure.ecrire(self.data.sn, proprietes)
        await self.async_request_refresh()

    async def ecrire_batterie_persistant(self, proprietes: dict[str, Any]) -> None:
        """Écrit un réglage qui doit survivre à une coupure.

        La batterie n'enregistre en mémoire flash que lorsque smartMode vaut 0.
        On l'y place, on écrit, puis on rétablit smartMode à 1 : sans ce
        rétablissement, la batterie cesserait d'accepter les consignes rapides
        de la régulation. À réserver aux réglages rares (bornes SOC, plafonds) :
        la flash a un nombre de cycles d'écriture limité.
        """
        await self.ecrire_batterie({"smartMode": 0, **proprietes})
        await asyncio.sleep(2)
        await self.ecrire_batterie({"smartMode": 1})

    async def ecrire_composant_virtuel(self, composant: str, valeur: Any) -> None:
        await self.shelly.vc_ecrire(composant, valeur)
        await self.async_request_refresh()

    async def ecrire_kvs(self, cle: str, valeur: Any) -> None:
        await self.shelly.kvs_ecrire(cle, valeur)
        await self.async_request_refresh()


# Dernières valeurs de la version YAML, par grandeur de la mémoire.
def _sources_yaml() -> dict[str, str]:
    sources = {
        "energie_chargee": f"sensor.{PREFIXE}_energie_chargee",
        "energie_dechargee": f"sensor.{PREFIXE}_energie_dechargee",
        "energie_pv": f"sensor.{PREFIXE}_energie_pv",
        "rendement_charge": f"sensor.{PREFIXE}_rendement_charge",
        "rendement_decharge": f"sensor.{PREFIXE}_rendement_decharge",
        "derniere_calibration": f"sensor.{PREFIXE}_derniere_calibration",
    }
    for n in range(1, NB_PACKS_MAX + 1):
        sources[f"pack_{n}_energie_dc"] = f"sensor.{PREFIXE}_pack_{n}_energie_dc"
        sources[f"pack_{n}_capacite"] = f"input_number.{PREFIXE}_pack_{n}_capacite_estimee"
        sources[f"pack_{n}_ancre_soc"] = f"input_number.{PREFIXE}_pack_{n}_soh_ancre_soc"
        sources[f"pack_{n}_ancre_energie"] = f"input_number.{PREFIXE}_pack_{n}_soh_ancre_energie"
    return sources


async def _anciennes_valeurs(hass: HomeAssistant) -> dict[str, Any]:
    """État courant si les packages sont encore chargés, sinon l'enregistreur."""
    valeurs: dict[str, Any] = {}
    manquantes: dict[str, str] = {}
    for cle, entite in _sources_yaml().items():
        etat = hass.states.get(entite)
        if etat and etat.state not in ("unknown", "unavailable", ""):
            valeurs[cle] = etat.state
        else:
            manquantes[cle] = entite
    if not manquantes or "recorder" not in hass.config.components:
        return valeurs
    try:
        from homeassistant.components.recorder import get_instance, history

        for cle, entite in manquantes.items():
            derniers = await get_instance(hass).async_add_executor_job(
                history.get_last_state_changes, hass, 1, entite)
            for etat in derniers.get(entite, []):
                if etat.state not in ("unknown", "unavailable", ""):
                    valeurs[cle] = etat.state
    except Exception as err:  # noqa: BLE001
        # La reprise est un confort : son échec ne doit pas bloquer l'installation.
        _LOGGER.warning("reprise des valeurs YAML impossible : %s", err)
    return valeurs

