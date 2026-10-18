# NorwegianSpeechBase (NSB)

Norsk talegjenkjenning med etterprøvbar kvalitet: en fast, åpen målestokk for norske talemodeller, et pilot-API for transkribering og verktøy for å trene og tilpasse NB-Whisper.

Status oktober 2026: fase 0 (opprydding) er ferdig. Fase 1 (målestokk) er delvis ferdig; se [status krav for krav](docs/PHASE1_STATUS.md). Første måling er kjørt 2026-10-16: fem modeller på fire faste testsett, se [analysen](eval/results/ANALYSIS.md) og [tabellene](eval/results/BENCHMARK.md). NB-Whisper large distil-turbo er kandidat for diktering, men er ikke målt på juridisk diktat ennå. Godkjenningskravene står i [ACCEPTANCE_CRITERIA.md](docs/ACCEPTANCE_CRITERIA.md) (forslag). Fase 2 er startet: talemotoren `nsb-engine` med strømming, juridisk formatering og lokal tjeneste; se [ENGINE.md](docs/ENGINE.md) og [status for fase 2](docs/PHASE2_STATUS.md).

## Innhold

| Mappe | Hva |
| --- | --- |
| `nsb_engine/` | Talemotoren: strømmende gjenkjenning, juridisk formatering og lokal tjeneste (HTTP og WebSocket); se [ENGINE.md](docs/ENGINE.md) |
| `nsb_eval/` | Målestokken: norsk normalisering, WER/CER, hallusinasjonsmål, kjører, forhåndssjekk, omscoring, rapport og parvis sammenligning (`compare`) |
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

## Talemotor

```powershell
scripts\RUN_ENGINE.cmd              # starter tjenesten og testsiden på http://127.0.0.1:8765/
scripts\RUN_STREAMING_CHECK.cmd     # måler ventetid, endringer og ordsikkerhet
```

## Pilot-API

```powershell
cd apps\pilot-asr-api
pip install -r requirements.dev.txt
python -m pytest tests
.\scripts\run_pilot_asr_api.ps1 -Backend faster-whisper -ModelName medium -Port 8091
```

## Regler

Ingen data uten lisens i dataregisteret, ingen lydopptak eller nøkler i git, og ingen modell tas i bruk uten å være målt på de faste testsettene. Se [docs/SECURITY.md](docs/SECURITY.md).
