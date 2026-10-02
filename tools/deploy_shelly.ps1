<#
.SYNOPSIS
    Televerse le script de regulation dans un Shelly, puis verifie par relecture.

.DESCRIPTION
    L'editeur web du Shelly tronque silencieusement les collages volumineux :
    au-dela de ~7 ko, une partie du code est perdue. Si la coupure tombe dans un
    commentaire, le script parse quand meme et demarre sans erreur, mais ne fait
    rien (cpu 0 %). Ce deployeur passe par l'API RPC, ecrit par blocs de 1 ko,
    puis relit et compare avant de demarrer le script.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\deploy_shelly.ps1 -Ip 192.168.1.XX

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\deploy_shelly.ps1 -Ip 192.168.1.XX -Id 2
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$Ip,
  [int]   $Id     = 1,
  [string]$Source = ""
)

$ErrorActionPreference = "Stop"

# Calcule ici et non dans le bloc param : avec un parametre Mandatory,
# $PSScriptRoot n'est pas encore renseigne a l'evaluation des valeurs par defaut.
if ($Source -eq "") {
  $Source = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\zendure_solarflow_4000_mix_pro.js"
}

function Rpc($method, $params) {
  $body  = (@{ id = 1; method = $method; params = $params } | ConvertTo-Json -Depth 10 -Compress)
  $bytes = [Text.Encoding]::UTF8.GetBytes($body)
  # Decodage manuel de la reponse : le Shelly renvoie de l'UTF-8 sans le declarer
  # dans le Content-Type, et PowerShell 5.1 retomberait sur ISO-8859-1 (accents casses).
  $resp = Invoke-WebRequest -Uri "http://$Ip/rpc" -Method Post -ContentType "application/json" `
                            -Body $bytes -TimeoutSec 20 -UseBasicParsing
  $text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
  if ([string]::IsNullOrWhiteSpace($text)) { return $null }
  $r = $text | ConvertFrom-Json
  # POST /rpc renvoie l'enveloppe {id, src, dst, result}, contrairement au GET /rpc/Methode
  if ($null -ne $r -and $r.PSObject.Properties.Name -contains "result") { return $r.result }
  return $r
}

function GetCode {
  $all = ""; $off = 0
  while ($true) {
    $r = Rpc "Script.GetCode" @{ id = $Id; offset = $off; len = 1024 }
    if (-not $r.data -or $r.data.Length -eq 0) { break }
    $d = $r.data
    # Une page peut se terminer AU MILIEU d'une sequence UTF-8 (un accent a
    # cheval sur deux pages) : les octets orphelins se decodent alors en U+FFFD.
    # On les retire, l'offset restera pose sur le 1er octet du caractere qui
    # sera donc relu entier a la page suivante. Sans ca, on perd un caractere
    # et on croit a tort que l'ecriture a echoue.
    while ($d.Length -gt 0 -and $d[$d.Length - 1] -eq [char]0xFFFD) {
      $d = $d.Substring(0, $d.Length - 1)
    }
    if ($d.Length -eq 0) { break }
    $all += $d
    # Script.GetCode pagine en OCTETS. Avancer du nombre de CARACTERES relirait
    # en double chaque sequence UTF-8 multi-octets (les accents) et fabriquerait
    # de faux doublons dans le texte reconstitue.
    $off += [Text.Encoding]::UTF8.GetByteCount($d)
    if ($r.left -le 0) { break }
  }
  return $all
}

if (-not (Test-Path $Source)) { Write-Host "Source introuvable : $Source"; exit 1 }

# Le Shelly stocke en LF : on normalise pour que la comparaison porte sur
# exactement ce qui sera ecrit.
$code = ([IO.File]::ReadAllText($Source)) -replace "`r`n", "`n"
Write-Host "source : $($code.Length) caracteres, $([Text.Encoding]::UTF8.GetByteCount($code)) octets"

Rpc "Script.Stop" @{ id = $Id } | Out-Null
Start-Sleep -Milliseconds 500

$chunk = 1024
$ok = $false

for ($try = 1; $try -le 3 -and -not $ok; $try++) {
  Write-Host "`n--- tentative $try ---"
  $off = 0
  while ($off -lt $code.Length) {
    $len  = [Math]::Min($chunk, $code.Length - $off)
    $part = $code.Substring($off, $len)
    Rpc "Script.PutCode" @{ id = $Id; code = $part; append = ($off -gt 0) } | Out-Null
    $off += $len
  }
  Start-Sleep -Milliseconds 500

  $back = GetCode
  if ($back -ceq $code) {
    Write-Host "verification OK : $($back.Length) caracteres identiques"
    $ok = $true
  } else {
    Write-Host "ECHEC : relu $($back.Length) vs attendu $($code.Length)"
    for ($i = 0; $i -lt [Math]::Min($back.Length, $code.Length); $i++) {
      if ($back[$i] -cne $code[$i]) {
        Write-Host "  premier ecart a l'offset $i"
        Write-Host "  attendu : ..." ($code.Substring([Math]::Max(0,$i-40), 80) -replace "`n","\n")
        Write-Host "  recu    : ..." ($back.Substring([Math]::Max(0,$i-40), 80) -replace "`n","\n")
        break
      }
    }
  }
}

if (-not $ok) { Write-Host "`nABANDON : le code n'a pas pu etre ecrit correctement"; exit 1 }

Rpc "Script.SetConfig" @{ id = $Id; config = @{ enable = $true } } | Out-Null
Rpc "Script.Start"     @{ id = $Id } | Out-Null
Start-Sleep -Seconds 3

$st = Rpc "Script.GetStatus" @{ id = $Id }
Write-Host "`n--- statut ---"
Write-Host ($st | ConvertTo-Json -Compress)
if ($st.running -ne $true) { Write-Host "ATTENTION : le script ne tourne pas"; exit 1 }
Write-Host "`nDeploiement termine. Laisse passer ~30 s puis verifie que cpu > 0 %"
Write-Host "(cpu a 0 % en mode regule = le script ne fait rien)."
