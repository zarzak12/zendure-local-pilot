"""Exécute les capteurs de l'intégration sur un rapport réel.

Compiler ne prouve rien sur les formules. Ce banc remplace Home Assistant par
des doublures minimales, puis fait tourner CHAQUE fonction de lecture sur le
rapport réellement renvoyé par une SolarFlow 4000 MIX PRO, et sur des cas
dégradés. Objectif : attraper les erreurs de portage des anciens modèles
Jinja (conversions d'unités, entier signé, champs absents) sans avoir besoin
d'une instance Home Assistant.

    python tests/test_capteurs.py
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "custom_components", "zendure_local_pilot")


# --------------------------------------------------------------------------
# Doublures de Home Assistant
# --------------------------------------------------------------------------
def _module(nom: str, **attributs):
    m = types.ModuleType(nom)
    for cle, valeur in attributs.items():
        setattr(m, cle, valeur)
    sys.modules[nom] = m
    return m


class _Souscriptible:
    def __class_getitem__(cls, _):
        return cls


class _Enum(str):
    """Remplace les énumérations d'unités : seule la valeur importe ici."""

    def __getattr__(self, nom):
        return nom.lower()


@dataclasses.dataclass(frozen=True, kw_only=True)
class _EntityDescription:
    key: str
    name: str | None = None
    icon: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    native_unit_of_measurement: str | None = None


def _prepare_doublures():
    if "aiohttp" not in sys.modules:
        try:
            import aiohttp  # noqa: F401
        except ImportError:
            _module("aiohttp", ClientSession=object, ClientError=Exception,
                    ClientTimeout=lambda **k: None)

    ha = _module("homeassistant")
    ha.__path__ = []
    _module("homeassistant.core", HomeAssistant=object, callback=lambda f: f)
    _module("homeassistant.config_entries", ConfigEntry=object,
            ConfigFlow=object, ConfigFlowResult=object, OptionsFlow=object)
    _module("homeassistant.const",
            PERCENTAGE="%", SIGNAL_STRENGTH_DECIBELS_MILLIWATT="dBm",
            UnitOfElectricCurrent=_Enum(), UnitOfElectricPotential=_Enum(),
            UnitOfEnergy=_Enum(), UnitOfPower=_Enum(),
            UnitOfTemperature=_Enum(), UnitOfTime=_Enum(),
            EntityCategory=_Enum(), Platform=_Enum())
    helpers = _module("homeassistant.helpers")
    helpers.__path__ = []
    _module("homeassistant.helpers.aiohttp_client",
            async_get_clientsession=lambda hass: None)
    _module("homeassistant.helpers.update_coordinator",
            DataUpdateCoordinator=_Souscriptible,
            CoordinatorEntity=_Souscriptible,
            UpdateFailed=type("UpdateFailed", (Exception,), {}))
    _module("homeassistant.helpers.device_registry", DeviceInfo=dict)
    _module("homeassistant.helpers.entity_platform",
            AddEntitiesCallback=object)
    _module("homeassistant.components")
    sys.modules["homeassistant.components"].__path__ = []
    _module("homeassistant.components.sensor",
            SensorDeviceClass=_Enum(), SensorStateClass=_Enum(),
            SensorEntity=object, SensorEntityDescription=_EntityDescription)

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class _NumberDescription(_EntityDescription):
        native_min_value: float = 0
        native_max_value: float = 100
        native_step: float = 1
        mode: str | None = None
        entity_registry_enabled_default: bool = True
        entity_category: str | None = None

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class _SelectDescription(_EntityDescription):
        options: list | None = None
        translation_key: str | None = None
        entity_category: str | None = None

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class _BinaryDescription(_EntityDescription):
        entity_category: str | None = None

    _module("homeassistant.components.number",
            NumberDeviceClass=_Enum(), NumberMode=_Enum(),
            NumberEntity=object, NumberEntityDescription=_NumberDescription)
    _module("homeassistant.components.select",
            SelectEntity=object, SelectEntityDescription=_SelectDescription)
    _module("homeassistant.components.switch",
            SwitchDeviceClass=_Enum(), SwitchEntity=object)
    _module("homeassistant.components.binary_sensor",
            BinarySensorDeviceClass=_Enum(), BinarySensorEntity=object,
            BinarySensorEntityDescription=_BinaryDescription)


