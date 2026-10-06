"""Vérifie que services.py et services.yaml racontent la même histoire.

Un champ renommé dans le schéma mais pas dans services.yaml donne une
interface graphique qui propose un champ refusé à l'exécution, et un service
déclaré d'un seul côté n'apparaît pas là où on le cherche. Ces divergences ne
se voient qu'à l'usage ; ce test les attrape à froid, par lecture de l'arbre
syntaxique (voluptuous n'est pas installé hors de Home Assistant).

    python tests/test_services.py
"""

from __future__ import annotations

import ast
import os
import sys

import yaml

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "custom_components", "zendure_local_pilot")

ARBRE = ast.parse(open(os.path.join(DOSSIER, "services.py"), encoding="utf-8").read())
with open(os.path.join(DOSSIER, "services.yaml"), encoding="utf-8") as _f:
    DECLARE = yaml.safe_load(_f)


def _constantes() -> dict[str, str]:
    """SERVICE_PUISSANCE -> « set_power »."""
    valeurs = {}
    for noeud in ARBRE.body:
        if isinstance(noeud, ast.Assign) and len(noeud.targets) == 1:
            cible = noeud.targets[0]
            if isinstance(cible, ast.Name) and isinstance(noeud.value, ast.Constant):
                valeurs[cible.id] = noeud.value.value
    return valeurs


def _champs_directs(noeud: ast.AST) -> set[str]:
    champs = set()
    for interne in ast.walk(noeud):
        if (isinstance(interne, ast.Call)
                and isinstance(interne.func, ast.Attribute)
                and interne.func.attr in ("Required", "Optional")
                and interne.args
                and isinstance(interne.args[0], ast.Constant)):
            champs.add(interne.args[0].value)
    return champs


def _dictionnaires_du_module() -> dict[str, set[str]]:
    """Dictionnaires de champs communs, repris par dépliage (**_BASE)."""
    resultat = {}
    for noeud in ARBRE.body:
        if (isinstance(noeud, ast.Assign) and len(noeud.targets) == 1
                and isinstance(noeud.targets[0], ast.Name)
                and isinstance(noeud.value, ast.Dict)):
            resultat[noeud.targets[0].id] = _champs_directs(noeud.value)
    return resultat


def _champs_des_schemas() -> dict[str, set[str]]:
    """SCHEMA_PUISSANCE -> {« power », « entry_id »}.

    Le dépliage ``**_BASE`` doit être suivi, sans quoi les champs communs
    passeraient pour absents du schéma.
    """
    communs = _dictionnaires_du_module()
    schemas: dict[str, set[str]] = {}
    for noeud in ARBRE.body:
        if not (isinstance(noeud, ast.Assign) and len(noeud.targets) == 1):
            continue
        cible = noeud.targets[0]
        if not (isinstance(cible, ast.Name) and cible.id.startswith("SCHEMA_")):
            continue
        champs = _champs_directs(noeud.value)
        for interne in ast.walk(noeud.value):
            if isinstance(interne, ast.Dict):
                for cle, valeur in zip(interne.keys, interne.values):
                    if cle is None and isinstance(valeur, ast.Name):
                        champs |= communs.get(valeur.id, set())
        schemas[cible.id] = champs
    return schemas


def _enregistrements() -> dict[str, str]:
    """« set_power » -> « SCHEMA_PUISSANCE »."""
    constantes = _constantes()
    resultat = {}
    for noeud in ast.walk(ARBRE):
        if not (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Attribute)
                and noeud.func.attr == "async_register"):
            continue
        if len(noeud.args) < 2 or not isinstance(noeud.args[1], ast.Name):
            continue
        nom = constantes.get(noeud.args[1].id)
        schema = next(
            (kw.value.id for kw in noeud.keywords
             if kw.arg == "schema" and isinstance(kw.value, ast.Name)),
            None,
        )
        if nom:
            resultat[nom] = schema
    return resultat


def test_services_declares_et_enregistres_concordent():
    enregistres = set(_enregistrements())
    declares = set(DECLARE)
    assert enregistres == declares, (
        f"enregistrés sans fiche : {enregistres - declares} ; "
        f"fiches orphelines : {declares - enregistres}"
    )


def test_chaque_service_a_un_schema():
    for nom, schema in _enregistrements().items():
        assert schema, f"{nom} est enregistré sans schéma de validation"


def test_les_champs_concordent():
    schemas = _champs_des_schemas()
    for nom, schema in _enregistrements().items():
        attendus = schemas[schema]
        proposes = set((DECLARE[nom] or {}).get("fields") or {})
        assert attendus == proposes, (
            f"{nom} : champs acceptés {sorted(attendus)} "
            f"mais proposés {sorted(proposes)}"
        )


def test_les_champs_requis_le_sont_des_deux_cotes():
    """Un champ requis seulement côté schéma produit une erreur à l'exécution
    là où l'interface laissait croire qu'il était facultatif."""
    for noeud in ARBRE.body:
        if not (isinstance(noeud, ast.Assign) and len(noeud.targets) == 1):
            continue
        cible = noeud.targets[0]
        if not (isinstance(cible, ast.Name) and cible.id.startswith("SCHEMA_")):
            continue
        requis = set()
        for interne in ast.walk(noeud.value):
            if (isinstance(interne, ast.Call)
                    and isinstance(interne.func, ast.Attribute)
                    and interne.func.attr == "Required"
                    and interne.args
                    and isinstance(interne.args[0], ast.Constant)):
                requis.add(interne.args[0].value)
        for nom, schema in _enregistrements().items():
            if schema != cible.id:
                continue
            champs = (DECLARE[nom] or {}).get("fields") or {}
            for champ in requis:
                assert champs.get(champ, {}).get("required") is True, (
                    f"{nom}.{champ} est requis par le schéma mais pas annoncé "
                    "comme tel dans services.yaml"
                )


def test_chaque_service_est_decrit():
    """Depuis 2024, Home Assistant attend les libellés dans strings.json et
    non dans services.yaml : des libellés restés dans le YAML n'apparaîtraient
    nulle part dans l'interface."""
    import json
    for langue in ("fr", "en"):
        chemin = os.path.join(DOSSIER, "translations", f"{langue}.json")
        with open(chemin, encoding="utf-8") as fichier:
            traductions = json.load(fichier)
        decrits = traductions.get("services", {})
        for nom in DECLARE:
            assert nom in decrits, f"{langue} : {nom} n'est pas décrit"
            fiche = decrits[nom]
            assert fiche.get("name"), f"{langue}/{nom} : libellé absent"
            assert fiche.get("description"), f"{langue}/{nom} : description absente"
            champs = set((DECLARE[nom] or {}).get("fields") or {})
            manquants = champs - set(fiche.get("fields", {}))
            assert not manquants, (
                f"{langue}/{nom} : champs non décrits {sorted(manquants)}"
            )

    for nom, fiche in DECLARE.items():
        assert "name" not in (fiche or {}), (
            f"{nom} : le libellé doit vivre dans strings.json, pas services.yaml"
        )


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
    print(f"\n{len(_enregistrements())} services declares")
    print(f"RESULTAT : {len(tests) - echecs}/{len(tests)} tests au vert")
    sys.exit(1 if echecs else 0)
