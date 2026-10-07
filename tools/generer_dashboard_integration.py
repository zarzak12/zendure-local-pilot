"""Produit le tableau de bord de l'intégration HACS à partir de celui du YAML.

    python tools/generer_dashboard_integration.py

Le tableau de bord de référence reste « dashboard/dashboard HA.yaml ». Ce
script en dérive « dashboard/dashboard_integration.yaml », prêt à coller tel
quel : avec l'intégration, les identifiants sont les mêmes chez tout le monde.

Chaque remplacement DOIT trouver sa cible : si le tableau de bord de référence
évolue et qu'une cible disparaît, le script s'arrête au lieu de produire un
tableau de bord silencieusement faux. Relance-le après toute modification du
tableau de bord de référence.
"""

from __future__ import annotations

import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(RACINE, "dashboard", "dashboard HA.yaml")
CIBLE = os.path.join(RACINE, "dashboard", "dashboard_integration.yaml")
P = "zendure_solarflow4000mix"

# Entités : version YAML -> intégration. Les plus longues d'abord, pour que
# « buffer_charge » ne soit pas pris pour « buffer » suivi de « _charge ».
ENTITES = {
    "select.SHELLY_ID_zendure_mode": f"select.{P}_mode",
    "number.SHELLY_ID_zendure_consigne_manuelle": f"number.{P}_consigne_manuelle",
    "number.SHELLY_ID_zendure_decharge_max": f"number.{P}_decharge_max",
    "number.SHELLY_ID_zendure_charge_max": f"number.{P}_charge_max",
    "number.SHELLY_ID_zendure_buffer_charge": f"number.{P}_buffer_charge",
    "number.SHELLY_ID_zendure_buffer": f"number.{P}_buffer",
    "number.SHELLY_ID_zendure_delai_veille": f"number.{P}_delai_veille",
    "binary_sensor.SHELLY_ID_zendure_en_veille": f"binary_sensor.{P}_en_veille",
    f"input_boolean.{P}_show_help": f"switch.{P}_show_help",
    f"input_boolean.{P}_show_pv": f"switch.{P}_show_pv",
    f"input_number.{P}_pack_1_capacite_estimee": f"sensor.{P}_pack_1_capacite_estimee",
    # La capacité n'est plus saisie : elle découle des packs présents.
    f"input_number.{P}_capacite": f"sensor.{P}_capacite_nominale_totale",
    f"input_number.{P}_soc_min_consigne": f"number.{P}_soc_min_consigne",
    f"input_number.{P}_soc_max_consigne": f"number.{P}_soc_max_consigne",
    f"input_number.{P}_em_canal": f"select.{P}_canal_em",
    f"input_text.{P}_ip": f"sensor.{P}_ip",
    f"input_number.{P}_periode": f"number.{P}_period",
    f"input_number.{P}_tick": f"number.{P}_tick",
    f"input_number.{P}_gain": f"number.{P}_gain",
    f"input_number.{P}_zone_morte": f"number.{P}_dead",
    f"input_number.{P}_hysteresis": f"number.{P}_hyst",
    f"input_number.{P}_seuil_reveil": f"number.{P}_wake",
    f"input_number.{P}_delai_bascule": f"number.{P}_flip",
    f"input_number.{P}_seuil_bascule": f"number.{P}_flipw",
    f"input_number.{P}_lissage": f"number.{P}_smooth",
}

ENTETE_SOURCE_FIN = "# =====================================================================\nviews:"
ENTETE = """\
# =====================================================================
# Dashboard Zendure — version INTÉGRATION HACS (zendure_local_pilot)
# Requiert : apexcharts-card (HACS) + l'intégration Zendure Local Pilot
#
# Fichier GÉNÉRÉ par tools/generer_dashboard_integration.py à partir de
# « dashboard HA.yaml » : ne le modifie pas à la main.
#
# À coller tel quel : avec l'intégration, les identifiants d'entités sont
# les mêmes chez tout le monde, il n'y a rien à personnaliser.
# =====================================================================
views:"""

