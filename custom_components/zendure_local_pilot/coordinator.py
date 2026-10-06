"""Sondage périodique de la batterie et du Shelly."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_EM_CANAL, CONF_SHELLY_HOST, DOMAIN, INTERVALLE_SONDAGE
from .shelly import ClientShelly, ErreurShelly
from .zendure import ClientZendure, ErreurZendure

_LOGGER = logging.getLogger(__name__)


@dataclass
class Donnees:
    """Instantané de l'installation."""

    rapport: dict[str, Any] | None = None
    erreur_batterie: str | None = None
    shelly: dict[str, Any] = field(default_factory=dict)
    kvs: dict[str, Any] = field(default_factory=dict)
    script: dict[str, Any] | None = None

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
        self.shelly = ClientShelly(session, entree.data[CONF_SHELLY_HOST])
        self.zendure = ClientZendure(session, "")
        self._id_script: int | None = None

    @property
    def canal_em(self) -> int:
        """Pince du Shelly à lire. Le réglage du Shelly fait foi.

        Il est aussi mémorisé dans l'entrée de configuration, mais c'est le
        script qui régule : afficher une autre pince que celle qu'il suit
        donnerait un tableau de bord cohérent en apparence et faux en réalité.
        """
        valeur = self.data.kvs.get("zendure_em") if self.data else None
        if valeur is None:
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

        return donnees

    async def ecrire_batterie(self, proprietes: dict[str, Any]) -> None:
        """Écrit des propriétés sur la batterie, numéro de série compris."""
        if not self.data or not self.data.sn:
            raise ErreurZendure("numéro de série inconnu : écriture refusée")
        await self.zendure.ecrire(self.data.sn, proprietes)
        await self.async_request_refresh()
