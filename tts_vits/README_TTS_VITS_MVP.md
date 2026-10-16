# TTS VITS MVP (NorwegianSpeechBase)

## Goal
Get a Norwegian VITS MVP running with a clean pipeline and a path to speaker conditioning using AudioEncoder_v2 embeddings.

## Quick start
1) Activate venv (optional; scripts use explicit venv python):
- F:\NorwegianSpeechBase\envs\tts_vits_env

2) Run CLI stub:
python tts_vits/tools/tts_generate.py --config tts_vits/config/vits_no_mvp.yaml --text \"Hei Norge!\"

## Data required for training
You need paired data:
- wavs/*.wav
- metadata.csv: wav_name|text

Place under:
tts_vits/data/dataset/

## Speaker conditioning
Plan is to use AudioEncoder_v2 embeddings (128-dim) and inject into VITS hidden states via projection.

See:
docs/vits_architecture_plan.md
