"""Capteurs issus du rapport de la batterie."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfInformation,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .calculs import (
    capacite_pack,
    capacite_totale,
    echelle_soc,
    efficacite_charge,
    efficacite_decharge,
    nom_modele,
    puissance_batterie_nette,
    puissance_dc_packs,
    pv_vers_batterie,
    pv_vers_maison,
)
from .const import CONF_NB_PACKS, DEFAUT_NB_PACKS, DOMAIN
from .coordinator import CoordinateurZendure, Donnees
from .entity import EntiteZendure
from .memoire import NB_PACKS_MAX, Memoire

MESURE = SensorStateClass.MEASUREMENT


def _i(source: dict[str, Any], cle: str, defaut: int = 0) -> int:
    """Lecture entière tolérante : un champ absent n'est pas une erreur.

    Les modèles n'exposent pas tous les mêmes champs — le SolarFlow 2400 AC
    n'a pas d'entrée photovoltaïque, les propriétés hors-réseau sont réservées
    à certains modèles. Mieux vaut une valeur neutre qu'une entité en erreur.
    """
    try:
        return int(source.get(cle, defaut) or 0)
    except (TypeError, ValueError):
        return defaut


def _dixiemes_kelvin(valeur: int) -> float:
    """Les températures arrivent en dixièmes de kelvin (2931 = 20,0 °C)."""
    return round((valeur - 2731) / 10, 1)


@dataclass(frozen=True, kw_only=True)
class DescriptionCapteur(SensorEntityDescription):
    """Description enrichie d'une fonction de lecture."""

    valeur: Callable[[Donnees], Any]
    present: Callable[[Donnees], bool] = lambda d: True
    # Mesure issue du Shelly : reste disponible si la batterie ne répond plus.
    shelly: bool = False
    attributs: Callable[[Donnees], dict[str, Any]] | None = None


def _direct(suffixe: str, nom: str, propriete: str, **kwargs) -> DescriptionCapteur:
    return DescriptionCapteur(
        key=suffixe,
        name=nom,
        valeur=lambda d, p=propriete: _i(d.proprietes, p),
        **kwargs,
    )


_W = {"native_unit_of_measurement": UnitOfPower.WATT,
      "device_class": SensorDeviceClass.POWER, "state_class": MESURE}


def _memo(suffixe: str, nom: str, lire: Callable[[Memoire], Any], **kwargs) -> DescriptionCapteur:
    """Capteur lu dans la mémoire ; indisponible tant qu'il n'a pas de valeur."""
    return DescriptionCapteur(
        key=suffixe, name=nom,
        valeur=lambda d: lire(d.memoire),
        present=lambda d: d.memoire is not None and lire(d.memoire) is not None,
        **kwargs,
    )


def _cumul(suffixe: str, nom: str, lire: Callable[[Memoire], float], **kwargs) -> DescriptionCapteur:
    """Compteur d'énergie en kWh. « total » comme la version YAML, dont il
    reprend la valeur : les statistiques long terme se poursuivent sans saut."""
    options = {"native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
               "device_class": SensorDeviceClass.ENERGY,
               "state_class": SensorStateClass.TOTAL, **kwargs}
    return _memo(suffixe, nom, lambda m: round(lire(m), 3), **options)


def etat_script(script: dict[str, Any] | None) -> str | None:
    """État lisible du script, d'après Script.GetStatus."""
    if script is None:
        return None
    if script.get("errors"):
        return "En erreur"
    return "En marche" if script.get("running") else "Arrêté"


def demarrage_shelly(shelly: dict[str, Any], maintenant: datetime) -> datetime | None:
    """Instant de démarrage du Shelly, arrondi à la minute.

    Recalculé à chaque relevé à partir de l'uptime : sans arrondi, quelques
    centaines de millisecondes d'écart feraient changer l'état à chaque fois.
    """
    uptime = (shelly.get("sys") or {}).get("uptime")
    if not isinstance(uptime, (int, float)):
        return None
    return (maintenant - timedelta(seconds=uptime)).replace(second=0, microsecond=0)


