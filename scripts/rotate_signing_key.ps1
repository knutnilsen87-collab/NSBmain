<#
.SYNOPSIS
  Sørger for at signeringsnøkkelen for loggfiler (FBL) ikke er den lekkede nøkkelen.

.DESCRIPTION
  Den gamle private nøkkelen lå i den offentlige git-historikken fram til
  2026-10-16. Fingeravtrykket (sha256 av RSA-modulus) ligger fast i
  docs/revoked_keys.json. Skriptet er trygt å kjøre flere ganger:

  - Finnes det en lokal nøkkel som ikke er tilbaketrukket, gjør det ingenting.
  - Ellers lages et nytt 2048-bits par i formatet FBL-skriptene bruker
    (privat i security/keys/, git-ignorert; offentlig i security/pubkeys/).
  - security/pubkeys/REVOKED.json skrives med alle tilbaketrukne nøkler, slik
    at signaturer laget med dem kan avvises.

  Virker i Windows PowerShell 5.1 og PowerShell 7.
#>
param([string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path)

$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1: hindrer at lister skrives som {"value":[...],"Count":n}.
Remove-TypeData System.Array -ErrorAction SilentlyContinue
$keysDir = Join-Path $Root 'security/keys'
$pubDir = Join-Path $Root 'security/pubkeys'
New-Item -ItemType Directory -Force -Path $keysDir, $pubDir | Out-Null
$privPath = Join-Path $keysDir 'private_key.xml'
$pubPath = Join-Path $pubDir 'public_key.xml'
$revokedPath = Join-Path $pubDir 'REVOKED.json'
$knownPath = Join-Path $Root 'docs/revoked_keys.json'

function Get-ModulusFingerprint([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    $xml = [xml](Get-Content -Path $Path -Raw)
    $modulus = [System.Convert]::FromBase64String($xml.RSAKeyValue.Modulus)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $hash = $sha.ComputeHash($modulus) } finally { $sha.Dispose() }
    return (-join ($hash | ForEach-Object { $_.ToString('x2') }))
}

function Read-JsonList([string]$Path) {
    if (-not (Test-Path $Path)) { return @() }
    # ForEach-Object pakker ut lista også i PowerShell 5.1.
    return @(Get-Content -Path $Path -Raw -Encoding UTF8 | ConvertFrom-Json | ForEach-Object { $_ })
}

$revoked = New-Object System.Collections.ArrayList
$revokedSet = @{}
foreach ($r in @(Read-JsonList $knownPath) + @(Read-JsonList $revokedPath)) {
    if ($r.modulus_sha256 -and -not $revokedSet.ContainsKey($r.modulus_sha256)) {
        [void]$revoked.Add($r)
        $revokedSet[$r.modulus_sha256] = $true
    }
}

$current = Get-ModulusFingerprint $privPath
if ($current -and -not $revokedSet.ContainsKey($current) -and (Get-ModulusFingerprint $pubPath) -eq $current) {
    Write-Host "Signeringsnøkkelen er allerede rotert (modulus sha256 $current)."
} else {
    $oldPub = Get-ModulusFingerprint $pubPath
    foreach ($fp in @($current, $oldPub)) {
        if ($fp -and -not $revokedSet.ContainsKey($fp)) {
            [void]$revoked.Add([pscustomobject]@{
                modulus_sha256 = $fp
                bits           = 2048
                revoked        = (Get-Date).ToString('yyyy-MM-dd')
                reason         = 'Erstattet ved rotasjon (lokal nøkkel uten gyldig par eller tidligere nøkkel).'
            })
            $revokedSet[$fp] = $true
        }
    }
    $rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider(2048)
    try {
        Set-Content -Path $privPath -Value ($rsa.ToXmlString($true)) -Encoding UTF8 -NoNewline
        Set-Content -Path $pubPath -Value ($rsa.ToXmlString($false)) -Encoding UTF8 -NoNewline
    } finally {
        $rsa.Dispose()
    }
    Write-Host "Ny signeringsnøkkel (modulus sha256 $(Get-ModulusFingerprint $pubPath))."
    Write-Host "Privat nøkkel: $privPath (git-ignorert, skal aldri committes)"
}
ConvertTo-Json -InputObject $revoked.ToArray() -Depth 4 | Set-Content -Path $revokedPath -Encoding UTF8
Write-Host "Tilbaketrukket: $($revoked.Count) nøkler i $revokedPath"
