"""Tests des grandeurs à mémoire : compteurs, statistiques du jour, santé.

Exécutables sans Home Assistant, comme test_calculs.py.

    python tests/test_memoire.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "custom_components", "zendure_local_pilot")

_paquet = types.ModuleType("zlp")
_paquet.__path__ = [DOSSIER]
sys.modules["zlp"] = _paquet


def _charge(nom: str):
    spec = importlib.util.spec_from_file_location(f"zlp.{nom}", os.path.join(DOSSIER, f"{nom}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"zlp.{nom}"] = module
    spec.loader.exec_module(module)
    return module


_charge("const")
calculs = _charge("calculs")
memoire = _charge("memoire")

PACK_8KWH = {"sn": "BEAAVCADA240984", "packType": 70}
T0 = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)


class Releve:
    """Doublure minimale de Donnees."""

    def __init__(self, proprietes=None, packs=None, reseau=None, joignable=True):
        self.proprietes = proprietes or {}
        self.packs = packs or []
        self.reseau = reseau
        self.batterie_joignable = joignable


def _rejouer(m, releves, pas_s=5, depart=T0):
    t = depart
    for r in releves:
        m.mettre_a_jour(r, t)
        t += timedelta(seconds=pas_s)
    return t


def test_compteurs_d_energie():
    m = memoire.Memoire()
    # 1 h de charge à 1000 W et de PV à 2000 W, relevés toutes les 5 s
    r = Releve({"outputPackPower": 1000, "solarInputPower": 2000})
    _rejouer(m, [r] * 721)
    assert abs(m.energie_chargee - 1.0) < 0.001, m.energie_chargee
    assert abs(m.energie_pv - 2.0) < 0.001
    assert abs(m.pv_jour - 2.0) < 0.001
    assert m.energie_dechargee == 0


def test_pas_d_energie_inventee_pendant_une_coupure():
    m = memoire.Memoire()
    r = Releve({"outputPackPower": 1000})
    m.mettre_a_jour(r, T0)
    # HA arrêté 10 minutes : la puissance de l'intervalle est inconnue
    m.mettre_a_jour(r, T0 + timedelta(minutes=10))
    assert m.energie_chargee == 0
    # Batterie muette entre deux relevés : même chose
    m.mettre_a_jour(Releve(joignable=False), T0 + timedelta(minutes=10, seconds=5))
    m.mettre_a_jour(r, T0 + timedelta(minutes=10, seconds=10))
    assert m.energie_chargee == 0


def test_remise_a_zero_quotidienne():
    m = memoire.Memoire()
    _rejouer(m, [Releve({"solarInputPower": 1000, "outputPackPower": 500})] * 100)
    m.commutations_charge = 3
    assert m.pv_jour > 0
    lendemain = datetime(2026, 6, 22, 0, 0, 1, tzinfo=timezone.utc)
    m.mettre_a_jour(Releve({"solarInputPower": 0}), lendemain)
    assert m.pv_jour == 0 and m.commutations_charge == 0 and m.zero_soutirage_s == 0
    # Le compteur total, lui, ne repart jamais de zéro
    assert m.energie_pv > 0


def test_zero_soutirage_du_jour():
    m = memoire.Memoire()
    # 60 s à −50 W (injection) puis 60 s à +200 W (soutirage)
    _rejouer(m, [Releve(reseau=-50)] * 12 + [Releve(reseau=200)] * 13)
    assert m.zero_soutirage_s == 60, m.zero_soutirage_s


def test_calibration_au_franchissement_de_99():
    m = memoire.Memoire()
    fin = _rejouer(m, [Releve({"electricLevel": s}) for s in (97, 98, 99, 100, 100)])
    assert m.derniere_calibration == (T0 + timedelta(seconds=15)).isoformat()
    assert m.jours_depuis_calibration(fin + timedelta(days=3)) == 3
    # Rester à 100 % ne redéclenche pas
    avant = m.derniere_calibration
    _rejouer(m, [Releve({"electricLevel": 100})] * 3, depart=fin)
    assert m.derniere_calibration == avant


def test_commutations():
    m = memoire.Memoire()
    # + charge / − décharge : outputPackPower = charge, packInputPower = décharge
    etats = [{"outputPackPower": 500}, {}, {"packInputPower": 400}, {"packInputPower": 300},
             {"outputPackPower": 800}]
    _rejouer(m, [Releve(p) for p in etats])
    assert (m.commutations_charge, m.commutations_decharge) == (1, 1)


def test_rendements_conservent_la_derniere_mesure():
    m = memoire.Memoire()
    # Charge réseau sans PV : 1000 W pris, 940 W stockés côté DC
    charge = Releve({"gridInputPower": 1000}, [{"state": 1, "power": 940}])
    m.mettre_a_jour(charge, T0)
    assert m.rendement_charge == 94.0
    # Au repos, la dernière mesure reste affichée
    m.mettre_a_jour(Releve({}), T0 + timedelta(seconds=5))
    assert m.rendement_charge == 94.0
    assert m.efficacite_charge_7j == 94.0
    # Avec du PV, la mesure n'a pas de sens et n'est pas prise
    m.mettre_a_jour(Releve({"gridInputPower": 1000, "solarInputPower": 500},
                           [{"state": 1, "power": 1400}]), T0 + timedelta(seconds=10))
    assert m.rendement_charge == 94.0


def test_rendement_ignore_les_mesures_non_representatives():
    m = memoire.Memoire()
    # 60 W pris au réseau pour 21 W stockés : vrai à cette puissance, mais
    # c'est le talon de l'onduleur qui parle, pas le rendement.
    m.mettre_a_jour(Releve({"gridInputPower": 60}, [{"state": 1, "power": 21}]), T0)
    assert m.rendement_charge is None
    # Rampe : AC déjà monté, DC pas encore -> 35 %, écarté
    m.mettre_a_jour(Releve({"gridInputPower": 2000}, [{"state": 1, "power": 700}]),
                    T0 + timedelta(seconds=5))
    assert m.rendement_charge is None
    # Plus de 100 % : instants décalés, écarté aussi
    m.mettre_a_jour(Releve({"outputHomePower": 900}, [{"state": 2, "power": 800}]),
                    T0 + timedelta(seconds=10))
    assert m.rendement_decharge is None
    # La reprise du YAML ne reconduit pas une valeur aberrante
    m.amorcer({"rendement_charge": "35.5", "rendement_decharge": "89.3"})
    assert m.rendement_charge is None and m.rendement_decharge == 89.3


def test_moyenne_7_jours_oublie_les_vieilles_mesures():
    m = memoire.Memoire()
    m.mettre_a_jour(Releve({"gridInputPower": 1000}, [{"state": 1, "power": 800}]), T0)
    m.mettre_a_jour(Releve({"gridInputPower": 1000}, [{"state": 1, "power": 960}]),
                    T0 + timedelta(days=8))
    assert m.efficacite_charge_7j == 96.0


def _cycle_de_charge(m, capacite_reelle_wh, soc_depart, soc_arrivee, depart=T0):
    """Charge à 2000 W DC ; le SOC suit l'énergie réellement stockée."""
    tension, courant = 5000, 400          # 50,00 V et 40,0 A -> 2000 W
    pas_s = 5
    energie_par_pas = 2000 * pas_s / 3600
    nrj, t = 0.0, depart
    while True:
        soc = soc_depart + nrj / capacite_reelle_wh * 100
        pack = {**PACK_8KWH, "socLevel": round(soc, 1), "totalVol": tension, "batcur": courant}
        m.mettre_a_jour(Releve({"electricLevel": soc}, [pack]), t)
        if soc >= soc_arrivee:
            return t
        nrj += energie_par_pas
        t += timedelta(seconds=pas_s)