def _diag_script(suffixe: str, nom: str, champ: str, unite: str | None,
                 classe: SensorDeviceClass | None, icone: str) -> DescriptionCapteur:
    """Grandeur de Script.GetStatus, rangée dans le diagnostic."""
    return DescriptionCapteur(
        key=suffixe, name=nom, icon=icone,
        native_unit_of_measurement=unite, device_class=classe, state_class=MESURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        valeur=lambda d: d.script[champ],
        present=lambda d: isinstance((d.script or {}).get(champ), (int, float)),
        shelly=True,
    )


def _energie_requise(d: Donnees) -> float:
    return round(
        max(_i(d.proprietes, "socSet") / echelle_soc(d.proprietes)
            - _i(d.proprietes, "electricLevel"), 0)
        * capacite_totale(d.packs) / 100, 2)


def _santes(d: Donnees) -> list[float]:
    """Santé estimée de chaque pack présent et déjà mesuré."""
    valeurs = []
    for i, pk in enumerate(d.packs[:NB_PACKS_MAX]):
        s = d.memoire.sante(i, capacite_pack(pk.get("sn"), pk.get("packType")))
        if s is not None:
            valeurs.append(s)
    return valeurs

CAPTEURS: tuple[DescriptionCapteur, ...] = (
    DescriptionCapteur(
        key="modele", name="modèle", icon="mdi:tag-outline",
        valeur=lambda d: nom_modele(d.produit),
        # Chaîne « product » brute et SN : le tableau de bord en a besoin
        # (image du modèle, identification) sans capteur « raw ».
        attributs=lambda d: {"produit": d.produit, "sn": d.sn},
    ),
    DescriptionCapteur(
        key="ip", name="adresse IP", icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        valeur=lambda d: str(d.kvs.get("zendure_ip") or "") or None,
        present=lambda d: bool(d.kvs.get("zendure_ip")),
        shelly=True,
    ),
    # ---- État global ----
    _direct("soc", "SOC", "electricLevel", native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.BATTERY, state_class=MESURE),
    DescriptionCapteur(
        key="tension_batterie", name="tension batterie",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE, state_class=MESURE,
        valeur=lambda d: round(_i(d.proprietes, "BatVolt") / 100, 2),
    ),
    DescriptionCapteur(
        key="autonomie_restante", name="autonomie restante",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        valeur=lambda d: _i(d.proprietes, "remainOutTime"),
        # L'appareil renvoie une autonomie farfelue quand il ne décharge pas.
        present=lambda d: _i(d.proprietes, "packInputPower") > 20,
    ),
    DescriptionCapteur(
        key="temperature_boitier", name="température boîtier",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE, state_class=MESURE,
        valeur=lambda d: _dixiemes_kelvin(_i(d.proprietes, "hyperTmp", 2931)),
    ),
    DescriptionCapteur(
        key="wifi_rssi", name="RSSI Wi-Fi",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH, state_class=MESURE,
        # Une valeur positive ou nulle signale une liaison filaire : il n'y a
        # alors pas de niveau radio. Indisponible plutôt qu'« Inconnu ».
        valeur=lambda d: _i(d.proprietes, "rssi"),
        present=lambda d: _i(d.proprietes, "rssi") < 0,
    ),
    # ---- Photovoltaïque ----
    _direct("pv", "PV", "solarInputPower", **_W),
    _direct("pv_1", "PV 1", "solarPower1", **_W),
    _direct("pv_2", "PV 2", "solarPower2", **_W),
    # ---- Flux AC ----
    _direct("sortie_maison", "sortie maison", "outputHomePower", **_W),
    _direct("entree_reseau", "entrée réseau", "gridInputPower", **_W),
    DescriptionCapteur(
        key="sortie_secours", name="sortie secours", **_W,
        valeur=lambda d: (_i(d.proprietes, "gridOffPower")
                          + _i(d.proprietes, "gridOffPower2")),
    ),
    # ---- Point de livraison, lu sur la pince que suit la régulation ----
    DescriptionCapteur(
        key="reseau", name="réseau", **_W,
        valeur=lambda d: d.reseau,
        present=lambda d: d.reseau is not None,
        shelly=True,
    ),
    # ---- Flux batterie ----
    # + charge / − décharge, côté pack : même convention que la version YAML.
    DescriptionCapteur(
        key="puissance", name="puissance", **_W,
        valeur=lambda d: -puissance_batterie_nette(d.proprietes),
    ),
    DescriptionCapteur(
        key="etat", name="état", icon="mdi:battery-sync",
        valeur=lambda d: ("Charge" if (w := -puissance_batterie_nette(d.proprietes)) > 20
                          else "Décharge" if w < -20 else "Veille"),
    ),
    DescriptionCapteur(
        key="limite_soc", name="limite SOC", icon="mdi:battery-lock",
        valeur=lambda d: {0: "Normal", 1: "SOC max atteint", 2: "SOC min atteint"}.get(
            _i(d.proprietes, "socLimit", -1) % 16 if _i(d.proprietes, "socLimit", -1) >= 0 else -1,
            "Inconnu"),
    ),
    _direct("charge_batterie", "charge batterie", "outputPackPower", **_W),
    _direct("decharge_batterie", "décharge batterie", "packInputPower", **_W),
    DescriptionCapteur(
        key="puissance_batterie_nette", name="puissance batterie nette", **_W,
        valeur=lambda d: puissance_batterie_nette(d.proprietes),
    ),
    # ---- Consignes et limites ----
    _direct("limite_sortie", "limite sortie", "outputLimit", **_W),
    _direct("limite_charge", "limite charge", "inputLimit", **_W),
    _direct("plafond_onduleur", "plafond onduleur", "inverseMaxPower", **_W),
    _direct("plafond_charge", "plafond charge", "chargeMaxLimit", **_W),
    DescriptionCapteur(
        key="soc_min", name="SOC minimum", native_unit_of_measurement=PERCENTAGE,
        state_class=MESURE,
        valeur=lambda d: round(
            _i(d.proprietes, "minSoc") / echelle_soc(d.proprietes), 1),
    ),
    DescriptionCapteur(
        key="soc_max", name="SOC maximum", native_unit_of_measurement=PERCENTAGE,
        state_class=MESURE,
        valeur=lambda d: round(
            _i(d.proprietes, "socSet") / echelle_soc(d.proprietes), 1),
    ),
    # ---- Divers ----
    _direct("nombre_de_packs", "nombre de packs", "packNum"),
    DescriptionCapteur(
        key="mode_ac", name="mode AC", icon="mdi:swap-vertical",
        valeur=lambda d: {1: "Charge", 2: "Décharge"}.get(
            _i(d.proprietes, "acMode"), "Inconnu"),
    ),
    DescriptionCapteur(
        key="injection_pv", name="injection PV", icon="mdi:transmission-tower",
        valeur=lambda d: {0: "Auto", 1: "Autorisée", 2: "Interdite"}.get(
            _i(d.proprietes, "gridReverse", -1), "Inconnu"),
    ),
    DescriptionCapteur(
        key="mode_secours", name="mode secours", icon="mdi:power-plug-off",
        valeur=lambda d: {0: "Standard", 1: "Économique", 2: "Arrêt"}.get(
            _i(d.proprietes, "gridOffMode", -1), "Inconnu"),
    ),
    # ---- Synthèse des packs ----
    DescriptionCapteur(
        key="ecart_cellules_max", name="écart cellules max",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=MESURE,
        valeur=lambda d: (max(_i(p, "maxVol") for p in d.packs)
                          - min(_i(p, "minVol") for p in d.packs)) * 10,
        present=lambda d: bool(d.packs),
    ),
    DescriptionCapteur(
        key="temperature_pack_max", name="température pack max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE, state_class=MESURE,
        valeur=lambda d: _dixiemes_kelvin(max(_i(p, "maxTemp", 2931) for p in d.packs)),
        present=lambda d: bool(d.packs),
    ),
    DescriptionCapteur(
        key="ecart_soc_packs", name="écart SOC packs",
        native_unit_of_measurement=PERCENTAGE, state_class=MESURE,
        valeur=lambda d: (max(_i(p, "socLevel") for p in d.packs)
                          - min(_i(p, "socLevel") for p in d.packs)),
        present=lambda d: bool(d.packs),
    ),
    DescriptionCapteur(
        key="capacite_nominale_totale", name="capacité nominale totale",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE, state_class=MESURE,
        valeur=lambda d: capacite_totale(d.packs),
        present=lambda d: bool(d.packs),
    ),
    # Énergie exploitable entre les bornes SOC. La capacité n'est plus saisie
    # à la main : elle découle des packs réellement présents.
    DescriptionCapteur(
        key="energie_disponible", name="énergie disponible",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE, state_class=MESURE,
        valeur=lambda d: round(
            max(_i(d.proprietes, "electricLevel")
                - _i(d.proprietes, "minSoc") / echelle_soc(d.proprietes), 0)
            * capacite_totale(d.packs) / 100, 2),
        present=lambda d: bool(d.packs),
    ),
    DescriptionCapteur(
        key="energie_requise", name="énergie requise",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE, state_class=MESURE,
        valeur=_energie_requise,
        present=lambda d: bool(d.packs),
    ),
    DescriptionCapteur(
        key="temps_charge_restant", name="temps de charge restant",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        valeur=lambda d: round(_energie_requise(d) * 1000
                               / -puissance_batterie_nette(d.proprietes) * 60),
        present=lambda d: bool(d.packs) and -puissance_batterie_nette(d.proprietes) > 20,
    ),
    # ---- Photovoltaïque : répartition ----
    DescriptionCapteur(
        key="pv_vers_batterie", name="PV vers batterie", **_W,
        valeur=lambda d: pv_vers_batterie(d.proprietes),
    ),
    DescriptionCapteur(
        key="pv_vers_maison", name="PV vers maison", **_W,
        valeur=lambda d: pv_vers_maison(d.proprietes),
    ),
    DescriptionCapteur(
        key="passthrough_pv", name="passthrough PV", icon="mdi:solar-power",
        valeur=lambda d: "PV inactif" if _i(d.proprietes, "solarInputPower") == 0
        else {0: "Vers batterie", 2: "Vers maison"}.get(_i(d.proprietes, "pass", -1), "Inconnu"),
    ),
    # ---- Côté DC des packs ----
    DescriptionCapteur(
        key="charge_dc", name="charge DC", **_W,
        valeur=lambda d: puissance_dc_packs(d.packs, 1),
    ),
    DescriptionCapteur(
        key="decharge_dc", name="décharge DC", **_W,
        valeur=lambda d: puissance_dc_packs(d.packs, 2),
    ),
    # ---- Rendements instantanés, mesurables seulement sans PV ----
    DescriptionCapteur(
        key="efficacite_charge", name="efficacité charge",
        native_unit_of_measurement=PERCENTAGE, state_class=MESURE,
        valeur=lambda d: efficacite_charge(d.proprietes, d.packs),
        present=lambda d: efficacite_charge(d.proprietes, d.packs) is not None,
    ),
    DescriptionCapteur(
        key="efficacite_decharge", name="efficacité décharge",
        native_unit_of_measurement=PERCENTAGE, state_class=MESURE,
        valeur=lambda d: efficacite_decharge(d.proprietes, d.packs),
        present=lambda d: efficacite_decharge(d.proprietes, d.packs) is not None,
    ),
    # ---- Divers ----
    DescriptionCapteur(
        key="calibration", name="calibration", icon="mdi:battery-sync-outline",
        valeur=lambda d: "En cours" if _i(d.proprietes, "socStatus") == 1 else "Non",
    ),
    DescriptionCapteur(
        key="stockage", name="stockage", icon="mdi:memory",
        valeur=lambda d: "RAM" if _i(d.proprietes, "smartMode") == 1 else "Flash",
    ),
    # ---- Grandeurs à mémoire (voir memoire.py) ----
    _cumul("energie_chargee", "énergie chargée", lambda m: m.energie_chargee),
    _cumul("energie_dechargee", "énergie déchargée", lambda m: m.energie_dechargee),
    _cumul("energie_pv", "énergie PV", lambda m: m.energie_pv),
    _cumul("pv_jour", "PV jour", lambda m: m.pv_jour,
           state_class=SensorStateClass.TOTAL_INCREASING),
    _memo("rendement_global", "rendement global", lambda m: m.rendement_global,
          native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-sync"),
    _memo("rendement_charge", "rendement charge", lambda m: m.rendement_charge,
          native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-plus-variant"),
    _memo("rendement_decharge", "rendement décharge", lambda m: m.rendement_decharge,
          native_unit_of_measurement=PERCENTAGE, icon="mdi:battery-minus-variant"),
    _memo("efficacite_charge_24h", "efficacité charge 7 j", lambda m: m.efficacite_charge_7j,
          native_unit_of_measurement=PERCENTAGE, state_class=MESURE),
    _memo("efficacite_decharge_24h", "efficacité décharge 7 j", lambda m: m.efficacite_decharge_7j,
          native_unit_of_measurement=PERCENTAGE, state_class=MESURE),
    # Unité vide "" et non absente : c'est celle que history_stats leur donnait
    # dans la version YAML. Sans unité, Home Assistant la jugerait différente
    # de celle des statistiques déjà compilées et les suspendrait.
    _memo("commutations_charge_jour", "commutations charge jour",
          lambda m: m.commutations_charge, state_class=MESURE, icon="mdi:swap-vertical-bold",
          native_unit_of_measurement=""),
    _memo("commutations_decharge_jour", "commutations décharge jour",
          lambda m: m.commutations_decharge, state_class=MESURE, icon="mdi:swap-vertical-bold",
          native_unit_of_measurement=""),
    # Le compteur qui intéresse l'usure : changements de sens du relais.
    _memo("bascules_relais_jour", "bascules relais jour",
          lambda m: m.bascules_relais, state_class=MESURE, icon="mdi:electric-switch"),
    _memo("commutations_jour", "commutations jour",
          lambda m: m.commutations_charge + m.commutations_decharge,
          state_class=MESURE, icon="mdi:swap-vertical-bold"),
    _memo("zero_soutirage_jour", "zéro soutirage jour",
          lambda m: round(m.zero_soutirage_s / 3600, 2),
          native_unit_of_measurement=UnitOfTime.HOURS, device_class=SensorDeviceClass.DURATION,
          state_class=MESURE, shelly=True),
    _memo("derniere_calibration", "dernière calibration",
          lambda m: datetime.fromisoformat(m.derniere_calibration) if m.derniere_calibration else None,
          device_class=SensorDeviceClass.TIMESTAMP, icon="mdi:battery-check"),
    _memo("jours_depuis_calibration", "jours depuis calibration",
          lambda m: m.jours_depuis_calibration(datetime.now(timezone.utc)),
          native_unit_of_measurement="j", icon="mdi:calendar-clock"),
    # ---- Script de régulation et Shelly (relevés déjà faits à chaque cycle) ----
    DescriptionCapteur(
        key="script_etat", name="script état", icon="mdi:script-text-play",
        valeur=lambda d: etat_script(d.script),
        present=lambda d: d.script is not None,
        attributs=lambda d: {"erreurs": (d.script or {}).get("errors") or [],
                             "message": (d.script or {}).get("error_msg"),
                             "id": (d.script or {}).get("id")},
        shelly=True,
    ),
    _diag_script("script_cpu", "script CPU", "cpu", PERCENTAGE, None, "mdi:cpu-64-bit"),
    _diag_script("script_memoire", "script mémoire utilisée", "mem_used",
                 UnitOfInformation.BYTES, SensorDeviceClass.DATA_SIZE, "mdi:memory"),
    _diag_script("script_memoire_pic", "script mémoire pic", "mem_peak",
                 UnitOfInformation.BYTES, SensorDeviceClass.DATA_SIZE, "mdi:memory"),
    _diag_script("script_memoire_libre", "script mémoire libre", "mem_free",
                 UnitOfInformation.BYTES, SensorDeviceClass.DATA_SIZE, "mdi:memory"),
    DescriptionCapteur(
        key="script_version", name="script version", icon="mdi:tag",
        entity_category=EntityCategory.DIAGNOSTIC,
        valeur=lambda d: str(d.kvs.get("zendure_version")),
        present=lambda d: bool(d.kvs.get("zendure_version")),
        shelly=True,
    ),
    DescriptionCapteur(
        key="shelly_demarrage", name="Shelly démarrage", icon="mdi:restart",
        device_class=SensorDeviceClass.TIMESTAMP, entity_category=EntityCategory.DIAGNOSTIC,
        valeur=lambda d: demarrage_shelly(d.shelly, datetime.now(timezone.utc)),
        present=lambda d: demarrage_shelly(d.shelly, datetime.now(timezone.utc)) is not None,
        shelly=True,
    ),
    DescriptionCapteur(
        key="shelly_wifi_rssi", name="Shelly RSSI Wi-Fi",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH, state_class=MESURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        valeur=lambda d: ((d.shelly.get("wifi") or {}).get("rssi")),
        present=lambda d: isinstance((d.shelly.get("wifi") or {}).get("rssi"), (int, float)),
        shelly=True,
    ),
    # ---- Santé des packs ----
    DescriptionCapteur(
        key="sante_min", name="santé minimale", icon="mdi:battery-heart-variant",
        native_unit_of_measurement=PERCENTAGE, state_class=MESURE,
        valeur=lambda d: min(_santes(d)),
        present=lambda d: d.memoire is not None and bool(_santes(d)),
    ),
    DescriptionCapteur(
        key="mesure_sante_progression", name="mesure santé progression",
        native_unit_of_measurement=PERCENTAGE, icon="mdi:progress-helper",
        valeur=lambda d: d.memoire.progression_sante(d.packs),
        present=lambda d: d.memoire is not None,
    ),
)


def _capteurs_pack(n: int) -> tuple[DescriptionCapteur, ...]:
    """Capteurs du n-ième pack (n commence à 1)."""
    i = n - 1

    def pack(d: Donnees) -> dict[str, Any]:
        return d.packs[i] if len(d.packs) > i else {}

    def courant(d: Donnees) -> float:
        # Le champ est un entier 16 bits non signé : 65534 vaut −0,2 A.
        # Sans cette conversion, une charge afficherait 6553,4 A.
        c = _i(pack(d), "batcur")
        return round(((c - 65536) if c > 32767 else c) / 10, 1)

    def tension(d: Donnees) -> float:
        return round(_i(pack(d), "totalVol") / 100, 2)

    present = lambda d: len(d.packs) > i  # noqa: E731

    return (
        DescriptionCapteur(
            key=f"pack_{n}_soc", name=f"pack {n} SOC",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.BATTERY, state_class=MESURE,
            valeur=lambda d: _i(pack(d), "socLevel"), present=present,
        ),
        DescriptionCapteur(
            key=f"pack_{n}_puissance", name=f"pack {n} puissance", **_W,
            valeur=lambda d: _i(pack(d), "power"), present=present,
        ),
        DescriptionCapteur(
            key=f"pack_{n}_tension", name=f"pack {n} tension",
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE, state_class=MESURE,
            valeur=tension, present=present,
        ),
        DescriptionCapteur(
            key=f"pack_{n}_courant", name=f"pack {n} courant",
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            device_class=SensorDeviceClass.CURRENT, state_class=MESURE,
            valeur=courant, present=present,
        ),
        DescriptionCapteur(
            key=f"pack_{n}_temperature", name=f"pack {n} température",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE, state_class=MESURE,
            valeur=lambda d: _dixiemes_kelvin(_i(pack(d), "maxTemp", 2931)),
            present=present,
        ),
        DescriptionCapteur(
            key=f"pack_{n}_ecart_cellules", name=f"pack {n} écart cellules",
            native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
            state_class=MESURE,
            valeur=lambda d: (_i(pack(d), "maxVol") - _i(pack(d), "minVol")) * 10,
            present=present,
        ),
        DescriptionCapteur(
            key=f"pack_{n}_puissance_dc", name=f"pack {n} puissance DC", **_W,
            valeur=lambda d: round(tension(d) * courant(d), 1), present=present,
        ),
        DescriptionCapteur(
            key=f"pack_{n}_capacite_nominale", name=f"pack {n} capacité nominale",
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY_STORAGE, state_class=MESURE,
            valeur=lambda d: capacite_pack(pack(d).get("sn"), pack(d).get("packType")),
            present=present,
        ),
        # Énergie DC nette échangée : monte en charge, descend en décharge.
        DescriptionCapteur(
            key=f"pack_{n}_energie_dc", name=f"pack {n} énergie DC",
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL,
            valeur=lambda d: round(d.memoire.packs[i]["energie_dc"], 2),
            present=lambda d: present(d) and d.memoire is not None,
        ),
        DescriptionCapteur(
            key=f"pack_{n}_capacite_estimee", name=f"pack {n} capacité estimée",
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY_STORAGE, state_class=MESURE,
            icon="mdi:battery-heart-variant",
            valeur=lambda d: round(d.memoire.packs[i]["capacite"]),
            present=lambda d: present(d) and d.memoire is not None
            and d.memoire.packs[i]["capacite"] > 0,
        ),
        DescriptionCapteur(
            key=f"pack_{n}_sante", name=f"pack {n} santé",
            native_unit_of_measurement=PERCENTAGE, state_class=MESURE,
            icon="mdi:battery-heart-variant",
            valeur=lambda d: d.memoire.sante(
                i, capacite_pack(pack(d).get("sn"), pack(d).get("packType"))),
            present=lambda d: present(d) and d.memoire is not None and d.memoire.sante(
                i, capacite_pack(pack(d).get("sn"), pack(d).get("packType"))) is not None,
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinateur: CoordinateurZendure = hass.data[DOMAIN][entry.entry_id]
    nb_packs = entry.options.get(
        CONF_NB_PACKS, entry.data.get(CONF_NB_PACKS, DEFAUT_NB_PACKS))

    descriptions = list(CAPTEURS)
    for n in range(1, int(nb_packs) + 1):
        descriptions.extend(_capteurs_pack(n))

    async_add_entities(CapteurZendure(coordinateur, d) for d in descriptions)


class CapteurZendure(EntiteZendure, SensorEntity):
    """Capteur dont la valeur est calculée à partir du rapport."""

    entity_description: DescriptionCapteur

    def __init__(self, coordinateur: CoordinateurZendure,
                 description: DescriptionCapteur) -> None:
        super().__init__(coordinateur, description.key, "sensor")
        self.entity_description = description

    @property
    def available(self) -> bool:
        if self.entity_description.shelly:
            if not CoordinatorEntity.available.fget(self) or self.coordinator.data is None:
                return False
        elif not super().available:
            return False
        try:
            return self.entity_description.present(self.coordinator.data)
        except (TypeError, ValueError, IndexError, KeyError):
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        lire = self.entity_description.attributs
        if lire is None or self.coordinator.data is None:
            return None
        return lire(self.coordinator.data)

    @property
    def native_value(self) -> Any:
        donnees = self.coordinator.data
        if donnees is None:
            return None
        try:
            return self.entity_description.valeur(donnees)
        except (TypeError, ValueError, IndexError, KeyError, ZeroDivisionError):
            # Un rapport incomplet ne doit pas faire remonter d'exception
            # jusqu'au journal à chaque cycle de sondage.
            return None
