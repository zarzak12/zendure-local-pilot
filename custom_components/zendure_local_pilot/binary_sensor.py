"""États binaires : veille, régulation en marche, erreur, liaisons, zéro soutirage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, VC_EN_VEILLE
from .coordinator import CoordinateurZendure, Donnees
from .entity import EntiteShelly, EntiteZendure


@dataclass(frozen=True, kw_only=True)
class DescriptionBinaire(BinarySensorEntityDescription):
    valeur: Callable[[Donnees], bool | None]
    shelly: bool = False
    attributs: Callable[[Donnees], dict[str, Any]] | None = None


def _en_veille(d: Donnees) -> bool | None:
    valeur = d.vc(VC_EN_VEILLE)
    return bool(valeur) if valeur is not None else None


def _defaut(d: Donnees) -> bool | None:
    """Erreur signalée par la batterie : is_error seul, comme la version YAML.

    faultLevel n'est PAS un indicateur de défaut : une batterie saine, que
    l'application Zendure affiche sans aucun problème, renvoie faultLevel 1
    (constaté sur une SolarFlow 4000 MIX PRO). Sa signification n'est pas
    documentée ; il est exposé en attribut pour le diagnostic.
    """
    try:
        return int(d.proprietes["is_error"]) == 1
    except (KeyError, TypeError, ValueError):
        return None


def _reseau_connecte(d: Donnees) -> bool | None:
    try:
        return int(d.proprietes["gridState"]) == 1
    except (KeyError, TypeError, ValueError):
        return None


BINAIRES: tuple[DescriptionBinaire, ...] = (
    DescriptionBinaire(
        key="script_shelly",
        name="Script Shelly",
        device_class=BinarySensorDeviceClass.RUNNING,
        valeur=lambda d: d.script_actif,
        shelly=True,
    ),
    DescriptionBinaire(
        # Le Shelly signale ici un plantage, une erreur de syntaxe, un manque
        # de mémoire… Le message exact est en attribut de « script état ».
        key="script_erreur",
        name="Script en erreur",
        device_class=BinarySensorDeviceClass.PROBLEM,
        valeur=lambda d: bool(d.script.get("errors")) if d.script is not None else None,
        shelly=True,
    ),
    DescriptionBinaire(
        key="en_veille",
        name="En veille",
        icon="mdi:power-sleep",
        valeur=_en_veille,
        shelly=True,
    ),
    DescriptionBinaire(
        key="batterie_joignable",
        name="Liaison batterie",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        valeur=lambda d: d.batterie_joignable,
        shelly=True,
    ),
    DescriptionBinaire(
        # « erreur » et non « défaut » : c'est l'identifiant de la version YAML,
        # dont l'historique est ainsi conservé à la migration.
        key="erreur",
        name="Erreur",
        device_class=BinarySensorDeviceClass.PROBLEM,
        valeur=_defaut,
        attributs=lambda d: {"is_error": d.proprietes.get("is_error"),
                             "fault_level": d.proprietes.get("faultLevel")},
    ),
    DescriptionBinaire(
        key="reseau_connecte",
        name="Réseau connecté",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        valeur=_reseau_connecte,
    ),
    DescriptionBinaire(
        key="zero_soutirage",
        name="Zéro soutirage",
        icon="mdi:transmission-tower-off",
        valeur=lambda d: (d.reseau <= 0) if d.reseau is not None else None,
        shelly=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entree: ConfigEntry,
    ajouter: AddEntitiesCallback,
) -> None:
    coordinateur: CoordinateurZendure = hass.data[DOMAIN][entree.entry_id]
    ajouter(
        BinaireShelly(coordinateur, d) if d.shelly
        else BinaireBatterie(coordinateur, d)
        for d in BINAIRES
    )


class _LectureBinaire:
    """Lecture commune. Placée après EntiteZendure dans les bases, afin que
    l'initialisation (entity_id imposé) reste celle du socle commun."""

    entity_description: DescriptionBinaire

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.valeur(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        lire = self.entity_description.attributs
        if lire is None or self.coordinator.data is None:
            return None
        return lire(self.coordinator.data)


class BinaireBatterie(EntiteZendure, _LectureBinaire, BinarySensorEntity):
    """État issu de la batterie : disparaît si elle ne répond plus."""

    def __init__(self, coordinateur: CoordinateurZendure,
                 description: DescriptionBinaire) -> None:
        super().__init__(coordinateur, description.key, "binary_sensor")
        self.entity_description = description


class BinaireShelly(EntiteShelly, _LectureBinaire, BinarySensorEntity):
    """État issu du Shelly : reste lisible batterie muette.

    « Liaison batterie » en particulier n'aurait aucun intérêt s'il devenait
    indisponible au moment précis où la liaison tombe.
    """

    def __init__(self, coordinateur: CoordinateurZendure,
                 description: DescriptionBinaire) -> None:
        super().__init__(coordinateur, description.key, "binary_sensor")
        self.entity_description = description
