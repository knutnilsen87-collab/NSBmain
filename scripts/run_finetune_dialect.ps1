<#
.SYNOPSIS
  Første treningsforsøk: NB-Whisper distil-turbo på dialekt og nynorsk (dialekt_v1).

.DESCRIPTION
  1. Bygger treningsdata (NB Samtale train + NPSC train), uten låste testsett.
  2. Trener i .venv-train (lages første gang, torch med CUDA). Kan avbrytes og startes igjen; fortsetter fra siste checkpoint.
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
    [switch]$SkipTrain,
    # Låst test: kjøres én gang, og bare etter at valideringskriteriene i docs/experiments/DIALEKT_V1.md er oppfylt.
    [switch]$LockedTest
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
$Bench = Join-Path $Root '.venv-bench/Scripts/python.exe'
if (-not (Test-Path $Bench)) { Stop-WithError 'Fant ikke .venv-bench. Kjør scripts\RUN_BENCHMARK.cmd først.' }
$Base = Join-Path $Root 'models/benchmark/nb-whisper-large-distil-turbo-beta/hf'
$BaseCt2 = Join-Path $Root 'models/benchmark/nb-whisper-large-distil-turbo-beta/ct2_converted'
if (-not (Test-Path (Join-Path $Base 'model.safetensors'))) { Stop-WithError "Fant ikke $Base" }

# ---------- 0. Treningsmiljø (.venv-train)
# De gamle miljøene .venv og .venv311 peker på Python-installasjoner som ikke
# finnes lenger. Treningen får sitt eget miljø, laget fra samme Python 3.11
# som .venv-bench, med torch for CUDA.
$TrainVenv = Join-Path $Root '.venv-train'
$Train = Join-Path $TrainVenv 'Scripts/python.exe'
if (-not (Test-Path $Train)) {
    Write-Log 'Lager .venv-train med Python 3.11'
    & py -3.11 -m venv $TrainVenv *>> $Detail
    if (-not (Test-Path $Train)) { Stop-WithError "Kunne ikke lage .venv-train med 'py -3.11'" }
}
$ok = (& $Train -c "import torch, transformers, librosa, soundfile, ctranslate2; print('ok')" 2>$null)
if ("$ok".Trim() -ne 'ok') {
    Write-Log 'Installerer torch med CUDA, transformers og lydbiblioteker (omtrent 3 GB, kan ta 10-20 minutter)'
    & $Train -m pip install --upgrade pip *>> $Detail
    & $Train -m pip install torch --index-url https://download.pytorch.org/whl/cu126 *>> $Detail
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'Kunne ikke installere torch (se RUN.detail.log)' }
    & $Train -m pip install "transformers>=4.57" safetensors numpy tqdm soundfile librosa "ctranslate2==4.8.3" *>> $Detail
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'Kunne ikke installere transformers m.m. (se RUN.detail.log)' }
}
$cuda = "$(& $Train -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')")".Trim()
Write-Log "torch CUDA: $cuda"
if (-not $cuda.StartsWith('True')) { Stop-WithError 'torch finner ikke skjermkortet i .venv-train' }

# ---------- 1. Data
$Data = Join-Path $Root "data/finetune/$Name"
# Bygg på nytt hvis dataene mangler eller er laget av en eldre versjon av byggeskriptet.
$want = "$(& $Train -c "import sys; sys.path.insert(0, 'scripts'); import build_finetune_dialect as b; print(b.BUILDER_VERSION)")".Trim()
$have = "$(& $Train -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8')).get('builder_version', 1))" (Join-Path $Data 'stats.json') 2>$null)".Trim()
if (-not (Test-Path (Join-Path $Data 'train.jsonl')) -or $want -ne $have) {
    Write-Log "Bygger treningsdata (versjon $want)"
    & $Train scripts/build_finetune_dialect.py --root $Root --out $Data *>> $Detail
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'Kunne ikke bygge treningsdata (se RUN.detail.log)' }
}
$summary = "$(& $Train -c "import json,sys; s=json.load(open(sys.argv[1], encoding='utf-8')); print('Trening: %d segmenter (nynorsk %d), validering: %d' % (s['train']['rows'], s['train']['by_language'].get('nn', 0), s['val']['rows']))" (Join-Path $Data 'stats.json'))"
Write-Log $summary

