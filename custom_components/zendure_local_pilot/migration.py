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
PLATEFORMES_YAML = ("template", "rest", "integration", "utility_meter",
                    "history_stats", "statistics")


def entites_revendiquees(nb_packs: int) -> set[str]:
    """entity_id que l'intégration va créer.

    Seuls ceux-là doivent être libérés. Les entités YAML que l'intégration ne
    reprend pas (compteurs d'énergie, santé des packs…) doivent rester
    intactes : l'utilisateur peut les garder en YAML à côté de l'intégration.
    """
    # Import local : ces modules dépendent des plateformes de Home Assistant.
    from .binary_sensor import BINAIRES
    from .number import NOMBRES_BATTERIE, NOMBRES_SHELLY, _nombres_kvs
    from .select import CHOIX
    from .sensor import CAPTEURS, _capteurs_pack

    capteurs = list(CAPTEURS)
    for n in range(1, nb_packs + 1):
        capteurs.extend(_capteurs_pack(n))
    ids = {f"sensor.{PREFIXE}_{d.key}" for d in capteurs}
    ids |= {f"binary_sensor.{PREFIXE}_{d.key}" for d in BINAIRES}
    ids |= {f"number.{PREFIXE}_{d.key}"
            for d in (*NOMBRES_BATTERIE, *NOMBRES_SHELLY, *_nombres_kvs())}
    ids |= {f"select.{PREFIXE}_{d.key}" for d in CHOIX}
    from .button import BOUTONS
    from .switch import AFFICHAGE
    from .update import CLE as CLE_MAJ

    ids |= {f"button.{PREFIXE}_{d.key}" for d in BOUTONS}

    ids.add(f"switch.{PREFIXE}_regulation")
    ids |= {f"switch.{PREFIXE}_{a[0]}" for a in AFFICHAGE}
    ids.add(f"update.{PREFIXE}_{CLE_MAJ}")
    return ids


async def liberer_anciennes_entites(hass: HomeAssistant, nb_packs: int) -> list[str]:
    """Supprime les entrées de registre YAML dont on reprend l'identifiant."""
    registre = er.async_get(hass)
    revendiques = entites_revendiquees(nb_packs)
    liberees: list[str] = []
    for entree in list(registre.entities.values()):
        if entree.platform in PLATEFORMES_YAML and entree.entity_id in revendiques:
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
