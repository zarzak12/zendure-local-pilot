"""Curseurs de réglage : bornes SOC, plafonds, et réglages de la régulation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .calculs import echelle_soc
from .const import (
    DOMAIN,
    KVS_REGLAGES,
    VC_BUFFER,
    VC_BUFFER_CHARGE,
    VC_CHARGE_MAX,
    VC_CONSIGNE_MANUELLE,
    VC_DECHARGE_MAX,
    VC_DELAI_VEILLE,
)
from .coordinator import CoordinateurZendure, Donnees
from .entity import EntiteZendure

W = UnitOfPower.WATT


@dataclass(frozen=True, kw_only=True)
class DescriptionNombre(NumberEntityDescription):
    """Un curseur, et la façon de le lire puis de l'écrire."""

    valeur: Callable[[Donnees], float | None]
    ecrire: Callable[[CoordinateurZendure, float], Any]
    # Pas de bornes déduites de inverseMaxPower / chargeMaxLimit : sur certains
    # firmwares, ces champs suivent la consigne en cours au lieu d'un plafond
    # fixe (voir le script). Les bornes sont celles des composants du Shelly.
    shelly: bool = False


def _i(source: dict[str, Any], cle: str, defaut: int = 0) -> int:
    try:
        return int(source.get(cle, defaut) or defaut)
    except (TypeError, ValueError):
        return defaut


# ---------------------------------------------------------------------------
# Bornes SOC — écriture persistante, car ce réglage doit survivre à une coupure
# ---------------------------------------------------------------------------
async def _ecrire_soc_min(coord: CoordinateurZendure, valeur: float) -> None:
    ech = echelle_soc(coord.data.proprietes)
    await coord.ecrire_batterie_persistant({"minSoc": int(valeur) * ech})


async def _ecrire_soc_max(coord: CoordinateurZendure, valeur: float) -> None:
    ech = echelle_soc(coord.data.proprietes)
    await coord.ecrire_batterie_persistant({"socSet": int(valeur) * ech})


def _soc(cle: str) -> Callable[[Donnees], float | None]:
    def lire(d: Donnees) -> float | None:
        if cle not in d.proprietes:
            return None
        return round(_i(d.proprietes, cle) / echelle_soc(d.proprietes))
    return lire


def _plafond(cle: str) -> Callable[[CoordinateurZendure, float], Any]:
    async def ecrire(coord: CoordinateurZendure, valeur: float) -> None:
        await coord.ecrire_batterie_persistant({cle: int(valeur)})
    return ecrire


NOMBRES_BATTERIE: tuple[DescriptionNombre, ...] = (
    DescriptionNombre(
        key="soc_min_consigne",
        name="SOC minimum",
        icon="mdi:battery-low",
        native_min_value=0,
        native_max_value=50,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        mode=NumberMode.SLIDER,
        valeur=_soc("minSoc"),
        ecrire=_ecrire_soc_min,
    ),
    DescriptionNombre(
        key="soc_max_consigne",
        name="SOC maximum",
        icon="mdi:battery-high",
        native_min_value=70,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        mode=NumberMode.SLIDER,
        valeur=_soc("socSet"),
        ecrire=_ecrire_soc_max,
    ),
    DescriptionNombre(
        key="plafond_decharge_consigne",
        name="Plafond de décharge",
        icon="mdi:transmission-tower-export",
        native_min_value=0,
        native_max_value=4000,
        native_step=100,
        native_unit_of_measurement=W,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        valeur=lambda d: _i(d.proprietes, "inverseMaxPower") or None,
        ecrire=_plafond("inverseMaxPower"),
    ),
    DescriptionNombre(
        key="plafond_charge_consigne",
        name="Plafond de charge",
        icon="mdi:transmission-tower-import",
        native_min_value=0,
        native_max_value=4000,
        native_step=100,
        native_unit_of_measurement=W,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        valeur=lambda d: _i(d.proprietes, "chargeMaxLimit") or None,
        ecrire=_plafond("chargeMaxLimit"),
    ),
)


def _vc(composant: str) -> Callable[[CoordinateurZendure, float], Any]:
    async def ecrire(coord: CoordinateurZendure, valeur: float) -> None:
        await coord.ecrire_composant_virtuel(composant, valeur)
    return ecrire


def _lire_vc(composant: str) -> Callable[[Donnees], float | None]:
    def lire(d: Donnees) -> float | None:
        valeur = d.vc(composant)
        try:
            return float(valeur)
        except (TypeError, ValueError):
            return None
    return lire


