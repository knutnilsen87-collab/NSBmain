<#
.SYNOPSIS
  Lager treningsdata fra Stortinget Speech Corpus (SSC) med bokmål som fasit.

.DESCRIPTION
  Bruker miljøet og modellene fra målestokken (.venv-bench og models/benchmark).
  Kjør scripts\RUN_BENCHMARK.cmd én gang først hvis de mangler.

  -Mode Inspect: viser feltene i SSC-filen, timer, talere og målform. Laster ingen modell.
                 Resultat: build/ssc/INSPECT.json
  -Mode Trial:   merker et lite utvalg (-Limit, standard 200 segmenter) for å kontrollere tersklene.
  -Mode Full:    hele utvalget. Kan avbrytes og startes igjen.

  Hovedmodell nb-whisper-large, kontrollmodell whisper-large-v3. Fremdrift: <OutDir>/RUN.log.

.EXAMPLE
  pwsh -File scripts\run_ssc.ps1 -Mode Inspect
  pwsh -File scripts\run_ssc.ps1 -Mode Trial
  pwsh -File scripts\run_ssc.ps1 -Mode Full -MaxHoursPerSpeaker 3
#>
param(
    [ValidateSet('Inspect', 'Trial', 'Full')]
    [string]$Mode = 'Inspect',
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    # SSC-filen. Tom: den største .jsonl-fila under dataset\Stortinget Speech Corpus versjon 1.0.
    [string]$Manifest = '',
    [string]$OutDir = '',
    [int]$Limit = 200,
    [double]$MaxHoursPerSpeaker = 3,
    [double]$MaxHours = 0,
    [string]$SpeakerMeta = '',
    [string]$Model = 'nb-whisper-large',
    [string]$SecondModel = 'whisper-large-v3',
    [string]$Device = 'cuda',
    [string]$ComputeType = 'float16'
)

$ErrorActionPreference = 'Stop'
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
Set-Location $Root
if (-not $OutDir) { $OutDir = if ($Mode -eq 'Trial') { 'build/ssc/trial' } else { 'build/ssc/v1' } }
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'build/ssc') | Out-Null

$Py = Join-Path $Root '.venv-bench/Scripts/python.exe'
if (-not (Test-Path $Py)) {
    Write-Host "Fant ikke $Py. Kjør scripts\RUN_BENCHMARK.cmd én gang først (lager miljøet og laster ned modellene)."
    exit 1
}
$site = (& $Py -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
$sep = [System.IO.Path]::PathSeparator
foreach ($sub in @('nvidia/cublas/bin', 'nvidia/cudnn/bin', 'nvidia/cuda_nvrtc/bin', 'nvidia/cuda_runtime/bin')) {
    $p = Join-Path $site $sub
    if (Test-Path $p) { $env:PATH = "$p$sep$env:PATH" }
}
$env:PYTHONPATH = "$Root$sep$(Join-Path $Root 'src/python')"
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

if (-not $Manifest) {
    $sscDir = Join-Path $Root 'dataset/Stortinget Speech Corpus versjon 1.0'
    if (-not (Test-Path $sscDir)) {
        Write-Host "Fant ikke $sscDir. Oppgi -Manifest <sti til SSC-fila (.jsonl)>."
        exit 1
    }
    $found = Get-ChildItem -Path $sscDir -Filter *.jsonl -Recurse | Sort-Object Length -Descending | Select-Object -First 1
    if (-not $found) {
        Write-Host "Fant ingen .jsonl-fil under $sscDir. Oppgi -Manifest."
        exit 1
    }
    $Manifest = $found.FullName
}
Write-Host "SSC-fil: $Manifest"

$common = @('src/python/ssc_select.py', '--manifest', $Manifest)
if ($SpeakerMeta) { $common += @('--speaker-meta', $SpeakerMeta) }

if ($Mode -eq 'Inspect') {
    $out = Join-Path $Root 'build/ssc/INSPECT.json'
    & $Py @common --inspect | Out-File -FilePath $out
    if ($LASTEXITCODE -ne 0) { Write-Host 'Inspeksjonen feilet.'; exit 1 }
    Get-Content $out
    Write-Host ''
    Write-Host "Lagret i $out. Sjekk field_map: audio og text må være riktige før Trial."
    exit 0
}

$registryPath = Join-Path $Root 'models/benchmark/models.json'
if (-not (Test-Path $registryPath)) { Write-Host 'models/benchmark/models.json mangler. Kjør RUN_BENCHMARK.cmd først.'; exit 1 }
$registry = Get-Content $registryPath -Raw | ConvertFrom-Json
foreach ($m in @($Model, $SecondModel)) {
    if (-not $registry.$m.path) { Write-Host "Modellen $m finnes ikke i models.json."; exit 1 }
}
$args2 = $common + @(
    '--out-dir', $OutDir,
    '--model', $registry.$Model.path, '--label', $Model,
    '--second-model', $registry.$SecondModel.path, '--second-label', $SecondModel,
    '--device', $Device, '--compute-type', $ComputeType
)
if ($MaxHoursPerSpeaker -gt 0) { $args2 += @('--max-hours-per-speaker', "$MaxHoursPerSpeaker") }
if ($MaxHours -gt 0) { $args2 += @('--max-hours', "$MaxHours") }
if ($Mode -eq 'Trial') { $args2 += @('--limit', "$Limit") }

New-Item -ItemType Directory -Force -Path (Join-Path $Root $OutDir) | Out-Null
$log = Join-Path $Root (Join-Path $OutDir 'RUN.log')
Write-Host "Kjører $Mode. Logg: $log"
& $Py @args2 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Write-Host "Kjøringen feilet; se $log"; exit 1 }
Write-Host ''
Write-Host "Ferdig. Se $OutDir/summary.json, labels.jsonl og rejected.jsonl."
exit 0
