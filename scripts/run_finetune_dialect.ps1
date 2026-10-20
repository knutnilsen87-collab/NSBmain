<#
.SYNOPSIS
  Første treningsforsøk: NB-Whisper distil-turbo på dialekt og nynorsk (dialekt_v1).

.DESCRIPTION
  1. Bygger treningsdata (NB Samtale train + NPSC train), uten låste testsett.
  2. Trener i .venv (torch med CUDA). Kan avbrytes og startes igjen; fortsetter fra siste checkpoint.
  3. Konverterer beste checkpoint til CTranslate2 og retter ordtidshodene.
  4. Måler utgangsmodell og ny modell på VALIDERINGSSETTENE (NB Samtale spk_dev, NPSC eval),
     aldri på de låste testsettene, og sammenligner med parvis bootstrap.
  Logg: runs/dialekt_v1/RUN.log. Resultater: eval/results/finetune_dialekt_v1.
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [int]$BatchSize = 4,
    [int]$GradAccum = 8,
    [int]$MaxSteps = 1500,
    [int]$EvalSteps = 250,
    [int]$FreezeLayers = 24,
    [double]$LearningRate = 1e-5,
    [switch]$SkipTrain
)
$ErrorActionPreference = 'Continue'
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
Set-Location $Root
$Name = 'dialekt_v1'
$Run = Join-Path $Root "runs/$Name"
New-Item -ItemType Directory -Force -Path $Run | Out-Null
$Log = Join-Path $Run 'RUN.log'
$Detail = Join-Path $Run 'RUN.detail.log'
function Write-Log([string]$Message) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    for ($i = 0; $i -lt 10; $i++) {
        try { Add-Content -Path $Log -Value $line -Encoding utf8 -ErrorAction Stop; return } catch { Start-Sleep -Milliseconds 300 }
    }
}
function Stop-WithError([string]$Message) { Write-Log "FEIL: $Message"; exit 1 }

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = "$Root;$(Join-Path $Root 'src/python')"
$env:HF_HUB_OFFLINE = '1'
$Train = Join-Path $Root '.venv/Scripts/python.exe'
$Bench = Join-Path $Root '.venv-bench/Scripts/python.exe'
if (-not (Test-Path $Train)) { Stop-WithError 'Fant ikke .venv (treningsmiljøet med torch).' }
if (-not (Test-Path $Bench)) { Stop-WithError 'Fant ikke .venv-bench. Kjør scripts\RUN_BENCHMARK.cmd først.' }
$Base = Join-Path $Root 'models/benchmark/nb-whisper-large-distil-turbo-beta/hf'
$BaseCt2 = Join-Path $Root 'models/benchmark/nb-whisper-large-distil-turbo-beta/ct2_converted'
if (-not (Test-Path (Join-Path $Base 'model.safetensors'))) { Stop-WithError "Fant ikke $Base" }

# ---------- 0. Miljø
Write-Log 'Sjekker treningsmiljøet'
& $Train -m pip install --quiet soundfile "ctranslate2==4.8.3" *>> $Detail
$cuda = (& $Train -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')").Trim()
Write-Log "torch CUDA: $cuda"
if (-not $cuda.StartsWith('True')) { Stop-WithError 'torch finner ikke skjermkortet i .venv' }

# ---------- 1. Data
$Data = Join-Path $Root "data/finetune/$Name"
if (-not (Test-Path (Join-Path $Data 'train.jsonl'))) {
    Write-Log 'Bygger treningsdata'
    & $Train scripts/build_finetune_dialect.py --root $Root --out $Data *>> $Detail
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'Kunne ikke bygge treningsdata (se RUN.detail.log)' }
}
$stats = Get-Content (Join-Path $Data 'stats.json') -Raw | ConvertFrom-Json
Write-Log ("Trening: {0} segmenter ({1}), validering: {2}" -f $stats.train.rows, (($stats.train.by_language | ConvertTo-Json -Compress)), $stats.val.rows)