NOMBRES_SHELLY: tuple[DescriptionNombre, ...] = (
    DescriptionNombre(
        key="decharge_max",
        name="Décharge maximale",
        icon="mdi:battery-arrow-down",
        native_min_value=0,
        native_max_value=4000,
        native_step=50,
        native_unit_of_measurement=W,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.SLIDER,
        valeur=_lire_vc(VC_DECHARGE_MAX),
        ecrire=_vc(VC_DECHARGE_MAX),
        shelly=True,
    ),
    DescriptionNombre(
        key="charge_max",
        name="Charge maximale",
        icon="mdi:battery-arrow-up",
        native_min_value=0,
        native_max_value=4000,
        native_step=50,
        native_unit_of_measurement=W,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.SLIDER,
        valeur=_lire_vc(VC_CHARGE_MAX),
        ecrire=_vc(VC_CHARGE_MAX),
        shelly=True,
    ),
    DescriptionNombre(
        key="consigne_manuelle",
        name="Consigne manuelle",
        icon="mdi:tune-variant",
        native_min_value=-4000,
        native_max_value=4000,
        native_step=50,
        native_unit_of_measurement=W,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.BOX,
        valeur=_lire_vc(VC_CONSIGNE_MANUELLE),
        ecrire=_vc(VC_CONSIGNE_MANUELLE),
        shelly=True,
    ),
    DescriptionNombre(
        key="buffer",
        name="Marge de décharge",
        icon="mdi:arrow-expand-vertical",
        # Négatif = injection résiduelle tolérée, comme dans le script.
        native_min_value=-200,
        native_max_value=200,
        native_step=5,
        native_unit_of_measurement=W,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.SLIDER,
        valeur=_lire_vc(VC_BUFFER),
        ecrire=_vc(VC_BUFFER),
        shelly=True,
    ),
    DescriptionNombre(
        key="buffer_charge",
        name="Marge de charge",
        icon="mdi:arrow-collapse-vertical",
        native_min_value=-200,
        native_max_value=200,
        native_step=5,
        native_unit_of_measurement=W,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.SLIDER,
        valeur=_lire_vc(VC_BUFFER_CHARGE),
        ecrire=_vc(VC_BUFFER_CHARGE),
        shelly=True,
    ),
    DescriptionNombre(
        key="delai_veille",
        name="Délai de mise en veille",
        icon="mdi:timer-sand",
        # En MINUTES : le script multiplie la valeur par 60 (0 = jamais).
        native_min_value=0,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        valeur=_lire_vc(VC_DELAI_VEILLE),
        ecrire=_vc(VC_DELAI_VEILLE),
        shelly=True,
    ),
)


# ---------------------------------------------------------------------------
# Réglages fins de la régulation, stockés dans le KVS du Shelly
# ---------------------------------------------------------------------------
LIBELLES_KVS: dict[str, tuple[str, str, str | None]] = {
    "zendure_period": ("Période d'écriture", "mdi:timer-outline", UnitOfTime.MILLISECONDS),
    "zendure_tick": ("Cadence de lecture", "mdi:metronome", UnitOfTime.MILLISECONDS),
    "zendure_gain": ("Gain de régulation", "mdi:chart-bell-curve", None),
    "zendure_dead": ("Zone morte", "mdi:arrow-collapse-horizontal", UnitOfPower.WATT),
    "zendure_hyst": ("Hystérésis", "mdi:sine-wave", UnitOfPower.WATT),
    "zendure_wake": ("Seuil de réveil", "mdi:power-sleep", UnitOfPower.WATT),
    "zendure_flip": ("Délai d'inversion", "mdi:swap-vertical", UnitOfTime.SECONDS),
    "zendure_flipw": ("Seuil d'inversion", "mdi:swap-horizontal-bold", UnitOfPower.WATT),
    "zendure_smooth": ("Lissage", "mdi:chart-bell-curve-cumulative", None),
}


def _lire_kvs(cle: str) -> Callable[[Donnees], float | None]:
    def lire(d: Donnees) -> float | None:
        try:
            return float(d.kvs[cle])
        except (KeyError, TypeError, ValueError):
            return None
    return lire


def _ecrire_kvs(cle: str, pas: float) -> Callable[[CoordinateurZendure, float], Any]:
    async def ecrire(coord: CoordinateurZendure, valeur: float) -> None:
        # Le KVS du Shelly est typé : réécrire un entier en flottant ferait
        # échouer les comparaisons du script, qui est en mJS.
        await coord.ecrire_kvs(cle, valeur if pas < 1 else int(valeur))
    return ecrire


def _nombres_kvs() -> list[DescriptionNombre]:
    descriptions: list[DescriptionNombre] = []
    for cle, (mini, maxi, pas) in KVS_REGLAGES.items():
        if cle not in LIBELLES_KVS:
            continue
        nom, icone, unite = LIBELLES_KVS[cle]
        descriptions.append(DescriptionNombre(
            key=cle.removeprefix("zendure_"),
            name=nom,
            icon=icone,
            native_min_value=mini,
            native_max_value=maxi,
            native_step=pas,
            native_unit_of_measurement=unite,
            mode=NumberMode.BOX,
            # Activés : le tableau de bord les affiche dans l'onglet Réglages.
            # La catégorie CONFIG les tient à l'écart des vues automatiques.
            entity_category=EntityCategory.CONFIG,
            valeur=_lire_kvs(cle),
            ecrire=_ecrire_kvs(cle, pas),
            shelly=True,
        ))
    return descriptions


async def async_setup_entry(
    hass: HomeAssistant,
    entree: ConfigEntry,
    ajouter: AddEntitiesCallback,
) -> None:
    coordinateur: CoordinateurZendure = hass.data[DOMAIN][entree.entry_id]
    descriptions = [*NOMBRES_BATTERIE, *NOMBRES_SHELLY, *_nombres_kvs()]
    ajouter(NombreZendure(coordinateur, d) for d in descriptions)


class NombreZendure(EntiteZendure, NumberEntity):
    """Un curseur rattaché à la batterie."""

    entity_description: DescriptionNombre

    def __init__(self, coordinateur: CoordinateurZendure,
                 description: DescriptionNombre) -> None:
        super().__init__(coordinateur, description.key, domaine="number")
        self.entity_description = description

    @property
    def available(self) -> bool:
        if self.entity_description.shelly:
            # Réglage porté par le Shelly : il reste modifiable même si la
            # batterie ne répond plus, ce qui est justement le moment où l'on
            # veut pouvoir brider la régulation. On court-circuite donc le
            # test « batterie joignable » d'EntiteZendure.
            return CoordinatorEntity.available.fget(self)
        return super().available

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.valeur(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.ecrire(self.coordinator, value)
