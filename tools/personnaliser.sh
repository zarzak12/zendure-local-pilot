#!/usr/bin/env bash
# =====================================================================
# Prepare le dashboard Zendure pour TON installation.
#
# Interroge le Shelly pour recuperer son identifiant, puis remplace le
# marqueur SHELLY_ID du dashboard par le prefixe d'entites utilise par
# Home Assistant. Le resultat est ecrit dans dashboard/dashboard-perso.yaml
# (ignore par git : il contient l'identifiant de ton materiel).
#
# Usage :
#   ./tools/personnaliser.sh <IP_DU_SHELLY> [prefixe_force]
# =====================================================================
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage : $0 <IP_DU_SHELLY> [prefixe_force]" >&2
  exit 1
fi

IP="$1"
PREFIXE="${2:-}"

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$RACINE/dashboard/dashboard HA.yaml"
SORTIE="$RACINE/dashboard/dashboard-perso.yaml"

command -v curl >/dev/null || { echo "curl est requis." >&2; exit 1; }

if [ ! -f "$SOURCE" ]; then
  echo "Dashboard source introuvable : $SOURCE" >&2
  exit 1
fi

# ---- 1. Determiner le prefixe d'entites ----
if [ -z "$PREFIXE" ]; then
  echo "Interrogation du Shelly sur $IP ..."
  INFO=$(curl -s --max-time 10 "http://$IP/rpc/Shelly.GetDeviceInfo") || {
    echo "Shelly injoignable sur $IP" >&2
    echo "  Verifie l'adresse, et que le Shelly est bien allume." >&2
    exit 1
  }
  [ -n "$INFO" ] || { echo "Reponse vide du Shelly." >&2; exit 1; }

  extrait() { printf '%s' "$INFO" | sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p"; }

  # Home Assistant derive l'identifiant d'entite du NOM de l'appareil s'il en
  # a un, sinon de son id usine. On reproduit la meme regle (slug).
  BRUT=$(extrait name)
  [ -n "$BRUT" ] || BRUT=$(extrait id)
  [ -n "$BRUT" ] || { echo "Identifiant du Shelly introuvable dans la reponse." >&2; exit 1; }

  PREFIXE=$(printf '%s' "$BRUT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\+/_/g; s/^_//; s/_$//')

  echo "  modele  : $(extrait model) ($(extrait app), firmware $(extrait ver))"
  echo "  profil  : $(extrait profile)"
  echo "  prefixe : $PREFIXE"

  PROFIL=$(extrait profile)
  if [ -n "$PROFIL" ] && [ "$PROFIL" != "monophase" ]; then
    echo
    echo "ATTENTION : ce Shelly est en profil '$PROFIL'."
    echo "Ce projet attend le profil monophase (pince sur em1:0)."
    echo "Voir la section « Utiliser un Shelly en triphase » du README."
  fi
else
  echo "Prefixe impose : $PREFIXE"
fi

# ---- 2. Generer le dashboard ----
if ! grep -q 'SHELLY_ID' "$SOURCE"; then
  echo "Aucun marqueur SHELLY_ID trouve : le fichier est-il deja personnalise ?" >&2
  exit 1
fi

# L'avertissement « ne colle pas ce fichier tel quel » n'a plus lieu d'etre
# dans le fichier genere : on retire le bloc de commentaires d'en-tete et on
# le remplace par une note de provenance. Sans ca, le marqueur present dans
# l'avertissement serait lui aussi substitue.
{
  echo "# ====================================================================="
  echo "# Dashboard Zendure SolarFlow 4000 MIX PRO - GENERE AUTOMATIQUEMENT"
  echo "# Ne pas editer a la main : relance tools/personnaliser.sh si besoin."
  echo "# Shelly : $PREFIXE"
  echo "# Requiert : apexcharts-card (HACS) + les packages zendure_solarflow4000mix"
  echo "# ====================================================================="
  awk 'debut { print; next } !/^[[:space:]]*(#|$)/ { debut = 1; print }' "$SOURCE"
} | sed "s/SHELLY_ID/$PREFIXE/g" > "$SORTIE"

N=$(grep -c "$PREFIXE" "$SORTIE" || true)
echo
echo "$N references ecrites."
echo "Dashboard pret : $SORTIE"

# ---- 3. Verification : les composants virtuels existent-ils ? ----
# Ils sont crees par le script de regulation. S'ils manquent, le dashboard
# s'affichera avec des cartes « entite introuvable ».
COMP=$(curl -s --max-time 10 -X POST "http://$IP/rpc" \
         -H 'Content-Type: application/json' \
         -d '{"id":1,"method":"Shelly.GetComponents","params":{"dynamic_only":true}}' || true)
# Attention : GetComponents ne renvoie que 7 composants par page, c'est le
# champ "total" qui donne le compte reel.
TOTAL=$(printf '%s' "$COMP" | sed -n 's/.*"total":\([0-9]*\).*/\1/p')
if [ -n "$TOTAL" ]; then
  if [ "$TOTAL" -lt 8 ]; then
    echo
    echo "ATTENTION : seulement $TOTAL composant(s) virtuel(s) sur le Shelly (8 attendus)."
    echo "Lance d'abord le script de regulation (etape 3 du README),"
    echo "puis recharge l'integration Shelly dans Home Assistant."
  else
    echo "Composants virtuels sur le Shelly : $TOTAL/8 OK"
  fi
fi

cat <<EOF

--- Etapes suivantes ---
1. Dans Home Assistant, onglet Reglages du dashboard, saisis
   l'adresse IP du Shelly : $IP
2. Copie le contenu de dashboard-perso.yaml dans ton dashboard
   (Modifier le dashboard -> menu ... -> Modifier en YAML).

L'IP de la Zendure n'est pas a saisir : elle est trouvee toute seule.
EOF
