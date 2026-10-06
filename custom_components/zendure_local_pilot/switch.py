"""Interrupteur de la régulation.

Couper le script, c'est rendre la main à la batterie. Cela mérite un
interrupteur visible plutôt qu'un passage par l'interface du Shelly.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CoordinateurZendure
from .entity import EntiteShelly


async def async_setup_entry(
    hass: HomeAssistant,
    entree: ConfigEntry,
    ajouter: AddEntitiesCallback,
) -> None:
    coordinateur: CoordinateurZendure = hass.data[DOMAIN][entree.entry_id]
    ajouter([InterrupteurRegulation(coordinateur)])


class InterrupteurRegulation(EntiteShelly, SwitchEntity):
    """Démarre ou arrête le script de régulation du Shelly."""

    _attr_name = "Régulation"
    _attr_icon = "mdi:robot"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinateur: CoordinateurZendure) -> None:
        super().__init__(coordinateur, "regulation", domaine="switch")

    @property
    def available(self) -> bool:
        # Sans identifiant de script, il n'y a rien à piloter : mieux vaut une
        # entité indisponible qu'un interrupteur qui ne ferait rien.
        return super().available and self.coordinator.id_script is not None

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.script_actif

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.shelly.script_demarrer(self.coordinator.id_script)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.shelly.script_arreter(self.coordinator.id_script)
        # Le script arrêté, la batterie conserverait sa dernière consigne et
        # continuerait d'injecter ou de tirer indéfiniment. On la remet au
        # repos, ce que faisait déjà l'automatisation de repli de la version
        # YAML.
        try:
            await self.coordinator.ecrire_batterie(
                {"smartMode": 1, "outputLimit": 0, "inputLimit": 0})
        except Exception:  # noqa: BLE001
            # La batterie peut être injoignable ; l'arrêt du script, lui, a
            # bien eu lieu et ne doit pas être signalé comme un échec.
            pass
        await self.coordinator.async_request_refresh()
