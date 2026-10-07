"""Boutons d'action sur le script de régulation du Shelly."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CoordinateurZendure
from .entity import EntiteShelly
from .shelly import ErreurShelly


@dataclass(frozen=True, kw_only=True)
class DescriptionBouton(ButtonEntityDescription):
    action: Callable[[CoordinateurZendure], Awaitable[None]]


BOUTONS: tuple[DescriptionBouton, ...] = (
    DescriptionBouton(
        key="relancer_script",
        name="Relancer le script",
        icon="mdi:restart",
        entity_category=EntityCategory.CONFIG,
        action=lambda c: c.async_relancer_script(),
    ),
    DescriptionBouton(
        # Le même dépôt vérifié que la mise à jour : utile si le code du
        # Shelly a été abîmé (collage tronqué dans l'éditeur web, par exemple).
        key="redeployer_script",
        name="Redéployer le script",
        icon="mdi:upload",
        entity_category=EntityCategory.CONFIG,
        action=lambda c: c.async_deployer_script(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entree: ConfigEntry,
    ajouter: AddEntitiesCallback,
) -> None:
    coordinateur: CoordinateurZendure = hass.data[DOMAIN][entree.entry_id]
    ajouter(BoutonScript(coordinateur, d) for d in BOUTONS)


class BoutonScript(EntiteShelly, ButtonEntity):
    entity_description: DescriptionBouton

    def __init__(self, coordinateur: CoordinateurZendure,
                 description: DescriptionBouton) -> None:
        super().__init__(coordinateur, description.key, domaine="button")
        self.entity_description = description

    @property
    def available(self) -> bool:
        return (super().available and self.coordinator.id_script is not None
                and not self.coordinator.deploiement_en_cours)

    async def async_press(self) -> None:
        try:
            await self.entity_description.action(self.coordinator)
        except ErreurShelly as err:
            raise HomeAssistantError(f"{self.entity_description.name} : {err}") from err
