<#
.SYNOPSIS
  Prepare le dashboard Zendure pour TON installation.

.DESCRIPTION
  Interroge le Shelly pour recuperer son identifiant, puis remplace le marqueur
  SHELLY_ID du dashboard par le prefixe d'entites utilise par Home Assistant.
  Le resultat est ecrit dans dashboard/dashboard-perso.yaml (ignore par git :
  il contient l'identifiant de ton materiel, il n'a rien a faire sur GitHub).

  Affiche aussi l'IP a saisir dans Home Assistant.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\personnaliser.ps1 -Ip 192.168.1.XX

.EXAMPLE
  # Si tu as renomme l'appareil dans Home Assistant, force le prefixe :
  powershell -ExecutionPolicy Bypass -File tools\personnaliser.ps1 -Ip 192.168.1.XX -Prefixe mon_shelly
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$Ip,
  [string]$Prefixe = "",
  [string]$Source  = "",
  [string]$Sortie  = ""
)

$ErrorActionPreference = "Stop"

# Calcules ici et non dans le bloc param : avec un parametre Mandatory,
# $PSScriptRoot n'est pas encore renseigne a l'evaluation des valeurs par defaut.
$racine = Split-Path -Parent $PSScriptRoot
if ($Source -eq "") { $Source = Join-Path $racine "dashboard\dashboard HA.yaml" }
if ($Sortie -eq "") { $Sortie = Join-Path $racine "dashboard\dashboard-perso.yaml" }

if (-not (Test-Path $Source)) {
  Write-Host "Dashboard source introuvable : $Source" -ForegroundColor Red
  exit 1
}

# ---- 1. Determiner le prefixe d'entites ----
if ($Prefixe -eq "") {
  Write-Host "Interrogation du Shelly sur $Ip ..."
  try {
    $resp = Invoke-WebRequest -Uri "http://$Ip/rpc/Shelly.GetDeviceInfo" `
                              -TimeoutSec 10 -UseBasicParsing
    # Le Shelly renvoie de l'UTF-8 sans le declarer : on decode nous-memes.
    $info = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray()) | ConvertFrom-Json
  } catch {
    Write-Host "Shelly injoignable sur $Ip" -ForegroundColor Red
    Write-Host "  Verifie l'adresse, et que le Shelly est bien allume."
    exit 1
  }

  # Home Assistant derive l'identifiant d'entite du NOM de l'appareil s'il en a
  # un, sinon de son id usine. On reproduit la meme regle (slug : minuscules,
  # tout caractere non alphanumerique devient un souligne).
  $brut = if ($info.name) { $info.name } else { $info.id }
  $Prefixe = ($brut.ToLower() -replace '[^a-z0-9]+', '_').Trim('_')

  Write-Host "  modele   : $($info.model) ($($info.app), firmware $($info.ver))"
  Write-Host "  profil   : $($info.profile)"
  Write-Host "  prefixe  : $Prefixe"

  if ($info.profile -and $info.profile -ne "monophase") {
    Write-Host ""
    Write-Host "ATTENTION : ce Shelly est en profil '$($info.profile)'." -ForegroundColor Yellow
    Write-Host "Ce projet attend le profil monophase (pince sur em1:0)."
    Write-Host "Voir la section « Utiliser un Shelly en triphase » du README."
  }
} else {
  Write-Host "Prefixe impose : $Prefixe"
}

# ---- 2. Generer le dashboard ----
$texte = [IO.File]::ReadAllText($Source)
$avant = ([regex]::Matches($texte, 'SHELLY_ID')).Count
if ($avant -eq 0) {
  Write-Host "Aucun marqueur SHELLY_ID trouve : le fichier est-il deja personnalise ?" -ForegroundColor Yellow
  exit 1
}

# L'avertissement « ne colle pas ce fichier tel quel » n'a plus lieu d'etre
# dans le fichier genere : on le remplace par une note de provenance. Sans ca,
# le marqueur present dans l'avertissement serait lui aussi substitue et le
# commentaire deviendrait incomprehensible.
$lignes = $texte -split "`r?`n"
$i = 0
while ($i -lt $lignes.Count -and ($lignes[$i].TrimStart().StartsWith("#") -or $lignes[$i].Trim() -eq "")) { $i++ }

$entete = @(
  "# ====================================================================="
  "# Dashboard Zendure SolarFlow 4000 MIX PRO - GENERE AUTOMATIQUEMENT"
  "# Ne pas editer a la main : relance tools/personnaliser.ps1 si besoin."
  "# Shelly : $Prefixe"
  "# Requiert : apexcharts-card (HACS) + les packages zendure_solarflow4000mix"
  "# ====================================================================="
)
$texte = ($entete + $lignes[$i..($lignes.Count - 1)]) -join "`r`n"

$avant = ([regex]::Matches($texte, 'SHELLY_ID')).Count
$texte = $texte -replace 'SHELLY_ID', $Prefixe
# Sans BOM : Home Assistant et l'editeur de dashboard n'en veulent pas.
[IO.File]::WriteAllText($Sortie, $texte, (New-Object Text.UTF8Encoding $false))

$chemin = (Resolve-Path $Sortie).Path
Write-Host ""
Write-Host "$avant remplacements effectues." -ForegroundColor Green
Write-Host "Dashboard pret : $chemin"

# ---- 3. Verification : les entites existent-elles vraiment ? ----
# Les composants virtuels sont crees par le script de regulation. S'ils
# manquent, le dashboard s'affichera avec des cartes « entite introuvable ».
try {
  $body  = '{"id":1,"method":"Shelly.GetComponents","params":{"dynamic_only":true}}'
  $bytes = [Text.Encoding]::UTF8.GetBytes($body)
  $resp  = Invoke-WebRequest -Uri "http://$Ip/rpc" -Method Post -Body $bytes `
                             -ContentType "application/json" -TimeoutSec 10 -UseBasicParsing
  $res   = ([Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray()) | ConvertFrom-Json).result
  # Attention : Shelly.GetComponents ne renvoie que 7 composants par page.
  # C'est le champ "total" qui donne le compte reel, pas la taille du tableau.
  $n     = [int]$res.total
  if ($n -lt 8) {
    Write-Host ""
    Write-Host "ATTENTION : seulement $n composant(s) virtuel(s) sur le Shelly (8 attendus)." -ForegroundColor Yellow
    Write-Host "Lance d'abord le script de regulation (etape 3 du README),"
    Write-Host "puis recharge l'integration Shelly dans Home Assistant."
  } else {
    Write-Host "Composants virtuels sur le Shelly : $n/8 OK" -ForegroundColor Green
  }
} catch {
  Write-Host "(verification des composants virtuels impossible, sans gravite)"
}

Write-Host ""
Write-Host "--- Etapes suivantes ---"
Write-Host "1. Dans Home Assistant, onglet Reglages du dashboard, saisis"
Write-Host "   l'adresse IP du Shelly : $Ip"
Write-Host "2. Copie le contenu de dashboard-perso.yaml dans ton dashboard"
Write-Host "   (Modifier le dashboard -> menu ... -> Modifier en YAML)."
Write-Host ""
Write-Host "L'IP de la Zendure n'est pas a saisir : elle est trouvee toute seule."
