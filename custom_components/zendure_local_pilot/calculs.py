"""Logique métier pure, sans dépendance à Home Assistant.

Tout ce qui est calculable à partir du rapport de la batterie vit ici, et
nulle part ailleurs : ces fonctions se testent sans instance Home Assistant,
ce qui est précieux pour vérifier le portage depuis les modèles Jinja.
"""

from __future__ import annotations

from typing import Any

from .const import CAPACITE_REPLI_PAR_TYPE, NOMS_MODELES


def nom_modele(produit: str | None) -> str:
    """Libellé lisible du modèle, à partir du champ « product »."""
    p = (produit or "").strip()
    if not p or p in ("unknown", "unavailable", "none"):
        return "SolarFlow"
    if p in NOMS_MODELES:
        return NOMS_MODELES[p]
    # Modèle inconnu : on dégrade proprement plutôt que d'afficher du jargon.
    if p.startswith("solarFlow"):
        return "SolarFlow " + p[len("solarFlow"):]
    return p


def capacite_pack(sn: str | None, pack_type: Any) -> float:
    """Capacité nominale d'un pack, en kWh.

    Résolue par le PRÉFIXE DU NUMÉRO DE SÉRIE, comme l'intégration officielle.
    La documentation zenSDK classe packType en « Reserved » : la même valeur y
    désigne des packs différents selon le modèle. Cas emblématique, packType 70
    vaut 8 kWh (pack interne I8000 des SolarFlow Mix) alors que des tables
    communautaires lui prêtent 1,92 kWh. packType ne sert donc qu'à départager
    les séries B, et de repli quand le préfixe est inconnu.
    """
    serie = (sn or "").upper()
    try:
        type_ = int(pack_type)
    except (TypeError, ValueError):
        type_ = 0

    p0 = serie[0:1]
    p3 = serie[3:4]

    if p0 == "A":
        return 2.40 if p3 == "3" else 0.96
    if p0 == "B":
        return 8.00 if type_ == 70 else 0.96
    if p0 == "C":
        return 1.92
    if p0 in ("F", "G"):
        return 2.88
    if p0 == "J":
        return 2.40
    return CAPACITE_REPLI_PAR_TYPE.get(type_, 0.0)


def echelle_soc(proprietes: dict[str, Any]) -> int:
    """Facteur de division des bornes SOC : 10 pour des pour-mille, 1 sinon.

    Tous les firmwares n'emploient pas la même échelle. La plupart renvoient
    des pour-mille (socSet 1000 = 100 %), certains des pourcentages bruts.
    socSet, documenté entre 70 et 100 %, sert d'indicateur : au-delà de 100,
    on est forcément en pour-mille. Se tromper d'échelle afficherait 10 % au
    lieu de 100 %, et surtout écrirait une consigne aberrante.
    """
    try:
        soc_set = int(proprietes.get("socSet", 0))
    except (TypeError, ValueError):
        return 10
    return 10 if soc_set > 100 else 1


def limites_materielles(proprietes: dict[str, Any]) -> tuple[int, int]:
    """Plafonds de décharge et de charge annoncés par la batterie, en W.

    Retourne (0, 0) quand la batterie ne les annonce pas : l'appelant ne doit
    alors rien plafonner, plutôt que d'inventer une limite.
    """
    def lire(cle: str) -> int:
        try:
            v = int(proprietes.get(cle, 0))
        except (TypeError, ValueError):
            return 0
        # Une valeur aberrante vaut mieux ignorée qu'appliquée : elle
        # brimerait la batterie ou, pire, lèverait tout plafond.
        return v if 100 <= v <= 10000 else 0

    return lire("inverseMaxPower"), lire("chargeMaxLimit")


def puissance_batterie_nette(proprietes: dict[str, Any]) -> int:
    """Positif en décharge vers la maison, négatif en charge."""
    def i(cle: str) -> int:
        try:
            return int(proprietes.get(cle, 0) or 0)
        except (TypeError, ValueError):
            return 0

    return i("packInputPower") - i("outputPackPower")


def capacite_totale(packs: list[dict[str, Any]]) -> float:
    """Somme des capacités nominales des packs présents, en kWh."""
    return round(
        sum(capacite_pack(p.get("sn"), p.get("packType")) for p in packs), 2
    )
