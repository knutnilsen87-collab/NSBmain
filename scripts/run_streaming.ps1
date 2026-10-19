<#
.SYNOPSIS
  Måler strømmende gjenkjenning (nsb-engine) på GPU og CPU.

.DESCRIPTION
  Bruker .venv-bench og modellene fra målestokken (models/benchmark).
  Resultater: eval/results/streaming/<måling>/<modell>/streaming_summary.json
  Fremdrift: eval/results/streaming/RUN.log
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [switch]$Quick
)

$ErrorActionPreference = 'Continue'
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
Set-Location $Root
$Py = Join-Path $Root '.venv-bench/Scripts/python.exe'
if (-not (Test-Path $Py)) { Write-Host 'Fant ikke .venv-bench. Kjør scripts\RUN_BENCHMARK.cmd først.'; exit 1 }
$Out = Join-Path $Root 'eval/results/streaming'
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Log = Join-Path $Out 'RUN.log'
function Write-Log([string]$Message) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    for ($i = 0; $i -lt 10; $i++) {
        try { Add-Content -Path $Log -Value $line -Encoding utf8 -ErrorAction Stop; return } catch { Start-Sleep -Milliseconds 300 }
    }
}

Write-Log 'Installerer numpy, fastapi og uvicorn i .venv-bench'
& $Py -m pip install --quiet numpy fastapi uvicorn websockets httpx cryptography *>> (Join-Path $Out 'RUN.detail.log')

$site = (& $Py -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
$sep = [System.IO.Path]::PathSeparator
foreach ($sub in @('nvidia/cublas/bin', 'nvidia/cudnn/bin', 'nvidia/cuda_nvrtc/bin', 'nvidia/cuda_runtime/bin')) {
    $p = Join-Path $site $sub
    if (Test-Path $p) { $env:PATH = "$p$sep$env:PATH" }
}
$env:PYTHONPATH = $Root
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

# Distil-turbo arver ordtidshoder fra large som ikke finnes i dens 2 dekoderlag.
& $Py scripts/download_models.py --out models/benchmark --fix-only *>> (Join-Path $Out 'RUN.detail.log')

$registry = Get-Content (Join-Path $Root 'eval/results/models.json') -Raw | ConvertFrom-Json
$limit = if ($Quick) { 20 } else { 0 }

# Navn, testsett, modell, enhet, antall setninger, ekstra argumenter
$jobs = @(
    @('npsc_vad', 'npsc_test_20170207', 'nb-whisper-large-distil-turbo-beta', 'cuda', 200, @('--vad')),
    @('npsc_vad', 'npsc_test_20170207', 'nb-whisper-large', 'cuda', 200, @('--vad')),
    @('npsc_vad_steg05', 'npsc_test_20170207', 'nb-whisper-large-distil-turbo-beta', 'cuda', 200, @('--vad', '--min-step', '0.5')),
    @('npsc_uten_vad', 'npsc_test_20170207', 'nb-whisper-large-distil-turbo-beta', 'cuda', 200, @()),
    @('samtale_vad', 'nb_samtale_test', 'nb-whisper-large-distil-turbo-beta', 'cuda', 300, @('--vad')),
    @('npsc_vad_cpu', 'npsc_test_20170207', 'nb-whisper-large-distil-turbo-beta', 'cpu', 50, @('--vad')),
    @('npsc_vad_cpu', 'npsc_test_20170207', 'nb-whisper-small', 'cpu', 50, @('--vad'))
)
$failed = 0
foreach ($j in $jobs) {
    $name, $ts, $m, $dev, $n, $extra = $j
    if ($limit) { $n = [Math]::Min($n, $limit) }
    $entry = $registry.$m
    if (-not $entry -or -not (Test-Path (Join-Path $Root $entry.path))) { Write-Log "Hopper over $m (modellen finnes ikke)"; continue }
    $dir = Join-Path $Out "$name/$m"
    if (Test-Path (Join-Path $dir 'streaming_summary.json')) { Write-Log "Ferdig fra før: $name / $m"; continue }
    $ct = if ($dev -eq 'cpu') { 'int8' } else { 'float16' }
    Write-Log "$name / $m ($dev, $n setninger)"
    & $Py -m nsb_eval.streaming_eval --root $Root --testset $ts --model $entry.path --label $m `
        --model-revision "$($entry.revision)" --model-sha256 "$($entry.model_sha256)" `
        --device $dev --compute-type $ct --limit $n --out-dir $dir @extra *>> (Join-Path $Out 'RUN.detail.log')
    if ($LASTEXITCODE -ne 0) { $failed++; Write-Log "FEIL: $name / $m (se RUN.detail.log)" }
    else {
        $s = Get-Content (Join-Path $dir 'streaming_summary.json') -Raw | ConvertFrom-Json
        Write-Log ("  WER strøm {0:P1}, hel {1:P1}; ferdig ord etter {2} s (median), vist etter {3} s; endringer {4} per 100 ord; sanntidsfaktor {5}" -f `
            $s.wer_streaming, $s.wer_batch, $s.commit_latency_s.median, $s.display_latency_s.median, $s.changes_per_100_words, $s.real_time_factor)
    }
}
Write-Log "Ferdig ($failed feilet)"
exit $failed
