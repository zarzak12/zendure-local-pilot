"""Tests de la logique métier de l'intégration.

Volontairement exécutables sans Home Assistant : on charge les modules sans
déclencher l'__init__ du paquet, qui lui dépend de Home Assistant. Cela permet
de vérifier le portage des anciens modèles Jinja sur n'importe quelle machine,
y compris une version de Python que Home Assistant ne supporte pas encore.

    python tests/test_calculs.py        (autonome)
    pytest tests/test_calculs.py        (dans une CI)
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "custom_components", "zendure_local_pilot")

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


_charge("const")
calculs = _charge("calculs")


def test_nom_modele():
    assert calculs.nom_modele("solarFlow4000MixPro") == "SolarFlow 4000 MIX PRO"
    assert calculs.nom_modele("solarFlow2400AC+") == "SolarFlow 2400 AC+"
    assert calculs.nom_modele("solarFlow800Pro") == "SolarFlow 800 Pro"
    # Un modèle encore inconnu doit dégrader proprement, pas afficher du jargon
    assert calculs.nom_modele("solarFlow5000MixUltra") == "SolarFlow 5000MixUltra"
    for vide in (None, "", "unknown", "unavailable"):
        assert calculs.nom_modele(vide) == "SolarFlow"


def test_capacite_pack():
    # Pack réel de référence : le portage ne doit RIEN changer pour lui
    assert calculs.capacite_pack("BEAAVCADA240984", 70) == 8.00
    # Même préfixe B mais autre packType : AB1000S, pas un pack interne
    assert calculs.capacite_pack("BXXX1234567890", 300) == 0.96
    assert calculs.capacite_pack("AXX31234567890", 0) == 2.40    # AIO2400
    assert calculs.capacite_pack("AXXA1234567890", 250) == 0.96  # AB1000
    assert calculs.capacite_pack("CXXF1234567890", 300) == 1.92  # AB2000S
    assert calculs.capacite_pack("FXXX1234567890", 5) == 2.88    # AB3000
    assert calculs.capacite_pack("GXXX1234567890", 5) == 2.88    # AB3000L
    assert calculs.capacite_pack("JO4A1234567890", 500) == 2.40  # I2400
    # Préfixe inconnu : repli sur packType, puis zéro
    assert calculs.capacite_pack("ZZZZ1234567890", 300) == 1.92
    assert calculs.capacite_pack("ZZZZ1234567890", 999) == 0.0
    # Données absentes ou corrompues : jamais d'exception
    assert calculs.capacite_pack(None, None) == 0.0
    assert calculs.capacite_pack("", "pas un nombre") == 0.0


def test_echelle_soc():
    # Firmware en pour-mille : socSet 1000 = 100 %
    assert calculs.echelle_soc({"socSet": 1000}) == 10
    assert calculs.echelle_soc({"socSet": 900}) == 10
    # Firmware en pourcentage brut
    assert calculs.echelle_soc({"socSet": 100}) == 1
    assert calculs.echelle_soc({"socSet": 85}) == 1
    # Le piège : minSoc 100 vaut 10 % en pour-mille et serait illisible si on
    # se fiait à minSoc seul. C'est bien socSet qui doit trancher.
    assert calculs.echelle_soc({"socSet": 1000, "minSoc": 100}) == 10


def test_limites_materielles():
    assert calculs.limites_materielles(
        {"inverseMaxPower": 3000, "chargeMaxLimit": 3000}) == (3000, 3000)
    assert calculs.limites_materielles(
        {"inverseMaxPower": 2400, "chargeMaxLimit": 3200}) == (2400, 3200)
    # Absent ou aberrant : on n'invente pas de limite, on n'en applique aucune
    assert calculs.limites_materielles({}) == (0, 0)
    assert calculs.limites_materielles(
        {"inverseMaxPower": 0, "chargeMaxLimit": 99999}) == (0, 0)


def test_puissance_batterie_nette():
    assert calculs.puissance_batterie_nette(
        {"packInputPower": 800, "outputPackPower": 0}) == 800
    assert calculs.puissance_batterie_nette(
        {"packInputPower": 0, "outputPackPower": 1200}) == -1200
    assert calculs.puissance_batterie_nette({}) == 0


def test_rendements_seulement_en_conditions_representatives():
    sans_pv = {"solarInputPower": 0}
    # 1000 W pris, 940 W stockés : 94 %
    assert calculs.efficacite_charge({**sans_pv, "gridInputPower": 1000},
                                     [{"state": 1, "power": 940}]) == 94.0
    # Sous 300 W : non mesuré
    assert calculs.efficacite_charge({**sans_pv, "gridInputPower": 60},
                                     [{"state": 1, "power": 21}]) is None
    # Hors 60-100 % : écarté, pas plafonné à 100
    assert calculs.efficacite_charge({**sans_pv, "gridInputPower": 1000},
                                     [{"state": 1, "power": 1100}]) is None
    assert calculs.efficacite_decharge({**sans_pv, "outputHomePower": 893},
                                       [{"state": 2, "power": 1000}]) == 89.3
    assert calculs.efficacite_decharge({**sans_pv, "outputHomePower": 100},
                                       [{"state": 2, "power": 200}]) is None
    # Avec du PV : jamais
    assert calculs.efficacite_charge({"solarInputPower": 500, "gridInputPower": 1000},
                                     [{"state": 1, "power": 940}]) is None


def test_capacite_totale():
    packs = [{"sn": "BEAAVCADA240984", "packType": 70}]
    assert calculs.capacite_totale(packs) == 8.00
    packs = [{"sn": "CXXF1", "packType": 300}, {"sn": "CXXF2", "packType": 300}]
    assert calculs.capacite_totale(packs) == 3.84
    assert calculs.capacite_totale([]) == 0.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    echecs = 0
    for t in tests:
        try:
            t()
            print(f"  OK     {t.__name__}")
        except AssertionError as err:
            echecs += 1
            print(f"  ECHEC  {t.__name__}  {err}")
    print(f"\nRESULTAT : {len(tests) - echecs}/{len(tests)} tests au vert")
    sys.exit(1 if echecs else 0)
