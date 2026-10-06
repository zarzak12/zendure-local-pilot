"""Intégration Zendure Local Pilot.

Pilotage 100 % local d'une batterie Zendure SolarFlow. La régulation
autoconsommation ne vit PAS ici : elle tourne dans le script du Shelly
Pro 3EM, et continue si Home Assistant s'arrête. Cette intégration sert au
réglage, à la supervision et au repli de sécurité.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_MIGRER, DOMAIN
from .coordinator import CoordinateurZendure
from .migration import liberer_anciennes_entites, verifier_migration
from .services import enregistrer_services, retirer_services

_LOGGER = logging.getLogger(__name__)

PLATEFORMES: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Met en place une installation."""
    # La libération doit précéder la création des entités, sinon les
    # identifiants d'origine sont déjà pris et les nôtres prendraient un
    # suffixe « _2 ».
    if entry.options.get(CONF_MIGRER, entry.data.get(CONF_MIGRER, False)):
        await liberer_anciennes_entites(hass)

    coordinateur = CoordinateurZendure(hass, entry)
    await coordinateur.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinateur
    enregistrer_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATEFORMES)

    entry.async_on_unload(entry.add_update_listener(_recharger))

    # Après coup seulement : c'est la création des entités qui révèle si un
    # package YAML encore chargé nous a soufflé les identifiants.
    verifier_migration(hass, entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge une installation."""
    decharge = await hass.config_entries.async_unload_platforms(entry, PLATEFORMES)
    if decharge:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        retirer_services(hass)
    return decharge


async def _recharger(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