_prepare_doublures()

_paquet = types.ModuleType("zlp")
_paquet.__path__ = [DOSSIER]
sys.modules["zlp"] = _paquet


def _charge(nom: str):
    spec = importlib.util.spec_from_file_location(
        f"zlp.{nom}", os.path.join(DOSSIER, f"{nom}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"zlp.{nom}"] = module
    spec.loader.exec_module(module)
    return module


for _nom in ("const", "calculs", "zendure", "shelly", "coordinator", "entity"):
    _charge(_nom)
capteurs = _charge("sensor")
nombres = _charge("number")
choix = _charge("select")
binaires = _charge("binary_sensor")
coordinator = sys.modules["zlp.coordinator"]
const = sys.modules["zlp.const"]


# --------------------------------------------------------------------------
# Rapport réellement renvoyé par une SolarFlow 4000 MIX PRO
# --------------------------------------------------------------------------
RAPPORT_REEL = {
    "sn": "EEE3NDP6P250210",
    "product": "solarFlow4000MixPro",
    "properties": {
        "packInputPower": 0, "outputPackPower": 0, "outputHomePower": 0,
        "remainOutTime": 16860, "electricLevel": 17, "gridInputPower": 0,
        "solarInputPower": 0, "solarPower1": 0, "solarPower2": 0,
        "hyperTmp": 3081, "gridOffPower": 0, "gridOffPower2": 0,
        "BatVolt": 2631, "outputLimit": 181, "inputLimit": 0,
        "socSet": 1000, "minSoc": 100, "gridReverse": 2,
        "inverseMaxPower": 3000, "chargeMaxLimit": 3000, "acMode": 2,
        "packNum": 1, "rssi": -40, "is_error": 0, "gridState": 1,
    },
    "packData": [{
        "sn": "BEAAVCADA240984", "packType": 70, "socLevel": 17, "state": 2,
        "power": 5, "maxTemp": 2940, "totalVol": 2624, "batcur": 65534,
        "maxVol": 328, "minVol": 328, "softVersion": 4144,
    }],
}


def _donnees(rapport):
    d = coordinator.Donnees()
    d.rapport = rapport
    return d


def _toutes_descriptions(nb_packs=4):
    descriptions = list(capteurs.CAPTEURS)
    for n in range(1, nb_packs + 1):
        descriptions.extend(capteurs._capteurs_pack(n))
    return descriptions


def _valeur(cle, donnees):
    for d in _toutes_descriptions():
        if d.key == cle:
            return d.valeur(donnees) if d.present(donnees) else "INDISPONIBLE"
    raise AssertionError(f"capteur absent : {cle}")


def test_valeurs_sur_rapport_reel():
    d = _donnees(RAPPORT_REEL)
    attendus = {
        "modele": "SolarFlow 4000 MIX PRO",
        "soc": 17,
        "tension_batterie": 26.31,
        "temperature_boitier": 35.0,
        "wifi_rssi": -40,
        "limite_sortie": 181,
        "plafond_onduleur": 3000,
        "plafond_charge": 3000,
        # socSet 1000 et minSoc 100 sont en pour-mille : 100 % et 10 %
        "soc_max": 100.0,
        "soc_min": 10.0,
        "mode_ac": "Décharge",
        "injection_pv": "Interdite",
        "nombre_de_packs": 1,
        "puissance_batterie_nette": 0,
        "sortie_secours": 0,
        "capacite_nominale_totale": 8.0,
        "pack_1_soc": 17,
        "pack_1_tension": 26.24,
        # batcur 65534 est un entier 16 bits signé : -0,2 A, pas 6553,4 A
        "pack_1_courant": -0.2,
        "pack_1_temperature": 20.9,
        "pack_1_ecart_cellules": 0,
        "pack_1_puissance_dc": -5.2,
        "pack_1_capacite_nominale": 8.0,
        "ecart_soc_packs": 0,
        "temperature_pack_max": 20.9,
        # 17 % - 10 % de 8 kWh
        "energie_disponible": 0.56,
        # 100 % - 17 % de 8 kWh
        "energie_requise": 6.64,
    }
    for cle, attendu in attendus.items():
        obtenu = _valeur(cle, d)
        assert obtenu == attendu, f"{cle} : {obtenu!r} au lieu de {attendu!r}"


def test_packs_absents_sont_indisponibles():
    d = _donnees(RAPPORT_REEL)
    # Un seul pack est présent : les capteurs des packs 2 à 4 ne doivent pas
    # afficher 0, ce qui ferait croire à un pack en panne.
    for n in (2, 3, 4):
        for mesure in ("soc", "tension", "courant", "capacite_nominale"):
            assert _valeur(f"pack_{n}_{mesure}", d) == "INDISPONIBLE"


def test_autonomie_masquee_hors_decharge():
    d = _donnees(RAPPORT_REEL)
    # packInputPower vaut 0 : l'autonomie annoncée (16 860 min) n'a aucun sens
    assert _valeur("autonomie_restante", d) == "INDISPONIBLE"
    actif = dict(RAPPORT_REEL)
    actif["properties"] = {**RAPPORT_REEL["properties"], "packInputPower": 800}
    assert _valeur("autonomie_restante", _donnees(actif)) == 16860


def test_liaison_filaire_sans_rssi():
    # rssi à 0 signale une liaison Ethernet : pas de niveau radio à afficher
    filaire = dict(RAPPORT_REEL)
    filaire["properties"] = {**RAPPORT_REEL["properties"], "rssi": 0}
    assert _valeur("wifi_rssi", _donnees(filaire)) is None


def test_modele_sans_photovoltaique():
    """Le SolarFlow 2400 AC n'a pas d'entrée PV : aucun capteur ne doit casser."""
    sans_pv = {
        "sn": "X", "product": "solarFlow2400AC",
        "properties": {"electricLevel": 50, "socSet": 1000, "minSoc": 100},
        "packData": [{"sn": "JO4A1", "packType": 500, "socLevel": 50}],
    }
    d = _donnees(sans_pv)
    assert _valeur("modele", d) == "SolarFlow 2400 AC"
    assert _valeur("pv", d) == 0
    assert _valeur("pack_1_capacite_nominale", d) == 2.40
    # Aucune des lectures ne doit lever, même sur un rapport très incomplet
    for description in _toutes_descriptions(1):
        if description.present(d):
            description.valeur(d)


def test_rapport_vide_ne_leve_jamais():
    d = _donnees({"properties": {}, "packData": []})
    for description in _toutes_descriptions():
        if description.present(d):
            description.valeur(d)


def test_pas_de_cle_dupliquee():
    cles = [d.key for d in _toutes_descriptions()]
    doublons = {c for c in cles if cles.count(c) > 1}
    assert not doublons, f"identifiants en double : {doublons}"


# --------------------------------------------------------------------------
# Contrôles : ils ECRIVENT dans la batterie, une erreur y coûte plus cher
# --------------------------------------------------------------------------
class _FauxCoordinateur:
    """Enregistre les écritures au lieu de les envoyer."""

    def __init__(self, donnees):
        self.data = donnees
        self.ecritures = []

    async def ecrire_batterie(self, proprietes):
        self.ecritures.append(("batterie", proprietes))

    async def ecrire_batterie_persistant(self, proprietes):
        self.ecritures.append(("persistant", proprietes))

    async def ecrire_composant_virtuel(self, composant, valeur):
        self.ecritures.append(("vc", composant, valeur))

    async def ecrire_kvs(self, cle, valeur):
        self.ecritures.append(("kvs", cle, valeur))


def _lancer(coroutine):
    import asyncio
    return asyncio.run(coroutine)


def _controles():
    return [*nombres.NOMBRES_BATTERIE, *nombres.NOMBRES_SHELLY,
            *nombres._nombres_kvs()]


def _controle(cle):
    for d in _controles():
        if d.key == cle:
            return d
    raise AssertionError(f"curseur absent : {cle}")


def test_lecture_des_curseurs():
    d = _donnees(RAPPORT_REEL)
    # minSoc 100 et socSet 1000 sont en pour-mille : les curseurs doivent
    # afficher 10 % et 100 %, et non 100 % et 1000 %.
    assert _controle("soc_min_consigne").valeur(d) == 10
    assert _controle("soc_max_consigne").valeur(d) == 100
    assert _controle("plafond_decharge_consigne").valeur(d) == 3000


def test_ecriture_des_bornes_soc_respecte_l_echelle():
    coord = _FauxCoordinateur(_donnees(RAPPORT_REEL))
    _lancer(_controle("soc_min_consigne").ecrire(coord, 20))
    _lancer(_controle("soc_max_consigne").ecrire(coord, 90))
    assert coord.ecritures == [
        ("persistant", {"minSoc": 200}),
        ("persistant", {"socSet": 900}),
    ], coord.ecritures

    # Firmware en pourcentages bruts (socSet <= 100) : on ne doit PAS
    # multiplier, sous peine d'envoyer une consigne de 900 %.
    brut = dict(RAPPORT_REEL)
    brut["properties"] = {**RAPPORT_REEL["properties"], "socSet": 100, "minSoc": 10}
    coord = _FauxCoordinateur(_donnees(brut))
    _lancer(_controle("soc_max_consigne").ecrire(coord, 90))
    assert coord.ecritures == [("persistant", {"socSet": 90})]


def test_bornes_des_curseurs_suivent_la_batterie():
    d = _donnees(RAPPORT_REEL)
    assert _controle("decharge_max").bornes(d) == (0, 3000)
    assert _controle("charge_max").bornes(d) == (0, 3000)
    # Batterie encore muette : on se replie, sans inventer une limite basse
    # qui briderait un 4000.
    vide = _donnees({"properties": {}, "packData": []})
    assert _controle("decharge_max").bornes(vide) == (0, const.LIMITE_REPLI)


def test_reglages_kvs_restent_types():
    coord = _FauxCoordinateur(_donnees(RAPPORT_REEL))
    # period est un entier : l'écrire en flottant casserait les comparaisons
    # du script, qui tourne en mJS.
    _lancer(_controle("period").ecrire(coord, 2000.0))
    _lancer(_controle("gain").ecrire(coord, 0.85))
    assert coord.ecritures == [
        ("kvs", "zendure_period", 2000),
        ("kvs", "zendure_gain", 0.85),
    ], coord.ecritures
    assert isinstance(coord.ecritures[0][2], int)


def test_listes_de_choix():
    d = _donnees(RAPPORT_REEL)
    par_cle = {c.key: c for c in choix.CHOIX}
    # gridReverse 2 = injection interdite
    assert par_cle["injection_pv_consigne"].valeur(d) == "interdite"
    coord = _FauxCoordinateur(d)
    _lancer(par_cle["injection_pv_consigne"].ecrire(coord, "autorisee"))
    _lancer(par_cle["mode_secours_consigne"].ecrire(coord, "arret"))
    assert coord.ecritures == [
        ("persistant", {"gridReverse": 1}),
        ("persistant", {"gridOffMode": 2}),
    ], coord.ecritures


def test_choix_sans_valeur_connue():
    # gridOffMode absent du rapport : afficher « standard » laisserait croire
    # à un réglage qui n'a pas été lu.
    d = _donnees(RAPPORT_REEL)
    par_cle = {c.key: c for c in choix.CHOIX}
    assert par_cle["mode_secours_consigne"].valeur(d) is None
    assert par_cle["mode"].valeur(d) is None


def test_mode_lu_depuis_le_shelly():
    d = _donnees(RAPPORT_REEL)
    d.shelly = {"enum:200": {"id": 200, "value": "autoconso"}}
    d.kvs = {"zendure_em": 2}
    par_cle = {c.key: c for c in choix.CHOIX}
    assert par_cle["mode"].valeur(d) == "autoconso"
    assert par_cle["canal_em"].valeur(d) == "2"
    # Un mode inconnu du script ne doit pas être affiché comme valide
    d.shelly = {"enum:200": {"id": 200, "value": "turbo"}}
    assert par_cle["mode"].valeur(d) is None


def test_etats_binaires():
    d = _donnees(RAPPORT_REEL)
    d.shelly = {"boolean:200": {"value": True}}
    d.script = {"running": True}
    par_cle = {b.key: b for b in binaires.BINAIRES}
    assert par_cle["en_veille"].valeur(d) is True
    assert par_cle["script_shelly"].valeur(d) is True
    assert par_cle["batterie_joignable"].valeur(d) is True
    assert par_cle["defaut"].valeur(d) is False
    # faultLevel non nul doit lever l'alerte même si is_error vaut 0
    alerte = dict(RAPPORT_REEL)
    alerte["properties"] = {**RAPPORT_REEL["properties"], "faultLevel": 3}
    assert par_cle["defaut"].valeur(_donnees(alerte)) is True


def test_toutes_les_options_sont_traduites():
    import json
    for langue in ("fr", "en"):
        chemin = os.path.join(DOSSIER, "translations", f"{langue}.json")
        with open(chemin, encoding="utf-8") as f:
            traductions = json.load(f)
        selects = traductions.get("entity", {}).get("select", {})
        for description in choix.CHOIX:
            cle = description.translation_key
            assert cle in selects, f"{langue} : traduction absente pour {cle}"
            etats = selects[cle].get("state", {})
            manquants = set(description.options or []) - set(etats)
            assert not manquants, f"{langue}/{cle} : options non traduites {manquants}"


def test_ecriture_persistante_retablit_smartmode():
    """Sans rétablissement de smartMode, la batterie refuserait ensuite les
    consignes rapides de la régulation : la batterie resterait figée."""
    import asyncio

    class _Faux:
        def __init__(self):
            self.ecritures = []

        async def ecrire_batterie(self, proprietes):
            self.ecritures.append(proprietes)

    faux = _Faux()
    veilles = []
    coordinator.asyncio = types.SimpleNamespace(
        sleep=lambda d: veilles.append(d) or asyncio.sleep(0))
    try:
        asyncio.run(coordinator.CoordinateurZendure.ecrire_batterie_persistant(
            faux, {"socSet": 900}))
    finally:
        coordinator.asyncio = asyncio

    assert faux.ecritures == [
        {"smartMode": 0, "socSet": 900},
        {"smartMode": 1},
    ], faux.ecritures
    assert veilles == [2], "la batterie a besoin d'un délai avant le rétablissement"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    echecs = 0
    for t in tests:
        try:
            t()
            print(f"  OK     {t.__name__}")
        except AssertionError as err:
            echecs += 1
            print(f"  ECHEC  {t.__name__}\n           {err}")
        except Exception as err:  # noqa: BLE001
            echecs += 1
            print(f"  ERREUR {t.__name__}\n           {type(err).__name__}: {err}")
    print(f"\n{len(_toutes_descriptions())} capteurs declares")
    print(f"RESULTAT : {len(tests) - echecs}/{len(tests)} tests au vert")
    sys.exit(1 if echecs else 0)