# ---------- 2. Trening
if (-not $SkipTrain) {
    Write-Log "Trener: $MaxSteps steg, batch $BatchSize x $GradAccum, $FreezeLayers frosne koderlag (kan ta flere timer)"
    & $Train src/python/train_whisper_iterable.py --train_jsonl (Join-Path $Data 'train.jsonl') `
        --val_jsonl (Join-Path $Data 'val.jsonl') --out_dir $Run --model_name $Base --language no `
        --val_languages no,nn --bf16 --batch_size $BatchSize --grad_accum $GradAccum `
        --freeze_encoder_layers $FreezeLayers --gradient_checkpointing --spec_augment --lr $LearningRate `
        --warmup_steps 150 --max_steps $MaxSteps --eval_steps $EvalSteps --save_steps $EvalSteps --keep_last 2 `
        --limit_val 500 --eval_at_start --resume *>> $Detail
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'Treningen stoppet (se RUN.detail.log). Kjør skriptet igjen for å fortsette fra siste checkpoint.' }
}
$best = Join-Path $Run 'best'
if (-not (Test-Path (Join-Path $best 'config.json'))) { Stop-WithError 'Fant ikke beste checkpoint' }
$bm = Get-Content (Join-Path $Run 'best_metrics.json') -Raw | ConvertFrom-Json
$b0 = Get-Content (Join-Path $Run 'baseline_metrics.json') -Raw | ConvertFrom-Json
Write-Log ("Validering under trening: utgangsmodell {0:P1} (bokmål {1:P1}, nynorsk {2:P1}); beste steg {3}: {4:P1} (bokmål {5:P1}, nynorsk {6:P1})" -f `
    $b0.wer, $b0.wer_no, $b0.wer_nn, $bm.step, $bm.wer, $bm.wer_no, $bm.wer_nn)

# ---------- 3. Konvertering
$Ct2 = Join-Path $Root "models/finetuned/$Name/ct2"
if (-not (Test-Path (Join-Path $Ct2 'model.bin'))) {
    Write-Log 'Konverterer til CTranslate2'
    # Via python -m: .venv ble flyttet, og .exe-oppstarterne peker på den gamle stien.
    & $Train -m ctranslate2.converters.transformers --model $best --output_dir $Ct2 --copy_files tokenizer.json preprocessor_config.json --quantization float16 --force *>> $Detail
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'Konverteringen feilet' }
    & $Train -c "import sys; sys.path.insert(0, 'scripts'); from pathlib import Path; from download_models import fix_alignment_heads; print(fix_alignment_heads(Path(r'$Ct2'), Path(r'$best')))" *>> $Detail
}

# ---------- 4. Måling på validering
$site = (& $Bench -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
foreach ($sub in @('nvidia/cublas/bin', 'nvidia/cudnn/bin', 'nvidia/cuda_nvrtc/bin', 'nvidia/cuda_runtime/bin')) {
    $p = Join-Path $site $sub
    if (Test-Path $p) { $env:PATH = "$p;$env:PATH" }
}
$Out = Join-Path $Root "eval/results/finetune_$Name"
$jobs = @(
    @('nb_samtale_spk_dev', 'distil-turbo-utgangspunkt', $BaseCt2, @()),
    @('nb_samtale_spk_dev', 'distil-turbo-utgangspunkt-maalform', $BaseCt2, @('--language-from-meta', 'standard')),
    @('nb_samtale_spk_dev', "distil-turbo-$Name", $Ct2, @('--language-from-meta', 'standard')),
    @('npsc_eval_20170209', 'distil-turbo-utgangspunkt', $BaseCt2, @()),
    @('npsc_eval_20170209', "distil-turbo-$Name", $Ct2, @())
)
foreach ($j in $jobs) {
    $ts, $label, $model, $extra = $j
    $dir = Join-Path $Out "$ts/$label"
    Write-Log "Måler $label på $ts"
    & $Bench -m nsb_eval.runner --manifest "eval/testsets/$ts.jsonl" --audio-root $Root --testset $ts `
        --backend faster-whisper --model $model --label $label --device cuda --compute-type float16 `
        --group-by dialect --group-by standard --out-dir $dir @extra *>> $Detail
    if ($LASTEXITCODE -ne 0) { Write-Log "FEIL i måling av $label på $ts (se RUN.detail.log)" }
}
foreach ($ts in @('nb_samtale_spk_dev', 'npsc_eval_20170209')) {
    & $Bench -m nsb_eval.compare --results $Out --testset $ts --baseline distil-turbo-utgangspunkt *>> (Join-Path $Out "compare_$ts.txt")
}
& $Bench -m nsb_eval.report --results eval/results --out eval/results/BENCHMARK.md *>> $Detail
Write-Log "Ferdig. Se $Out (compare_*.txt) og eval/results/BENCHMARK.md"