# Remplacements de texte : (cible, remplacement). Chacun doit trouver sa cible.
TEXTES = [
    # Le mode est lu par son option, plus par le libellé du Shelly
    ("state: Manuel", "state: manuel"),
    # Plus de capteur « raw » : la liaison est un binary_sensor, le produit et
    # le SN sont des attributs du capteur de modèle.
    ("{% set raw = states.sensor.zendure_solarflow4000mix_raw %}\n"
     "              {% set age = (now() - raw.last_updated).total_seconds() if raw else 9999 %}",
     "{% set age = 0 if is_state('binary_sensor.zendure_solarflow4000mix_batterie_joignable', 'on') else 9999 %}"),
    ("states('sensor.zendure_solarflow4000mix_raw')",
     "state_attr('sensor.zendure_solarflow4000mix_modele', 'produit')"),
    ("              {% set raw = states.sensor.zendure_solarflow4000mix_raw %}\n\n", ""),
    ("state_attr('sensor.zendure_solarflow4000mix_raw', 'sn')",
     "state_attr('sensor.zendure_solarflow4000mix_modele', 'sn')"),
    ("""              **Dernière lecture API**

              {% if raw and (now() - raw.last_updated).total_seconds() < 120 %}
              {{ raw.last_updated | as_local | as_timestamp | timestamp_custom('%d/%m/%Y %H:%M:%S') }}
              {% else %}API locale injoignable{% endif %}""",
     """              **Liaison batterie**

              {% if is_state('binary_sensor.zendure_solarflow4000mix_batterie_joignable', 'on') %}
              OK — {{ states('sensor.zendure_solarflow4000mix_ip') }}
              {% else %}API locale injoignable{% endif %}"""),
    # Textes d'aide devenus faux
    ("""Renseigne la capacité
              utile totale de tes packs : elle sert""",
     """La capacité est déduite
              des packs présents : elle sert"""),
    ("l'écriture dans la Zendure part 5 s après le dernier mouvement",
     "chaque réglage est écrit aussitôt dans la Zendure"),
    ("""l'installation. Ne change l'**IP** que si la réservation DHCP de la
              Zendure a changé.""",
     """l'installation. L'**IP** de la Zendure est découverte par le
              script."""),
    # Bloc propre à l'intégration : état du script du Shelly et actions
    ("""          - type: heading
            heading: Réglages avancés (KVS Shelly)""",
     f"""          - type: heading
            heading: Script du Shelly
            heading_style: title
            badges:
              - type: entity
                entity: sensor.{P}_script_etat
                show_state: true
                show_icon: true
                color: '#01a180'
          - type: markdown
            text_only: true
            content: >-
              <ha-alert alert-type="error">Script en erreur</ha-alert>{{{{
              state_attr('sensor.{P}_script_etat', 'message')
              or 'Le Shelly signale une erreur : consulte la console du script.' }}}}
            visibility:
              - condition: state
                entity: binary_sensor.{P}_script_erreur
                state: 'on'
          - type: markdown
            text_only: true
            content: >-
              <ha-alert alert-type="info">Aide</ha-alert>**Relancer** arrête
              puis redémarre le script sans toucher à son code. **Redéployer**
              réécrit le script embarqué dans l'intégration, vérifié par
              relecture : utile si le code du Shelly a été abîmé. Un **CPU à
              0 %** alors que le script tourne en mode régulé signale un script
              tronqué.
            visibility: *vis_help2
          - type: entities
            show_header_toggle: false
            entities:
              - entity: switch.{P}_regulation
                name: Régulation
              - entity: update.{P}_script_shelly
                name: Version du script
              - entity: sensor.{P}_script_cpu
                name: CPU du script
              - entity: sensor.{P}_script_memoire
                name: Mémoire utilisée
              - entity: sensor.{P}_script_memoire_pic
                name: Mémoire (pic)
              - entity: sensor.{P}_shelly_demarrage
                name: Démarrage du Shelly
              - entity: sensor.{P}_shelly_wifi_rssi
                name: Signal Wi-Fi du Shelly
              - entity: button.{P}_relancer_script
                name: Relancer le script
              - entity: button.{P}_redeployer_script
                name: Redéployer le script
          - type: heading
            heading: Réglages avancés (KVS Shelly)"""),
    # Les scripts de réglage deviennent des entités modifiables directement
    ("""          - type: tile
            entity: script.zendure_solarflow4000mix_set_soc
            name: Modifier les bornes SOC
            icon: mdi:battery-sync
            tap_action: {action: more-info}
""", ""),
    ("""          - type: tile
            entity: script.zendure_solarflow4000mix_set_plafonds
            name: Modifier les plafonds
            icon: mdi:speedometer
            tap_action: {action: more-info}""",
     f"""          - type: entities
            show_header_toggle: false
            entities:
              - entity: number.{P}_plafond_decharge_consigne
                name: Plafond de décharge
              - entity: number.{P}_plafond_charge_consigne
                name: Plafond de charge"""),
    ("""          - type: tile
            entity: script.zendure_solarflow4000mix_set_injection_pv
            name: Modifier l'injection PV
            icon: mdi:transmission-tower-export
            tap_action: {action: more-info}""",
     f"""          - type: entities
            show_header_toggle: false
            entities:
              - entity: select.{P}_injection_pv_consigne
                name: Injection PV"""),
    ("""          - type: tile
            entity: script.zendure_solarflow4000mix_set_mode_secours
            name: Modifier le mode secours
            icon: mdi:power-plug-off
            tap_action: {action: more-info}""",
     f"""          - type: entities
            show_header_toggle: false
            entities:
              - entity: select.{P}_mode_secours_consigne
                name: Mode secours"""),
    ("""              - entity: script.zendure_solarflow4000mix_reset_sante
                name: Réinitialiser l'estimation
                icon: mdi:restart""",
     """              - type: button
                name: Réinitialiser l'estimation
                icon: mdi:restart
                action_name: Réinitialiser
                tap_action:
                  action: perform-action
                  perform_action: zendure_local_pilot.reset_health
                  confirmation:
                    text: Effacer les capacités mesurées et repartir de zéro ?"""),
]

