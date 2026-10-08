"""Sondage périodique de la batterie et du Shelly."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EM_CANAL,
    CONF_MAJ_AUTO,
    CONF_SHELLY_HOST,
    DOMAIN,
    INTERVALLE_SONDAGE,
    KVS_VERSION_SCRIPT,
    PREFIXE,
    SCRIPT_EMBARQUE,
)
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
        self._code_embarque: str | None = None
        self.version_embarquee: str | None = None
        self._maj_tentee: str | None = None
        self.deploiement_en_cours = False

    # -- script de régulation embarqué ---------------------------------------

    async def async_charger_script_embarque(self) -> None:
        chemin = os.path.join(os.path.dirname(__file__), SCRIPT_EMBARQUE)

        def lire() -> str:
            with open(chemin, encoding="utf-8") as fichier:
                return fichier.read()

        try:
            self._code_embarque = await self.hass.async_add_executor_job(lire)
        except OSError as err:
            _LOGGER.error("script embarqué illisible (%s) : pas de mise à jour du Shelly", err)
            return
        self.version_embarquee = version_du_script(self._code_embarque)

    @property
    def version_shelly(self) -> str | None:
        """Version du script installé, ou None s'il est antérieur à 1.2.0
        (il ne publiait pas encore sa version)."""
        if not self.data:
            return None
        v = self.data.kvs.get(KVS_VERSION_SCRIPT)
        return str(v) if v else None

    @property
    def script_a_jour(self) -> bool:
        return bool(self.version_embarquee) and self.version_shelly == self.version_embarquee

    async def async_deployer_script(self) -> None:
        """Pousse le script embarqué sur le Shelly, vérifié par relecture.

        Les réglages ne bougent pas : ils vivent dans le KVS et les composants
        virtuels, que le script retrouve au démarrage. Pendant les quelques
        secondes d'écriture, la batterie garde sa consigne ; si le dépôt
        échoue, le script reste arrêté et le repli à 0 W prend le relais.
        """
        if self._code_embarque is None:
            raise ErreurShelly("script embarqué indisponible")
        if self._id_script is None:
            raise ErreurShelly("aucun script de régulation repéré sur le Shelly")
        self.deploiement_en_cours = True
        self.async_update_listeners()
        try:
            await self.shelly.script_deployer(self._id_script, self._code_embarque)
        finally:
            self.deploiement_en_cours = False
        ir.async_delete_issue(self.hass, DOMAIN, "maj_script_echec")
        await self.async_request_refresh()

    async def async_relancer_script(self) -> None:
        """Arrête puis redémarre le script, sans toucher à son code.

        L'interruption ne dure qu'un instant, bien en deçà des 30 s du repli
        à 0 W : la batterie garde sa consigne le temps du redémarrage.
        """
        if self._id_script is None:
            raise ErreurShelly("aucun script de régulation repéré sur le Shelly")
        await self.shelly.script_arreter(self._id_script)
        await self.shelly.script_demarrer(self._id_script)
        await self.async_request_refresh()

    def _planifier_maj_auto(self) -> None:
        """Une tentative par version et par démarrage : en cas d'échec, pas de
        boucle de redéploiement, une alerte de réparation à la place."""
        if not self.entree.options.get(CONF_MAJ_AUTO, True):
            return
        if (not self.version_embarquee or self.script_a_jour or self.deploiement_en_cours
                or self._id_script is None or self._maj_tentee == self.version_embarquee):
            return
        self._maj_tentee = self.version_embarquee
        self.hass.async_create_task(self._maj_auto())

    async def _maj_auto(self) -> None:
        avant = self.version_shelly or "antérieure à 1.2.0"
        _LOGGER.warning("mise à jour du script du Shelly : %s -> %s",
                        avant, self.version_embarquee)
        try:
            await self.async_deployer_script()
        except ErreurShelly as err:
            _LOGGER.error("mise à jour du script du Shelly impossible : %s", err)
            ir.async_create_issue(
                self.hass, DOMAIN, "maj_script_echec",
                is_fixable=False, severity=ir.IssueSeverity.ERROR,
                translation_key="maj_script_echec",
                translation_placeholders={"version": self.version_embarquee or "?",
                                          "erreur": str(err)})

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
            # Script supprimé puis recréé : il a changé d'identifiant. On le
            # recherchera par son nom au relevé suivant.
            self._id_script = None

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

    def async_update_listeners(self) -> None:
        super().async_update_listeners()
        # Après chaque relevé réussi, self.data est à jour : c'est le moment
        # de comparer la version du script à celle embarquée.
        if self.data is not None and self.last_update_success:
            self._planifier_maj_auto()

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


def version_du_script(code: str) -> str | None:
    """Lit « let SCRIPT_VERSION = "x.y.z"; » dans le code du script."""
    m = re.search(r'let\s+SCRIPT_VERSION\s*=\s*"([^"]+)"', code)
    return m.group(1) if m else None


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


ETATS_REMONTES = 50


def derniere_valeur_valide(etats: list[Any]) -> str | None:
    """La plus récente valeur exploitable d'une liste d'états enregistrés."""
    valides = [e for e in etats
               if getattr(e, "state", None) not in (None, "unknown", "unavailable", "")]
    if not valides:
        return None
    # L'ordre renvoyé par l'enregistreur a varié selon les versions : on
    # s'appuie sur l'horodatage quand il est là, sur la position sinon.
    if all(getattr(e, "last_updated", None) is not None for e in valides):
        return max(valides, key=lambda e: e.last_updated).state
    return valides[-1].state


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
            # Plusieurs changements, pas seulement le dernier : pendant la
            # migration, le capteur YAML est souvent enregistré
            # « indisponible » juste avant son retrait. Constaté en réel : le
            # rendement de décharge n'était pas repris pour cette raison.
            derniers = await get_instance(hass).async_add_executor_job(
                history.get_last_state_changes, hass, ETATS_REMONTES, entite)
            v = derniere_valeur_valide(derniers.get(entite, []))
            if v is not None:
                valeurs[cle] = v
    except Exception as err:  # noqa: BLE001
        # La reprise est un confort : son échec ne doit pas bloquer l'installation.
        _LOGGER.warning("reprise des valeurs YAML impossible : %s", err)
    return valeurs

