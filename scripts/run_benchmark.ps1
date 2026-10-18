<#
.SYNOPSIS
  Kjører NSB-målestokken: alle modeller mot alle faste testsett.

.DESCRIPTION
  1. Lager .venv-bench med faster-whisper og CUDA-bibliotekene fra pip.
  2. Laster ned modellene (scripts/download_models.py).
  3. Lager stillhetssettet (nsb_eval.silence).
  4. Sjekker at GPU-en virker; faller tilbake til CPU int8 hvis ikke.
  5. Kjører nsb_eval.runner per modell og testsett (kan avbrytes og startes igjen).
  6. Skriver eval/results/BENCHMARK.md og BENCHMARK.json.

  Fremdrift: eval/results/RUN.log (detaljer i RUN.detail.log) og eval/results/RUN_STATUS.json.

.EXAMPLE
  pwsh -File scripts\run_benchmark.ps1
  pwsh -File scripts\run_benchmark.ps1 -Models nb-whisper-small -Testsets npsc_test_20170207 -Limit 20
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string[]]$Models = @('nb-whisper-small', 'nb-whisper-medium', 'nb-whisper-large', 'nb-whisper-large-distil-turbo-beta', 'whisper-large-v3'),
    [string[]]$Testsets = @('silence_v1', 'npsc_test_20170207', 'npsc_eval_20170209', 'nb_samtale_test'),
    [string]$PythonLauncher = 'py',
    [string]$PythonVersion = '3.11',
    [string]$Device = 'cuda',
    [string]$ComputeType = 'float16',
    [int]$Limit = 0,
    # Egen undermappe i eval/results for ekstra kjøringer (for eksempel 'cpu').
    [string]$OutPrefix = '',
    # Legges til testsettnavnet i resultatet (for eksempel '_maalform').
    [string]$TestsetSuffix = '',
    # Dekod hver setning med målformen i manifestet (bm -> no, nn -> nn).
    [switch]$LanguageFromMeta,
    # Slå på stemmeaktivitetsdeteksjon (VAD) i dekodingen.
    [switch]$Vad,
    [switch]$SkipSetup,
    # For testing: bruk en eksisterende Python og en ferdig models.json (hopper over nedlasting).
    [string]$PythonExe = '',
    [string]$ModelsJson = ''
)