def test_sante_mesuree_sur_un_cycle():
    m = memoire.Memoire()
    # Pack 8 kWh nominal qui n'en stocke plus que 7600 Wh : 95 %
    _cycle_de_charge(m, 7600, 20, 50)
    cap = m.packs[0]["capacite"]
    assert abs(cap - 7600) / 7600 < 0.02, cap
    assert abs(m.sante(0, 8.0) - 95) < 2
    # Le repère est replacé dès la mesure faite, à 45 % (20 + 25) : la
    # mesure suivante est déjà engagée de 5 points sur 25.
    assert abs(m.packs[0]["ancre_soc"] - 45) < 0.5, m.packs[0]["ancre_soc"]
    assert m.progression_sante([{"socLevel": 50}]) == 20


def test_sante_rejette_une_mesure_implausible():
    m = memoire.Memoire()
    m.packs[0]["capacite"] = 7600
    # Repère faussé : énergie qui n'a pas bougé alors que le SOC a gagné 30 points
    m.packs[0].update(ancre_soc=20, ancre_energie=0)
    pack = {**PACK_8KWH, "socLevel": 50, "totalVol": 0, "batcur": 0}
    m.mettre_a_jour(Releve({}, [pack]), T0)
    assert m.packs[0]["capacite"] == 7600             # mesure rejetée
    assert m.packs[0]["ancre_soc"] == 50              # repère tout de même replacé


