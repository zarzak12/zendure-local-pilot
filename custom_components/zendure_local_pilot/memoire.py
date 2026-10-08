"""Grandeurs à mémoire : compteurs, statistiques du jour, santé des packs.

L'appareil ne fournit aucun compteur cumulé, aucune statistique et aucun
indicateur de santé. La version YAML les reconstruisait avec les plateformes
« integration », « utility_meter », « history_stats », « statistics » et une
automatisation. Tout est réuni ici, en logique pure et sans dépendance à Home
Assistant, pour pouvoir le tester sur n'importe quelle machine.

L'état se sérialise en dictionnaire (en_dict / depuis_dict) : le coordinateur
le confie au stockage de Home Assistant, et rien n'est perdu au redémarrage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .calculs import (
    capacite_pack,
    efficacite_charge,
    efficacite_decharge,
    puissance_batterie_nette,
    rendement_plausible,
)

NB_PACKS_MAX = 4

# Au-delà de cet écart entre deux relevés (HA arrêté, batterie muette), la
# puissance de l'intervalle est inconnue : on ne l'intègre pas plutôt que
# d'inventer de l'énergie.
ECART_MAX_S = 120

# Moyennes « 24 h » des rendements : sur 7 jours, comme la version YAML (la
# mesure n'est possible qu'en charge réseau sans PV, une fenêtre de 24 h
# restait souvent vide).
FENETRE_RENDEMENT_S = 7 * 86400

# Santé : il faut avoir parcouru au moins 25 points de SOC depuis le repère.
DELTA_SOC_SANTE = 25
PLAUSIBLE_MIN, PLAUSIBLE_MAX = 0.4, 1.3


def _f(source: dict[str, Any], cle: str) -> float:
    try:
        return float(source.get(cle, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def puissance_dc_pack(pack: dict[str, Any]) -> float:
    """Puissance DC signée d'un pack, + charge / − décharge.

    packData.power n'est qu'une magnitude : le sens vient du courant, un
    entier 16 bits non signé (65534 = −0,2 A).
    """
    c = _f(pack, "batcur")
    courant = ((c - 65536) if c > 32767 else c) / 10
    return round(_f(pack, "totalVol") / 100 * courant, 1)


def _pack_neuf() -> dict[str, float]:
    return {"energie_dc": 0.0, "ancre_soc": -1.0, "ancre_energie": 0.0, "capacite": 0.0}


class Memoire:
    """État cumulé de l'installation, mis à jour à chaque relevé."""

    def __init__(self) -> None:
        self.energie_chargee = 0.0      # kWh, côté AC du pack (outputPackPower)
        self.energie_dechargee = 0.0    # kWh (packInputPower)
        self.energie_pv = 0.0           # kWh (solarInputPower)
        self.pv_jour = 0.0              # kWh depuis minuit
        self.jour = ""                  # date locale du compteur du jour
        self.commutations_charge = 0
        self.commutations_decharge = 0
        # Bascules du RELAIS charge <-> décharge (changements d'acMode). À ne
        # pas confondre avec les commutations, qui comptent aussi chaque
        # reprise depuis le repos, sans que le relais bouge.
        self.bascules_relais = 0
        self.zero_soutirage_s = 0.0
        self.rendement_charge: float | None = None
        self.rendement_decharge: float | None = None
        self.seaux_charge: dict[str, list[float]] = {}     # heure -> [somme, nombre]
        self.seaux_decharge: dict[str, list[float]] = {}
        self.derniere_calibration: str | None = None
        self.packs = [_pack_neuf() for _ in range(NB_PACKS_MAX)]
        self.amorcee = False            # reprise des valeurs YAML déjà faite
        # Relevé précédent : volontairement NON sauvegardé, pour ne jamais
        # intégrer à travers un redémarrage de Home Assistant.
        self._prec: dict[str, Any] | None = None
        self._prec_reseau: tuple[float, bool] | None = None
        self._soc_prec: float | None = None
        self._etat_prec: str | None = None
        self._ac_mode_prec: int | None = None

    # -- persistance ---------------------------------------------------------

    _CHAMPS = ("energie_chargee", "energie_dechargee", "energie_pv", "pv_jour", "jour",
               "commutations_charge", "commutations_decharge", "bascules_relais",
               "zero_soutirage_s",
               "rendement_charge", "rendement_decharge", "seaux_charge", "seaux_decharge",
               "derniere_calibration", "packs", "amorcee")

    def en_dict(self) -> dict[str, Any]:
        return {cle: getattr(self, cle) for cle in self._CHAMPS}

    @classmethod
    def depuis_dict(cls, donnees: dict[str, Any] | None) -> "Memoire":
        m = cls()
        for cle in cls._CHAMPS:
            if donnees and cle in donnees:
                setattr(m, cle, donnees[cle])
        while len(m.packs) < NB_PACKS_MAX:
            m.packs.append(_pack_neuf())
        return m

    def amorcer(self, valeurs: dict[str, Any]) -> list[str]:
        """Reprend les dernières valeurs de la version YAML.

        Sans cela, un compteur d'énergie repartirait de zéro : pour un
        capteur « total », Home Assistant y verrait une chute de plusieurs
        centaines de kWh, et le tableau Énergie un trou impossible à combler.
        Retourne les grandeurs effectivement reprises.
        """
        reprises = []
        for cle in ("energie_chargee", "energie_dechargee", "energie_pv",
                    "rendement_charge", "rendement_decharge"):
            v = _nombre(valeurs.get(cle))
            # Un rendement mesuré à trop faible puissance par la version YAML
            # (35 % en charge, par exemple) ne doit pas être reconduit.
            if v is not None and (not cle.startswith("rendement") or rendement_plausible(v)):
                setattr(self, cle, v)
                reprises.append(cle)
        if isinstance(valeurs.get("derniere_calibration"), str):
            self.derniere_calibration = valeurs["derniere_calibration"]
            reprises.append("derniere_calibration")
        for i, pack in enumerate(self.packs):
            for champ in ("energie_dc", "ancre_soc", "ancre_energie", "capacite"):
                v = _nombre(valeurs.get(f"pack_{i + 1}_{champ}"))
                if v is not None:
                    pack[champ] = v
                    reprises.append(f"pack_{i + 1}_{champ}")
        self.amorcee = True
        return reprises

    # -- mise à jour ---------------------------------------------------------

    def mettre_a_jour(self, donnees, maintenant: datetime) -> None:
        """Intègre un relevé du coordinateur (objet Donnees)."""
        t = maintenant.timestamp()
        jour = maintenant.date().isoformat()
        if jour != self.jour:
            self.jour = jour
            self.pv_jour = 0.0
            self.commutations_charge = self.commutations_decharge = 0
            self.bascules_relais = 0
            self.zero_soutirage_s = 0.0

        self._zero_soutirage(donnees.reseau, t)

        if not donnees.batterie_joignable:
            self._prec = None
            return

        p = donnees.proprietes
        packs = donnees.packs
        releve = {
            "t": t,
            "charge": _f(p, "outputPackPower"),
            "decharge": _f(p, "packInputPower"),
            "pv": _f(p, "solarInputPower"),
            "dc": [puissance_dc_pack(pk) for pk in packs[:NB_PACKS_MAX]],
        }
        prec = self._prec
        if prec is not None and 0 < t - prec["t"] <= ECART_MAX_S:
            dt_h = (t - prec["t"]) / 3600
            # Méthode « gauche », comme la version YAML : la puissance du
            # relevé précédent vaut pour tout l'intervalle.
            self.energie_chargee += prec["charge"] * dt_h / 1000
            self.energie_dechargee += prec["decharge"] * dt_h / 1000
            gain_pv = prec["pv"] * dt_h / 1000
            self.energie_pv += gain_pv
            self.pv_jour += gain_pv
            # Packs : trapèzes, comme la version YAML.
            for i in range(min(len(prec["dc"]), len(releve["dc"]))):
                self.packs[i]["energie_dc"] += (prec["dc"][i] + releve["dc"][i]) / 2 * dt_h
        self._prec = releve

        self._rendements(p, packs, t)
        self._calibration(_f(p, "electricLevel"), maintenant)
        self._commutations(-puissance_batterie_nette(p))
        self._bascules_relais(p.get("acMode"))
        self._sante(packs)

    def _zero_soutirage(self, reseau: float | None, t: float) -> None:
        # Le temps est attribué à l'état du relevé PRÉCÉDENT, comme history_stats.
        if self._prec_reseau is not None:
            t0, zero = self._prec_reseau
            if zero and 0 < t - t0 <= ECART_MAX_S:
                self.zero_soutirage_s += t - t0
        self._prec_reseau = (t, reseau <= 0) if reseau is not None else None

    def _rendements(self, p: dict[str, Any], packs: list[dict[str, Any]], t: float) -> None:
        heure = str(int(t // 3600))
        for valeur, attribut, seaux in (
            (efficacite_charge(p, packs), "rendement_charge", self.seaux_charge),
            (efficacite_decharge(p, packs), "rendement_decharge", self.seaux_decharge),
        ):
            # Un rendement réel n'est jamais nul : un 0 transitoire se figerait
            # sinon en se faisant passer pour une mesure.
            if valeur is None or valeur <= 0:
                continue
            setattr(self, attribut, valeur)
            seau = seaux.setdefault(heure, [0.0, 0])
            seau[0] += valeur
            seau[1] += 1
        limite = (t - FENETRE_RENDEMENT_S) // 3600
        for seaux in (self.seaux_charge, self.seaux_decharge):
            for h in [h for h in seaux if int(h) < limite]:
                del seaux[h]

    def _calibration(self, soc: float, maintenant: datetime) -> None:
        # Franchissement de 99 % vers le haut, comme le déclencheur YAML.
        if self._soc_prec is not None and self._soc_prec <= 99 < soc:
            self.derniere_calibration = maintenant.isoformat()
        self._soc_prec = soc

    def _commutations(self, puissance: float) -> None:
        etat = "Charge" if puissance > 20 else "Décharge" if puissance < -20 else "Veille"
        if self._etat_prec is not None and etat != self._etat_prec:
            if etat == "Charge":
                self.commutations_charge += 1
            elif etat == "Décharge":
                self.commutations_decharge += 1
        self._etat_prec = etat

    def _bascules_relais(self, ac_mode: Any) -> None:
        # Seules 1 (charge) et 2 (décharge) désignent un sens du relais ; une
        # valeur absente ou autre ne doit ni compter ni effacer la précédente.
        if ac_mode not in (1, 2):
            return
        if self._ac_mode_prec is not None and ac_mode != self._ac_mode_prec:
            self.bascules_relais += 1
        self._ac_mode_prec = ac_mode

    def _sante(self, packs: list[dict[str, Any]]) -> None:
        """Capacité réelle = énergie DC échangée ÷ variation de SOC × 100."""
        for i, pk in enumerate(packs[:NB_PACKS_MAX]):
            if "socLevel" not in pk:
                continue
            etat = self.packs[i]
            soc = _f(pk, "socLevel")
            nrj = etat["energie_dc"]
            if etat["ancre_soc"] < 0:
                etat["ancre_soc"], etat["ancre_energie"] = soc, nrj
                continue
            delta_soc = soc - etat["ancre_soc"]
            if abs(delta_soc) < DELTA_SOC_SANTE:
                continue
            cap = (nrj - etat["ancre_energie"]) / delta_soc * 100
            nom = capacite_pack(pk.get("sn"), pk.get("packType")) * 1000
            if nom > 0 and nom * PLAUSIBLE_MIN < cap < nom * PLAUSIBLE_MAX:
                # Premier passage : valeur brute ; ensuite lissage 70/30.
                etat["capacite"] = round(
                    cap if etat["capacite"] <= 0 else etat["capacite"] * 0.7 + cap * 0.3)
            # Repère replacé dans tous les cas, même mesure rejetée, sinon on
            # resterait bloqué sur un repère faussé.
            etat["ancre_soc"], etat["ancre_energie"] = soc, nrj

    def reinitialiser_sante(self) -> None:
        for etat in self.packs:
            etat["capacite"] = 0.0
            etat["ancre_soc"] = -1.0

    # -- lectures ------------------------------------------------------------

    @property
    def rendement_global(self) -> float | None:
        if self.energie_chargee <= 0.1:
            return None
        return round(self.energie_dechargee / self.energie_chargee * 100, 1)

    @staticmethod
    def _moyenne(seaux: dict[str, list[float]]) -> float | None:
        somme = sum(s for s, _ in seaux.values())
        nombre = sum(n for _, n in seaux.values())
        return round(somme / nombre, 1) if nombre else None

    @property
    def efficacite_charge_7j(self) -> float | None:
        return self._moyenne(self.seaux_charge)

    @property
    def efficacite_decharge_7j(self) -> float | None:
        return self._moyenne(self.seaux_decharge)

    def jours_depuis_calibration(self, maintenant: datetime) -> int | None:
        if not self.derniere_calibration:
            return None
        try:
            depuis = datetime.fromisoformat(self.derniere_calibration)
        except ValueError:
            return None
        return round((maintenant - depuis).total_seconds() / 86400)

    def sante(self, i: int, nominal_kwh: float) -> float | None:
        cap = self.packs[i]["capacite"]
        if cap <= 0 or nominal_kwh <= 0:
            return None
        return round(cap / (nominal_kwh * 1000) * 100, 1)

    def progression_sante(self, packs: list[dict[str, Any]]) -> float:
        """Avancement de la mesure en cours, le plus avancé des packs."""
        meilleur = 0.0
        for i, pk in enumerate(packs[:NB_PACKS_MAX]):
            ancre = self.packs[i]["ancre_soc"]
            if ancre >= 0 and "socLevel" in pk:
                meilleur = max(meilleur, min(abs(_f(pk, "socLevel") - ancre) / DELTA_SOC_SANTE * 100, 100))
        return round(meilleur)


def _nombre(valeur: Any) -> float | None:
    try:
        v = float(valeur)
    except (TypeError, ValueError):
        return None
    return v if v == v else None   # écarte NaN
