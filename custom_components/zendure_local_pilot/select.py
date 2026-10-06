"""Listes de choix : mode de régulation, injection PV, secours, pince lue."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODES, VC_MODE
from .coordinator import CoordinateurZendure, Donnees
from .entity import EntiteZendure


@dataclass(frozen=True, kw_only=True)
class DescriptionChoix(SelectEntityDescription):
    """Une liste de choix, et la façon de la lire puis de l'écrire."""

    valeur: Callable[[Donnees], str | None]
    ecrire: Callable[[CoordinateurZendure, str], Any]
    shelly: bool = False


def _i(source: dict[str, Any], cle: str) -> int | None:
    try:
        return int(source[cle])
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Mode de régulation : porté par le Shelly, c'est lui qui régule
# ---------------------------------------------------------------------------
def _lire_mode(d: Donnees) -> str | None:
    valeur = d.vc(VC_MODE)
    return valeur if valeur in MODES else None


async def _ecrire_mode(coord: CoordinateurZendure, option: str) -> None:
    await coord.ecrire_composant_virtuel(VC_MODE, option)


# ---------------------------------------------------------------------------
# Réglages de la batterie, écrits en flash : rares, donc persistants
# ---------------------------------------------------------------------------
def _enum_batterie(cle: str, options: list[str]):
    """Associe une propriété entière de la batterie à une liste de choix."""

    def lire(d: Donnees) -> str | None:
        indice = _i(d.proprietes, cle)
        if indice is None or not 0 <= indice < len(options):
            return None
        return options[indice]

    async def ecrire(coord: CoordinateurZendure, option: str) -> None:
        await coord.ecrire_batterie_persistant({cle: options.index(option)})

    return lire, ecrire


OPTIONS_INJECTION = ["auto", "autorisee", "interdite"]
OPTIONS_SECOURS = ["standard", "economique", "arret"]
OPTIONS_CANAL = ["0", "1", "2"]

_lire_injection, _ecrire_injection = _enum_batterie("gridReverse", OPTIONS_INJECTION)
_lire_secours, _ecrire_secours = _enum_batterie("gridOffMode", OPTIONS_SECOURS)


# ---------------------------------------------------------------------------
# Pince du Shelly réellement lue par la régulation
# ---------------------------------------------------------------------------
def _lire_canal(d: Donnees) -> str | None:
    valeur = d.kvs.get("zendure_em")
    try:
        return str(int(valeur))
    except (TypeError, ValueError):
        return None


async def _ecrire_canal(coord: CoordinateurZendure, option: str) -> None:
    await coord.ecrire_kvs("zendure_em", int(option))


CHOIX: tuple[DescriptionChoix, ...] = (
    DescriptionChoix(
        key="mode",
        translation_key="mode",
        icon="mdi:state-machine",
        options=MODES,
        valeur=_lire_mode,
        ecrire=_ecrire_mode,
        shelly=True,
    ),
    DescriptionChoix(
        key="injection_pv_consigne",
        translation_key="injection_pv",
        icon="mdi:solar-power-variant",
        options=OPTIONS_INJECTION,
        entity_category=EntityCategory.CONFIG,
        valeur=_lire_injection,
        ecrire=_ecrire_injection,
    ),
    DescriptionChoix(
        key="mode_secours_consigne",
        translation_key="mode_secours",
        icon="mdi:power-plug-off",
        options=OPTIONS_SECOURS,
        entity_category=EntityCategory.CONFIG,
        valeur=_lire_secours,
        ecrire=_ecrire_secours,
    ),
    DescriptionChoix(
        key="canal_em",
        translation_key="canal_em",
        icon="mdi:numeric",
        options=OPTIONS_CANAL,
        entity_category=EntityCategory.CONFIG,
        valeur=_lire_canal,
        ecrire=_ecrire_canal,
        shelly=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entree: ConfigEntry,
    ajouter: AddEntitiesCallback,
) -> None:
    coordinateur: CoordinateurZendure = hass.data[DOMAIN][entree.entry_id]
    ajouter(ChoixZendure(coordinateur, d) for d in CHOIX)


class ChoixZendure(EntiteZendure, SelectEntity):
    entity_description: DescriptionChoix

    def __init__(self, coordinateur: CoordinateurZendure,
                 description: DescriptionChoix) -> None:
        super().__init__(coordinateur, description.key, domaine="select")
        self.entity_description = description
        self._attr_options = list(description.options or [])

    @property
    def available(self) -> bool:
        if self.entity_description.shelly:
            return CoordinatorEntity.available.fget(self)
        return super().available

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.valeur(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        await self.entity_description.ecrire(self.coordinator, option)
