<#
.SYNOPSIS
  Måler dekodingsprofiler mot gjentakelsesløkker for dialekt_v1 på valideringssettene.
  Se docs/experiments/LOOPVAKT_V1.md. Den låste testen brukes ikke.
#>
param([string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path)
$ErrorActionPreference = 'Continue'
Set-Location $Root
$Out = Join-Path $Root 'eval/results/loopvakt_v1'
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Log = Join-Path $Out 'RUN.log'; $Detail = Join-Path $Out 'RUN.detail.log'
function Write-Log([string]$m) { $l = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m; Write-Host $l; Add-Content -Path $Log -Value $l -Encoding utf8 }
$env:PYTHONIOENCODING = 'utf-8'; $env:PYTHONUTF8 = '1'; $env:PYTHONPATH = $Root; $env:HF_HUB_OFFLINE = '1'
$Bench = Join-Path $Root '.venv-bench/Scripts/python.exe'
$Model = Join-Path $Root 'models/finetuned/dialekt_v1/ct2'
if (-not (Test-Path (Join-Path $Model 'model.bin'))) { Write-Log "FEIL: fant ikke $Model"; exit 1 }
$site = (& $Bench -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
foreach ($sub in @('nvidia/cublas/bin', 'nvidia/cudnn/bin', 'nvidia/cuda_nvrtc/bin', 'nvidia/cuda_runtime/bin')) {
    $p = Join-Path $site $sub; if (Test-Path $p) { $env:PATH = "$p;$env:PATH" }
}
$failed = $false
foreach ($dec in @('loopvakt', 'loopvakt_ngram')) {
    $jobs = @(
        @('nb_samtale_spk_dev', @('--manifest', 'eval/testsets/nb_samtale_spk_dev.jsonl', '--audio-root', $Root, '--language-from-meta', 'standard', '--group-by', 'standard')),
        @('npsc_eval_20170209', @('--manifest', 'eval/testsets/npsc_eval_20170209.jsonl', '--audio-root', $Root)),
        @('silence_v1', @('--manifest', 'eval/testsets/silence_v1/manifest.jsonl', '--audio-root', 'eval/testsets/silence_v1', '--vad'))
    )
    foreach ($j in $jobs) {
        $ts, $tsArgs = $j
        Write-Log "Måler dialekt_v1 med $dec på $ts"
        & $Bench -m nsb_eval.runner @tsArgs --testset $ts --backend faster-whisper --model $Model --label "dialekt_v1-$dec" `
            --decoding $dec --device cuda --compute-type float16 --out-dir (Join-Path $Out "$ts/dialekt_v1-$dec") *>> $Detail
        if ($LASTEXITCODE -ne 0) { Write-Log "FEIL i $dec på $ts (se RUN.detail.log)"; $failed = $true }
    }
}
if ($failed) { Write-Log 'Ikke fullført. Kjør igjen; ferdige setninger hoppes over.'; exit 1 }
Write-Log "Ferdig. Resultater: $Out"
