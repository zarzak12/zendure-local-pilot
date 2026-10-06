"""Reprise des entités créées par l'ancienne version YAML.

Pourquoi c'est nécessaire : une entrée du registre est identifiée par le
triplet (domaine, intégration, unique_id). Les entités actuelles appartiennent
aux intégrations « template », « rest », « integration » et « utility_meter ».
Une nouvelle intégration ne peut donc pas hériter de ces entrées : Home
Assistant verrait des entités différentes, constaterait que l'entity_id est
déjà pris, et ajouterait un suffixe « _2 » à tout. Historique, statistiques
long terme, automatisations et dashboard seraient perdus d'un coup.

La parade : libérer les anciennes entrées AVANT de créer les nôtres, puis
revendiquer exactement les mêmes entity_id. L'historique et les statistiques
sont stockés par entity_id, pas par entrée de registre : ils survivent.

Condition impérative : les packages YAML doivent avoir été retirés. S'ils sont
encore chargés, l'intégration « template » recréera ses entités aussitôt et
reprendra les identifiants. On le détecte après coup et on le signale.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

from .const import DOMAIN, PREFIXE

_LOGGER = logging.getLogger(__name__)

# Intégrations ayant pu créer les entités de la version YAML.
PLATEFORMES_YAML = ("template", "rest", "integration", "utility_meter")


def _concerne(entree: er.RegistryEntry) -> bool:
    objet = entree.entity_id.split(".", 1)[-1]
    return entree.platform in PLATEFORMES_YAML and objet.startswith(PREFIXE)


async def liberer_anciennes_entites(hass: HomeAssistant) -> list[str]:
    """Supprime les entrées de registre de la version YAML. Retourne leurs id."""
    registre = er.async_get(hass)
    liberees: list[str] = []
    for entree in list(registre.entities.values()):
        if _concerne(entree):
            liberees.append(entree.entity_id)
            registre.async_remove(entree.entity_id)

    if liberees:
        _LOGGER.info(
            "migration : %d entity_id libérés par l'intégration %s",
            len(liberees), DOMAIN,
        )
    return liberees


def verifier_migration(hass: HomeAssistant, entry_id: str) -> list[str]:
    """Repère les entités ayant dû se rabattre sur un suffixe « _2 ».

    C'est le symptôme d'un package YAML encore chargé : il a repris
    l'identifiant d'origine, et nos entités se sont vu attribuer un nom de
    repli. Les graphiques de l'utilisateur pointeraient alors vers des
    entités figées.
    """
    registre = er.async_get(hass)
    boiteux = [
        e.entity_id
        for e in registre.entities.values()
        if e.config_entry_id == entry_id and e.entity_id.endswith("_2")
    ]
    if boiteux:
        _LOGGER.warning(
            "migration incomplète : %d entités ont un identifiant de repli (%s…). "
            "Les packages YAML sont probablement encore chargés.",
            len(boiteux), boiteux[0],
        )
        async_create_issue(
            hass,
            DOMAIN,
            "packages_yaml_encore_charges",
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="packages_yaml_encore_charges",
            translation_placeholders={"nombre": str(len(boiteux))},
        )
    return boiteux