# ---------- 2. Trening
if (-not $SkipTrain -and -not $LockedTest) {
    Write-Log "Trener: $MaxSteps steg, batch $BatchSize x $GradAccum, $FreezeLayers frosne koderlag (kan ta flere timer)"
    # Stopper treningen uten feilmelding fra Python (Windows avslutter prosessen,
    # for eksempel ved lite minne under lagring), startes den igjen fra siste
    # checkpoint, opptil fem ganger.
    for ($try = 1; $try -le 6; $try++) {
        & $Train src/python/train_whisper_iterable.py --train_jsonl (Join-Path $Data 'train.jsonl') `
            --val_jsonl (Join-Path $Data 'val.jsonl') --out_dir $Run --model_name $Base --language no `
            --val_languages no,nn --bf16 --batch_size $BatchSize --grad_accum $GradAccum `
            --freeze_encoder_layers $FreezeLayers --gradient_checkpointing --spec_augment --lr $LearningRate `
            --warmup_steps 150 --max_steps $MaxSteps --eval_steps $EvalSteps --save_steps $EvalSteps --keep_last 2 `
            --limit_val 500 --eval_at_start --resume *>> $Detail
        $code = $LASTEXITCODE
        if ($code -eq 0) { break }
        $hex = '0x{0:X8}' -f ([int64]$code -band 0xFFFFFFFF)
        if ($try -eq 6) { Stop-WithError "Treningen stoppet seks ganger (siste avslutningskode $code / $hex). Se RUN.detail.log." }
        Write-Log "Treningen stoppet (avslutningskode $code / $hex). Starter igjen fra siste checkpoint om 30 sekunder ($try av 5)."
        Start-Sleep -Seconds 30
    }
}
$best = "$(& $Train -c "import sys; sys.path.insert(0, 'src/python'); from train_whisper_iterable import best_dir; print(best_dir(sys.argv[1]))" $Run)".Trim()
if (-not (Test-Path (Join-Path $best 'config.json'))) { Stop-WithError 'Fant ikke beste checkpoint' }
$bm = Get-Content (Join-Path $Run 'best_metrics.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$b0 = Get-Content (Join-Path $Run 'baseline_metrics.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Log ("Validering under trening: utgangsmodell {0:P1} (bokmål {1:P1}, nynorsk {2:P1}); beste steg {3}: {4:P1} (bokmål {5:P1}, nynorsk {6:P1})" -f `
    $b0.wer, $b0.wer_no, $b0.wer_nn, $bm.step, $bm.wer, $bm.wer_no, $bm.wer_nn)

# ---------- 3. Konvertering
$Ct2 = Join-Path $Root "models/finetuned/$Name/ct2"
if (-not (Test-Path (Join-Path $Ct2 'model.bin'))) {
    Write-Log 'Konverterer til CTranslate2'
    # transformers 5 lagrer ikke preprocessor_config.json; den er lik utgangsmodellens (128 mel-bånd).
    if (-not (Test-Path (Join-Path $best 'preprocessor_config.json'))) { Copy-Item (Join-Path $Base 'preprocessor_config.json') $best }
    # Via python -m: .venv ble flyttet, og .exe-oppstarterne peker på den gamle stien.
    & $Train -m ctranslate2.converters.transformers --model $best --output_dir $Ct2 --copy_files tokenizer.json preprocessor_config.json --quantization float16 --force *>> $Detail
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'Konverteringen feilet' }
    & $Train -c "import sys; sys.path.insert(0, 'scripts'); from pathlib import Path; from download_models import fix_alignment_heads; print(fix_alignment_heads(Path(r'$Ct2'), Path(r'$best')))" *>> $Detail
}

# ---------- 4b. Låst test (én gang)
if ($LockedTest) {
    $Locked = Join-Path $Root "eval/results/finetune_${Name}_locked"
    $Marker = Join-Path $Locked 'DONE'
    if (Test-Path $Marker) { Stop-WithError "Den låste testen er allerede kjørt ($Marker). Den kjøres bare én gang per kandidat." }
    $site = (& $Bench -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
    foreach ($sub in @('nvidia/cublas/bin', 'nvidia/cudnn/bin', 'nvidia/cuda_nvrtc/bin', 'nvidia/cuda_runtime/bin')) {
        $p = Join-Path $site $sub
        if (Test-Path $p) { $env:PATH = "$p;$env:PATH" }
    }
    if (-not (Test-Path 'eval/testsets/silence_v1/manifest.jsonl')) { & $Bench -m nsb_eval.silence --out-dir eval/testsets/silence_v1 *>> $Detail }
    $ljobs = @(
        @('nb_samtale_spk_test', 'distil-turbo-utgangspunkt', $BaseCt2, @(), @('--manifest', 'eval/testsets/nb_samtale_spk_test.jsonl', '--audio-root', $Root, '--group-by', 'dialect', '--group-by', 'standard')),
        @('nb_samtale_spk_test', "distil-turbo-$Name", $Ct2, @('--language-from-meta', 'standard'), @('--manifest', 'eval/testsets/nb_samtale_spk_test.jsonl', '--audio-root', $Root, '--group-by', 'dialect', '--group-by', 'standard')),
        @('npsc_test_20170207', 'distil-turbo-utgangspunkt', $BaseCt2, @(), @('--manifest', 'eval/testsets/npsc_test_20170207.jsonl', '--audio-root', $Root)),
        @('npsc_test_20170207', "distil-turbo-$Name", $Ct2, @(), @('--manifest', 'eval/testsets/npsc_test_20170207.jsonl', '--audio-root', $Root)),
        @('silence_v1', "distil-turbo-$Name-vad", $Ct2, @('--vad'), @('--manifest', 'eval/testsets/silence_v1/manifest.jsonl', '--audio-root', 'eval/testsets/silence_v1'))
    )
    $failed = $false
    foreach ($j in $ljobs) {
        $ts, $label, $model, $extra, $tsArgs = $j
        Write-Log "Låst test: $label på $ts"
        & $Bench -m nsb_eval.runner @tsArgs --testset $ts --backend faster-whisper --model $model --label $label `
            --device cuda --compute-type float16 --out-dir (Join-Path $Locked "$ts/$label") @extra *>> $Detail
        if ($LASTEXITCODE -ne 0) { Write-Log "FEIL i $label på $ts (se RUN.detail.log)"; $failed = $true }
    }
    if ($failed) { Stop-WithError 'Den låste testen ble ikke fullført. Kjør igjen; ferdige setninger hoppes over.' }
    foreach ($ts in @('nb_samtale_spk_test', 'npsc_test_20170207')) {
        & $Bench -m nsb_eval.compare --results $Locked --testset $ts --baseline distil-turbo-utgangspunkt *>> (Join-Path $Locked "compare_$ts.txt")
    }
    Set-Content -Path $Marker -Value (Get-Date -Format o) -Encoding utf8
    Write-Log "Låst test ferdig. Se $Locked (compare_*.txt)"
    exit 0
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
