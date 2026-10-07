"""Interrupteur de la régulation.

Couper le script, c'est rendre la main à la batterie. Cela mérite un
interrupteur visible plutôt qu'un passage par l'interface du Shelly.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import CoordinateurZendure
from .entity import EntiteShelly

# Préférences d'affichage du tableau de bord (ex-input_boolean de la version
# YAML) : clé, nom, icône, état initial.
AFFICHAGE = (
    ("show_help", "Afficher l'aide", "mdi:help-circle", False),
    ("show_pv", "Afficher le PV", "mdi:solar-power", True),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entree: ConfigEntry,
    ajouter: AddEntitiesCallback,
) -> None:
    coordinateur: CoordinateurZendure = hass.data[DOMAIN][entree.entry_id]
    ajouter([InterrupteurRegulation(coordinateur),
             *(InterrupteurAffichage(coordinateur, *a) for a in AFFICHAGE)])


class InterrupteurAffichage(EntiteShelly, SwitchEntity, RestoreEntity):
    """Préférence d'affichage : ne pilote rien, sert aux cartes conditionnelles."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinateur: CoordinateurZendure, cle: str, nom: str,
                 icone: str, defaut: bool) -> None:
        super().__init__(coordinateur, cle, domaine="switch")
        self._attr_name = nom
        self._attr_icon = icone
        self._attr_is_on = defaut

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (precedent := await self.async_get_last_state()) is not None:
            self._attr_is_on = precedent.state == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()


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
