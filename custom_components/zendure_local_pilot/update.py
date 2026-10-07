"""Mise à jour du script de régulation du Shelly.

Le script est embarqué dans l'intégration : une mise à jour par HACS apporte
donc aussi le nouveau script. Cette entité le signale dans Paramètres → Mises à
jour, et l'installe d'un clic (ou toute seule, si la mise à jour automatique
est activée dans les options).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CoordinateurZendure
from .entity import EntiteShelly
from .shelly import ErreurShelly

URL_RELEASES = "https://github.com/zarzak12/zendure-local-pilot/releases"

# entity_id : update.zendure_solarflow4000mix_script_shelly
CLE = "script_shelly"


async def async_setup_entry(
    hass: HomeAssistant,
    entree: ConfigEntry,
    ajouter: AddEntitiesCallback,
) -> None:
    coordinateur: CoordinateurZendure = hass.data[DOMAIN][entree.entry_id]
    ajouter([MiseAJourScript(coordinateur)])


class MiseAJourScript(EntiteShelly, UpdateEntity):
    """Version du script sur le Shelly face à celle embarquée."""

    _attr_name = "Script de régulation"
    _attr_title = "Script de régulation du Shelly"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_release_url = URL_RELEASES

    def __init__(self, coordinateur: CoordinateurZendure) -> None:
        super().__init__(coordinateur, CLE, domaine="update")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.id_script is not None

    @property
    def installed_version(self) -> str | None:
        # Un script antérieur à 1.2.0 ne publiait pas sa version : on l'affiche
        # comme tel, ce qui le signale bien comme à mettre à jour.
        return self.coordinator.version_shelly or "antérieure à 1.2.0"

    @property
    def latest_version(self) -> str | None:
        return self.coordinator.version_embarquee

    @property
    def in_progress(self) -> bool:
        return self.coordinator.deploiement_en_cours

    @property
    def release_summary(self) -> str | None:
        return ("Pousse sur le Shelly le script embarqué dans l'intégration, vérifié "
                "par relecture. Tes réglages sont conservés. La régulation est "
                "interrompue quelques secondes pendant l'écriture.")

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        try:
            await self.coordinator.async_deployer_script()
        except ErreurShelly as err:
            raise HomeAssistantError(f"Mise à jour du script impossible : {err}") from err