def test_sante_lissee_entre_deux_cycles():
    m = memoire.Memoire()
    fin = _cycle_de_charge(m, 7600, 20, 50)
    _cycle_de_charge(m, 7000, 50, 80, depart=fin + timedelta(seconds=5))
    # 70 % de l'ancienne estimation, 30 % de la nouvelle
    attendu = 7600 * 0.7 + 7000 * 0.3
    assert abs(m.packs[0]["capacite"] - attendu) / attendu < 0.02, m.packs[0]["capacite"]


def test_reinitialisation_de_la_sante():
    m = memoire.Memoire()
    _cycle_de_charge(m, 7600, 20, 50)
    m.reinitialiser_sante()
    assert m.packs[0]["capacite"] == 0 and m.packs[0]["ancre_soc"] == -1
    assert m.sante(0, 8.0) is None


def test_persistance():
    m = memoire.Memoire()
    _cycle_de_charge(m, 7600, 20, 50)
    copie = memoire.Memoire.depuis_dict(m.en_dict())
    assert copie.en_dict() == m.en_dict()
    # Le relevé précédent n'est PAS restauré : pas d'intégration à travers
    # un redémarrage.
    assert copie._prec is None


def test_reprise_des_valeurs_yaml():
    m = memoire.Memoire()
    reprises = m.amorcer({
        "energie_chargee": "152.437", "energie_pv": "1203.5", "energie_dechargee": "unknown",
        "derniere_calibration": "2026-05-01T12:00:00+00:00",
        "pack_1_capacite": "7712", "pack_1_ancre_soc": "35.0", "pack_1_energie_dc": "-1532.4",
    })
    assert m.energie_chargee == 152.437 and m.energie_pv == 1203.5
    assert m.energie_dechargee == 0                    # valeur illisible ignorée
    assert m.packs[0]["capacite"] == 7712 and m.packs[0]["energie_dc"] == -1532.4
    assert "energie_dechargee" not in reprises and m.amorcee
    # Le compteur repris continue de monter, sans repartir de zéro
    _rejouer(m, [Releve({"outputPackPower": 1000})] * 721)
    assert abs(m.energie_chargee - 153.437) < 0.001


def test_puissance_dc_signee():
    assert memoire.puissance_dc_pack({"totalVol": 5000, "batcur": 400}) == 2000.0
    # 65534 = −0,2 A : décharge
    assert memoire.puissance_dc_pack({"totalVol": 2624, "batcur": 65534}) == -5.2


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
        except Exception as err:  # noqa: BLE001
            echecs += 1
            print(f"  ERREUR {t.__name__}  {type(err).__name__}: {err}")
    print(f"\nRESULTAT : {len(tests) - echecs}/{len(tests)} tests au vert")
    sys.exit(1 if echecs else 0)
