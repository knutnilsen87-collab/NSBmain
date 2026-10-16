# pilot-asr-api

Isolert pilot-klar ASR API-scaffold.

## Hva dette gir
- `/v1/health`
- `/v1/readiness`
- `/v1/models`
- `/v1/version`
- `/v1/transcriptions/path`
- `/v1/transcriptions/upload`

## Kontrakt i dag
- `GET /v1/health`: liveness + backend/model-identitet
- `GET /v1/readiness`: readiness + modellastestatus
- `GET /v1/models`: valgt backend/modell/device
- `GET /v1/version`: tjenestenavn, versjon, backend, modell
- `POST /v1/transcriptions/path`: transkribering fra tilgjengelig filsti
- `POST /v1/transcriptions/upload`: transkribering fra opplastet lydfil

Transkripsjonsresponsene fra `path` og `upload` bruker samme kontrakt:

```json
{
  "backend": "faster-whisper",
  "model_name": "medium",
  "audio_source": "upload:example.wav",
  "language": "no",
  "transcript": "…",
  "segments": [],
  "notes": []
}
```

API-feil returneres strukturert via `detail`, med `error`, `detail`, `request_id` og eventuelt `extra`.

Eksempel:

```json
{
  "detail": {
    "error": "unsupported_media_type",
    "detail": "Unsupported audio file extension.",
    "request_id": "…",
    "extra": {
      "supported_extensions": [".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm", ".mp4"],
      "received_extension": ".txt"
    }
  }
}
```

## Upload-regler
- Maks størrelse styres av `ASR_MAX_UPLOAD_MB`
- Støttede filendelser er `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.webm`, `.mp4`
- Tom upload returnerer `400`
- For stor upload returnerer `413`
- Ustøttet filtype returnerer `415`

## Standardmodus
Standard backend er `mock`, slik at pilotprogrammet kan koble seg på uten at reell modell er installert ennå.

## Base setup
```powershell
cd F:\NorwegianSpeechBase\apps\pilot-asr-api
py -3 -m venv .venv-pilot-asr
.venv-pilot-asr\Scripts\python.exe -m pip install --upgrade pip
.venv-pilot-asr\Scripts\python.exe -m pip install -r requirements.base.txt
```

## Kjøring
```powershell
cd F:\NorwegianSpeechBase\apps\pilot-asr-api
.\scripts\run_pilot_asr_api.ps1 -Backend faster-whisper -ModelName medium -Port 8091
```

## Tester
```powershell
cd F:\NorwegianSpeechBase\apps\pilot-asr-api
.venv-pilot-asr-py312\Scripts\python.exe -m unittest discover -s tests -v
```
