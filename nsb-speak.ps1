[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TextParts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"



$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$preflight = Join-Path $repoRoot "scripts\NSB.SpeakPreflight.ps1"

if (-not (Test-Path $preflight)) {
    throw "Missing preflight script: $preflight"
}

& $preflight
if ($LASTEXITCODE -ne 0) {
    Write-Host "Speak aborted: preflight failed." -ForegroundColor Red
    exit $LASTEXITCODE
}
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$preflight = Join-Path $repoRoot "scripts\NSB.SpeakPreflight.ps1"

if (-not (Test-Path $preflight)) {
    throw "Missing preflight script: $preflight"
}

& $preflight
if ($LASTEXITCODE -ne 0) {
    Write-Host "Speak aborted: preflight failed." -ForegroundColor Red
    exit $LASTEXITCODE
}
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$yetix = Join-Path $repoRoot 'nsb-speak-yetix.ps1'

if (-not (Test-Path $yetix)) { throw "Missing script: $yetix" }

& $yetix @TextParts
exit $LASTEXITCODE




# Autopilot Phase 1 - enforced verify and speech truth
& "\scripts\NSB.VerifySpeakReference.ps1"
& "\scripts\NSB.EnforceSpeakTruth.ps1"
