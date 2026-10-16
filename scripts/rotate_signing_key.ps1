<#
.SYNOPSIS
  Lager nytt RSA-nøkkelpar for signering av loggfiler (FBL) og trekker det gamle tilbake.

.DESCRIPTION
  Den gamle private nøkkelen (security/keys/private_key.xml) lå i den offentlige
  git-historikken fram til oktober 2026 og regnes som kompromittert. Den ble bare
  brukt til å signere lokale loggfiler. Skriptet:

  1. Lager et nytt 2048-bits RSA-par i formatet FBL-skriptene bruker (.NET XML).
  2. Lagrer privat nøkkel i security/keys/ (git-ignorert) og offentlig nøkkel i
     security/pubkeys/public_key.xml.
  3. Skriver security/pubkeys/REVOKED.json med fingeravtrykket til den gamle
     offentlige nøkkelen, slik at gamle signaturer kan avvises.
#>
param([string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path)

$ErrorActionPreference = 'Stop'
$keysDir = Join-Path $Root 'security/keys'
$pubDir = Join-Path $Root 'security/pubkeys'
New-Item -ItemType Directory -Force -Path $keysDir, $pubDir | Out-Null
$privPath = Join-Path $keysDir 'private_key.xml'
$pubPath = Join-Path $pubDir 'public_key.xml'
$revokedPath = Join-Path $pubDir 'REVOKED.json'

function Get-Fingerprint([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

$revoked = @()
if (Test-Path $revokedPath) { $revoked = @(Get-Content $revokedPath -Raw | ConvertFrom-Json) }
if (Test-Path $pubPath) {
    $revoked += [ordered]@{
        public_key_sha256 = (Get-Fingerprint $pubPath)
        revoked_at        = (Get-Date).ToString('o')
        reason            = 'Privat nøkkel lå i offentlig git-historikk (knutnilsen87-collab/NSBmain) fram til 2026-10-16.'
    }
}

$rsa = [System.Security.Cryptography.RSACryptoServiceProvider]::new(2048)
try {
    Set-Content -Path $privPath -Value ($rsa.ToXmlString($true)) -Encoding utf8 -NoNewline
    Set-Content -Path $pubPath -Value ($rsa.ToXmlString($false)) -Encoding utf8 -NoNewline
} finally {
    $rsa.Dispose()
}
ConvertTo-Json -InputObject @($revoked) -Depth 4 | Set-Content -Path $revokedPath -Encoding utf8

Write-Host "Ny offentlig nøkkel: $pubPath (sha256 $(Get-Fingerprint $pubPath))"
Write-Host "Privat nøkkel: $privPath (git-ignorert, skal aldri committes)"
Write-Host "Tilbaketrukket: $($revoked.Count) gamle nøkler i $revokedPath"