$ErrorActionPreference = 'Continue'
# Fra .cmd (-File) kommer lister som én streng med komma: del dem opp.
$Models = @($Models | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Testsets = @($Testsets | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
# Windows PowerShell 5.1 skriver ellers omdirigering (*>>) som UTF-16.
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
Set-Location $Root
if ($Device -eq 'cpu' -and $ComputeType -eq 'float16') { $ComputeType = 'int8' }  # float16 virker ikke på CPU
$Results = Join-Path $Root 'eval/results'
$JobRoot = if ($OutPrefix) { Join-Path $Results $OutPrefix } else { $Results }
New-Item -ItemType Directory -Force -Path $JobRoot | Out-Null
$Log = Join-Path $JobRoot 'RUN.log'
# Utdata fra pip og Python går til en egen fil. Windows PowerShell 5.1 kan holde
# filen låst etter *>>, og da feiler Add-Content mot samme fil.
$Detail = Join-Path $JobRoot 'RUN.detail.log'
$StatusPath = Join-Path $JobRoot 'RUN_STATUS.json'

function Write-Log([string]$Message) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    for ($i = 0; $i -lt 10; $i++) {
        try { Add-Content -Path $Log -Value $line -Encoding utf8 -ErrorAction Stop; return }
        catch { Start-Sleep -Milliseconds 300 }
    }
}

$status = [ordered]@{
    started      = (Get-Date).ToString('o')
    root         = $Root
    device       = $Device
    compute_type = $ComputeType
    phase        = 'setup'
    jobs         = [ordered]@{}
    finished     = $null
    error        = $null
}
function Save-Status { $status | ConvertTo-Json -Depth 8 | Set-Content -Path $StatusPath -Encoding utf8 }
function Stop-WithError([string]$Message) {
    Write-Log "FEIL: $Message"
    $status.phase = 'failed'
    $status.error = $Message
    $status.finished = (Get-Date).ToString('o')
    Save-Status
    exit 1
}
Save-Status
Write-Log "Start i $Root (modeller: $($Models -join ', '); testsett: $($Testsets -join ', '))"

# ---------- 1. Miljø
$Venv = Join-Path $Root '.venv-bench'
$Py = if ($PythonExe) { $PythonExe } else { Join-Path $Venv 'Scripts/python.exe' }
if (-not $SkipSetup) {
    if (-not (Test-Path $Py)) {
        Write-Log "Lager $Venv med Python $PythonVersion"
        & $PythonLauncher "-$PythonVersion" -m venv $Venv
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Py)) { Stop-WithError "Kunne ikke lage venv med '$PythonLauncher -$PythonVersion'" }
    }
    Write-Log 'Installerer faster-whisper og CUDA-biblioteker (kan ta noen minutter)'
    & $Py -m pip install --upgrade pip *>> $Detail
    & $Py -m pip install 'faster-whisper==1.2.1' 'av>=11,<16' 'huggingface_hub[hf_xet]>=0.23,<1.0' 'nvidia-cublas-cu12' 'nvidia-cudnn-cu12==9.*' 'psutil' *>> $Detail
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'pip install feilet; se RUN.detail.log' }
}
if (-not (Test-Path $Py) -and -not (Get-Command $Py -ErrorAction SilentlyContinue)) { Stop-WithError "Fant ikke Python i $Py. Kjør uten -SkipSetup første gang." }
$site = (& $Py -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
$sep = [System.IO.Path]::PathSeparator
foreach ($sub in @('nvidia/cublas/bin', 'nvidia/cudnn/bin', 'nvidia/cuda_nvrtc/bin', 'nvidia/cuda_runtime/bin')) {
    $p = Join-Path $site $sub
    if (Test-Path $p) { $env:PATH = "$p$sep$env:PATH" }
}
$env:PYTHONPATH = "$Root$sep$(Join-Path $Root 'src/python')"
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
$versions = (& $Py -c "import faster_whisper, ctranslate2; print(faster_whisper.__version__, ctranslate2.__version__, ctranslate2.get_cuda_device_count())").Trim()
Write-Log "faster-whisper, ctranslate2, CUDA-enheter: $versions"
$status.versions = $versions

# ---------- 2. Modeller
$status.phase = 'download'; Save-Status
$onlyArgs = @(); foreach ($m in $Models) { $onlyArgs += @('--only', $m) }
if ($ModelsJson) {
    $registryPath = $ModelsJson
    Write-Log "Bruker ferdig modelliste $ModelsJson"
} else {
    Write-Log 'Laster ned modeller'
    & $Py scripts/download_models.py --out models/benchmark @onlyArgs *>> $Detail
    $registryPath = Join-Path $Root 'models/benchmark/models.json'
}
if (-not (Test-Path $registryPath)) { Stop-WithError 'models.json mangler etter nedlasting' }
$registry = Get-Content $registryPath -Raw | ConvertFrom-Json

# ---------- 3. Stillhetssett og egne opptak
& $Py -m nsb_eval.silence --out-dir eval/testsets/silence_v1 *>> $Detail
if ($LASTEXITCODE -ne 0) { Stop-WithError 'Kunne ikke lage stillhetssettet' }
foreach ($ts in @($Testsets | Where-Object { $_ -in @('legal_dictation_v1', 'simulated_interview_v1') })) {
    & $Py -m nsb_eval.recorded --root $Root --set $ts *>> $Detail
    if ($LASTEXITCODE -ne 0) { Stop-WithError "Ingen (verifiserte) opptak i eval/recording/$ts" }
}
$preflightArgs = @(); foreach ($ts in $Testsets) { $preflightArgs += @('--testset', $ts) }
if ($Limit -gt 0) { $preflightArgs += @('--limit', "$Limit") }
& $Py -m nsb_eval.preflight --root $Root @preflightArgs *>> $Detail
if ($LASTEXITCODE -ne 0) { Stop-WithError 'Lydfiler mangler for et eller flere testsett (se RUN.detail.log, linjer med [mangler])' }

function Get-TestsetArgs([string]$Name) {
    if ($Name -eq 'legal_dictation_v1') {
        return @('--manifest', 'eval/recording/legal_dictation_v1/all.jsonl', '--audio-root', $Root, '--group-by', 'speaker_id', '--group-by', 'category')
    }
    if ($Name -eq 'simulated_interview_v1') {
        return @('--manifest', 'eval/recording/simulated_interview_v1/all.jsonl', '--audio-root', $Root, '--group-by', 'group')
    }
    if ($Name -eq 'silence_v1') {
        return @('--manifest', 'eval/testsets/silence_v1/manifest.jsonl', '--audio-root', 'eval/testsets/silence_v1')
    }
    return @('--manifest', "eval/testsets/$Name.jsonl", '--audio-root', $Root, '--group-by', 'dialect', '--group-by', 'standard')
}

# ---------- 4. GPU-sjekk
$firstModel = $Models | Where-Object { $registry.$_.path } | Select-Object -First 1
if (-not $firstModel) { Stop-WithError 'Ingen modeller ble lastet ned' }
if ($Device -eq 'cuda') {
    $probe = Join-Path $Results '_gpu_probe'
    if (Test-Path $probe) { Remove-Item -Recurse -Force $probe }
    & $Py -m nsb_eval.runner @(Get-TestsetArgs 'npsc_test_20170207') --limit 3 --testset gpu_probe --backend faster-whisper `
        --model $registry.$firstModel.path --label $firstModel --device cuda --compute-type $ComputeType --out-dir $probe *>> $Detail
    if ($LASTEXITCODE -ne 0) {
        $probeErrors = @()
        $probeItems = Join-Path $probe 'items.jsonl'
        if (Test-Path $probeItems) {
            $probeErrors = @(Get-Content $probeItems | Where-Object { $_.Trim() } | ForEach-Object { ($_ | ConvertFrom-Json).error } | Where-Object { $_ })
        }
        $cudaLike = @($probeErrors | Where-Object { $_ -match 'cuda|cublas|cudnn|nvrtc|\.dll|GPU|device' })
        if ($probeErrors.Count -gt 0 -and $cudaLike.Count -eq 0) {
            Stop-WithError "GPU-sjekken feilet av en annen grunn enn CUDA: $($probeErrors[0])"
        }
        Write-Log "GPU virker ikke ($(if ($cudaLike) { $cudaLike[0] } else { 'se RUN.detail.log' })). Bytter til CPU int8; det tar vesentlig lengre tid."
        $Device = 'cpu'; $ComputeType = 'int8'
        $status.device = $Device; $status.compute_type = $ComputeType
    } else {
        Write-Log 'GPU virker'
    }
    if (Test-Path $probe) { Remove-Item -Recurse -Force $probe }
}

# ---------- 5. Målinger
$status.phase = 'evaluate'; Save-Status
$failedJobs = 0
foreach ($m in $Models) {
    $entry = $registry.$m
    if (-not $entry.path) {
        $status.jobs["$m"] = [ordered]@{ state = 'skipped'; reason = "$($entry.error)" }
        $failedJobs++
        Write-Log "Hopper over ${m}: $($entry.error)"
        Save-Status
        continue
    }
    foreach ($ts in $Testsets) {
        $tsLabel = "$ts$TestsetSuffix"
        $key = "$tsLabel/$m"
        $out = Join-Path (Join-Path $JobRoot $tsLabel) $m
        New-Item -ItemType Directory -Force -Path $out | Out-Null
        $status.jobs[$key] = [ordered]@{ state = 'running'; started = (Get-Date).ToString('o') }
        Save-Status
        Write-Log "Kjører $key på $Device/$ComputeType"
        $limitArgs = @(); if ($Limit -gt 0) { $limitArgs = @('--limit', "$Limit") }
        if ($entry.revision) { $limitArgs += @('--model-revision', "$($entry.revision)") }
        if ($entry.model_sha256) { $limitArgs += @('--model-sha256', "$($entry.model_sha256)") }
        if ($LanguageFromMeta) { $limitArgs += @('--language-from-meta', 'standard') }
        if ($Vad) { $limitArgs += @('--vad') }
        & $Py -m nsb_eval.runner @(Get-TestsetArgs $ts) --testset $tsLabel --backend faster-whisper --model $entry.path --label $m `
            --device $Device --compute-type $ComputeType --out-dir $out @limitArgs *>> (Join-Path $out 'run.log')
        $code = $LASTEXITCODE
        if ($code -ne 0) { $failedJobs++ }
        $summaryPath = Join-Path $out 'summary.json'
        $job = [ordered]@{ state = $(if ($code -eq 0) { 'done' } else { 'failed' }); exit_code = $code; finished = (Get-Date).ToString('o') }
        if (Test-Path $summaryPath) {
            $s = Get-Content $summaryPath -Raw | ConvertFrom-Json
            $job.wer = $s.speech.wer
            $job.items_failed = $s.items_failed
            if ($s.silence) { $job.silence_hallucination_rate = $s.silence.hallucination_on_silence_rate }
        }
        $status.jobs[$key] = $job
        Save-Status
        Write-Log ("Ferdig {0}: exit {1}, WER {2}" -f $key, $code, $job.wer)
    }
}

# ---------- 6. Rapport
$status.phase = 'report'; Save-Status
& $Py -m nsb_eval.report --results eval/results --out eval/results/BENCHMARK.md *>> $Detail
if ($LASTEXITCODE -ne 0) { Stop-WithError 'Rapporten kunne ikke lages; se RUN.detail.log' }
$status.phase = $(if ($failedJobs -gt 0) { 'done_with_failures' } else { 'done' })
$status.failed_jobs = $failedJobs
$status.finished = (Get-Date).ToString('o')
Save-Status
if ($failedJobs -gt 0) {
    Write-Log "Ferdig med $failedJobs feilede jobber. Se RUN_STATUS.json og run.log i hver resultatmappe."
    exit 1
}
Write-Log 'Ferdig. Se eval/results/BENCHMARK.md'
exit 0
