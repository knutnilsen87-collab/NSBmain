# NorwegianSpeechBase (NSB)

Norsk talegjenkjenning med etterprøvbar kvalitet: en fast, åpen målestokk for norske talemodeller, et pilot-API for transkribering og verktøy for å trene og tilpasse NB-Whisper.

Status oktober 2026: fase 0 (opprydding) og fase 1 (målestokk) i [planen](https://claude.ai/code/artifact/0b3c098e-dbbd-4ebb-84b7-dad0a2f19f11). Første offentlige resultater ligger i [`eval/results/BENCHMARK.md`](eval/results/BENCHMARK.md) når målingen er kjørt.

## Innhold

| Mappe | Hva |
| --- | --- |
| `nsb_eval/` | Målestokken: norsk normalisering, WER/CER, hallusinasjonsmål, kjører, forhåndssjekk, omscoring og rapport |
| `eval/testsets/` | Faste testsett (NPSC, NB Samtale), låst med sjekksum |
| `eval/recording/` | Innspillingssett for juridisk diktering |
| `apps/pilot-asr-api/` | FastAPI-tjeneste for transkribering (mock eller faster-whisper), med Dockerfile |
| `src/python/` | Dataflyt og trening: `train_whisper_iterable.py`, `split_by_group.py`, `nsb_train_utils.py` |
| `scripts/` | `run_benchmark.ps1`, `download_models.py`, `build_testsets.py`, `rotate_signing_key.ps1`, opptaksverktøy |
| `docs/` | [Metode](docs/BENCHMARK_METHOD.md), [dataregister](docs/DATA_REGISTER.md), [sikkerhet](docs/SECURITY.md) |

Plattform-stillaset (runtime, packages, TTS-skjelett, frontend) ligger i grenen `archive/scaffold-2026-05`.

## Kom i gang

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest                         # over 100 tester, ingen modell nødvendig
```

Kjør målestokken på GPU (laster ned NB-Whisper og Whisper large-v3):

```powershell
pwsh -File scripts\run_benchmark.ps1
```

Mål én modell mot ett testsett:

```powershell
python -m nsb_eval.runner --manifest eval/testsets/npsc_test_20170207.jsonl --audio-root . `
  --model models/benchmark/nb-whisper-large/ct2 --label nb-whisper-large `
  --device cuda --compute-type float16 --out-dir eval/results/npsc_test_20170207/nb-whisper-large
```

Testsettene peker på lyd under `dataset/` (Språkbankens filer, ikke i git). Se [dataregisteret](docs/DATA_REGISTER.md) for kilder og lisenser.

## Pilot-API

```powershell
cd apps\pilot-asr-api
pip install -r requirements.dev.txt
python -m pytest tests
.\scripts\run_pilot_asr_api.ps1 -Backend faster-whisper -ModelName medium -Port 8091
```

## Regler

Ingen data uten lisens i dataregisteret, ingen lydopptak eller nøkler i git, og ingen modell tas i bruk uten å være målt på de faste testsettene. Se [docs/SECURITY.md](docs/SECURITY.md).
