"""Constantes partagées de l'intégration Zendure Local Pilot."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "zendure_local_pilot"

# Préfixe HISTORIQUE des entity_id. Il ne doit jamais changer, même pour un
# possesseur de SolarFlow 2400 : les utilisateurs venant de la version YAML
# perdraient leur historique, leurs statistiques long terme, leurs
# automatisations et leur dashboard. Ce n'est qu'un identifiant.
PREFIXE: Final = "zendure_solarflow4000mix"

CONF_SHELLY_HOST: Final = "shelly_host"
CONF_EM_CANAL: Final = "em_canal"
CONF_NB_PACKS: Final = "nb_packs"
CONF_MIGRER: Final = "migrer"

DEFAUT_NB_PACKS: Final = 4

# Cadence de sondage. La régulation vit dans le Shelly : ce sondage ne sert
# qu'à l'affichage, inutile donc d'être agressif avec le serveur HTTP de la
# batterie, qui marque de longues pauses quand plusieurs clients l'interrogent.
INTERVALLE_SONDAGE: Final = 5
DELAI_HTTP: Final = 20

# ---------------------------------------------------------------------------
# Réglages avancés, stockés dans le KVS du Shelly (clé -> (mini, maxi, pas))
# ---------------------------------------------------------------------------
# zendure_ip et zendure_sn sont renseignés par le script lui-même lors de la
# découverte de la batterie : ils sont exposés en lecture seule.
KVS_REGLAGES: Final = {
    "zendure_em": (0, 2, 1),
    # Jamais sous 1000 ms : en dessous, les écritures s'empilent plus vite que
    # la batterie ne les applique et la régulation se met à osciller.
    "zendure_period": (1000, 10000, 100),
    "zendure_tick": (100, 2000, 50),
    "zendure_gain": (0.1, 1, 0.05),
    "zendure_dead": (0, 200, 5),
    "zendure_hyst": (0, 200, 5),
    "zendure_wake": (0, 500, 10),
    "zendure_flip": (0, 300, 1),
    "zendure_flipw": (0, 1000, 10),
    "zendure_smooth": (0, 0.9, 0.1),
}

KVS_LECTURE_SEULE: Final = ("zendure_ip", "zendure_sn")

# ---------------------------------------------------------------------------
# Composants virtuels du Shelly (réglages courants de la régulation)
# ---------------------------------------------------------------------------
# Les exposer ici, en plus de l'intégration Shelly officielle, n'est pas une
# redondance gratuite : l'intégration Shelly nomme ses entités d'après
# l'identifiant matériel (shellypro3em_a1b2c3...), qui diffère d'une
# installation à l'autre. C'est précisément ce qui obligeait jusqu'ici à
# personnaliser le dashboard. Sous des identifiants stables, le dashboard
# devient universel.
VC_MODE: Final = "enum:200"
VC_DECHARGE_MAX: Final = "number:200"
VC_CHARGE_MAX: Final = "number:201"
VC_CONSIGNE_MANUELLE: Final = "number:202"
VC_BUFFER: Final = "number:203"
VC_DELAI_VEILLE: Final = "number:204"
VC_EN_VEILLE: Final = "boolean:200"
VC_BUFFER_CHARGE: Final = "number:205"

# Doivent être EXACTEMENT les options de l'enum créé par le script (enum:200) :
# une option inconnue du script serait refusée par le Shelly, et un mode du
# script absent d'ici s'afficherait comme inconnu. Vérifié par les tests.
MODES: Final = ["arret", "autoconso", "charge_seule", "decharge_seule", "manuel"]

# Repli employé tant que la batterie n'a pas annoncé ses propres limites.
LIMITE_REPLI: Final = 4000

# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------
NOMS_MODELES: Final = {
    "solarFlow4000MixPro": "SolarFlow 4000 MIX PRO",
    "solarFlow4000MixAC+": "SolarFlow 4000 MIX AC+",
    "solarFlow3000MixPro": "SolarFlow 3000 MIX PRO",
    "solarFlow3000MixAC+": "SolarFlow 3000 MIX AC+",
    "solarFlow2400AC": "SolarFlow 2400 AC",
    "solarFlow2400AC+": "SolarFlow 2400 AC+",
    "solarFlow2400Pro": "SolarFlow 2400 Pro",
    "solarFlow1600AC+": "SolarFlow 1600 AC+",
    "solarFlow800": "SolarFlow 800",
    "solarFlow800Plus": "SolarFlow 800 Plus",
    "solarFlow800Pro": "SolarFlow 800 Pro",
}

# Capacité d'un pack, en kWh, résolue par le PRÉFIXE DU NUMÉRO DE SÉRIE.
# La documentation zenSDK classe packType en « Reserved » et la même valeur y
# désigne des packs différents selon le modèle : packType 70 vaut 8 kWh sur les
# SolarFlow Mix alors que des tables communautaires lui prêtent 1,92 kWh.
# packType ne sert donc qu'à départager les séries B, et de repli.
CAPACITE_REPLI_PAR_TYPE: Final = {5: 2.88, 250: 0.96, 300: 1.92, 500: 2.40}
