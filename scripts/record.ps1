<#
.SYNOPSIS
  Spill inn juridisk diktat eller simulerte avhør til testsettene.

.DESCRIPTION
  Bruker .venv-bench (lages hvis den mangler), installerer sounddevice,
  viser mikrofonene og starter innspillingen. Opptakene lagres lokalt under
  eval/recording/ og skal aldri i git.

.EXAMPLE
  pwsh -File scripts\record.ps1 -Set diktat
  pwsh -File scripts\record.ps1 -Set avhor -Speakers knut,kari
#>
param(
    [ValidateSet('diktat', 'avhor')]
    [string]$Set = 'diktat',
    [string]$Speaker = '',
    [string]$Speakers = '',
    [string]$Session = '',
    [int]$Device = -1,
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$PythonLauncher = 'py',
    [string]$PythonVersion = '3.11'
)

$ErrorActionPreference = 'Stop'
Set-Location $Root
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$Venv = Join-Path $Root '.venv-bench'
$Py = Join-Path $Venv 'Scripts/python.exe'
if (-not (Test-Path $Py)) {
    Write-Host "Lager $Venv med Python $PythonVersion"
    & $PythonLauncher "-$PythonVersion" -m venv $Venv
}
& $Py -m pip install --quiet sounddevice soundfile numpy
if ($LASTEXITCODE -ne 0) { throw 'Kunne ikke installere sounddevice/soundfile' }

if ($Device -lt 0) {
    Write-Host ''
    Write-Host 'Mikrofoner:'
    $list = & $Py scripts/py/nsb_list_input_devices.py | Out-String | ConvertFrom-Json
    foreach ($d in $list.devices) { Write-Host ("  {0,3}  {1}" -f $d.index, $d.name) }
    $Device = [int](Read-Host 'Nummer på mikrofonen du vil bruke')
}

if ($Set -eq 'diktat') {
    if (-not $Speaker) { $Speaker = Read-Host 'Kort navn på den som leser (for eksempel knut)' }
    Write-Host ''
    Write-Host "50 setninger. Les hver setning nøyaktig slik den står. Ta opp på nytt hvis du leser feil."
    & $Py scripts/py/nsb_record_prompts.py --speaker $Speaker --device $Device
} else {
    if (-not $Speakers) { $Speakers = Read-Host 'To navn, avhører først (for eksempel knut,kari)' }
    if (-not $Session) { $Session = 's' + (Get-Date -Format 'yyyyMMdd-HHmm') }
    Write-Host ''
    Write-Host "Tre avhør. Etterpå må fasiten kontrolleres mot opptaket (se eval/recording/simulated_interview_v1/README.md)."
    & $Py scripts/py/nsb_record_interview.py --session $Session --speakers $Speakers --device $Device
}
exit $LASTEXITCODE