# Ce qui ne doit plus apparaître dans le résultat
INTERDITS = ("SHELLY_ID", "input_number.", "input_boolean.", "input_text.",
             "script.zendure", "_raw", "reseau_shelly", "config_shelly")


def generer(source: str) -> str:
    texte = source.replace("\r\n", "\n")
    debut = texte.index(ENTETE_SOURCE_FIN) + len(ENTETE_SOURCE_FIN)
    texte = ENTETE + texte[debut:]

    for cible, remplacement in TEXTES:
        if cible not in texte:
            raise SystemExit(f"cible introuvable, le tableau de bord a changé :\n{cible}")
        texte = texte.replace(cible, remplacement)

    for ancien in sorted(ENTITES, key=len, reverse=True):
        motif = re.escape(ancien) + r"(?![A-Za-z0-9_])"
        texte, n = re.subn(motif, ENTITES[ancien], texte)
        if n == 0:
            raise SystemExit(f"entité introuvable, le tableau de bord a changé : {ancien}")

    restes = [m for m in INTERDITS if m in texte]
    if restes:
        raise SystemExit(f"références de la version YAML restantes : {restes}")
    return texte


def main() -> None:
    with open(SOURCE, encoding="utf-8") as f:
        resultat = generer(f.read())
    with open(CIBLE, "w", encoding="utf-8", newline="\n") as f:
        f.write(resultat)
    print(f"écrit : {os.path.relpath(CIBLE, RACINE)} ({resultat.count(chr(10))} lignes)")


if __name__ == "__main__":
    sys.exit(main())
