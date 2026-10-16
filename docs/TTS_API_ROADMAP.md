# NorwegianSpeechBase — TTS / Synthetic Voices / API Roadmap

## Current readiness
- STT/speak baseline is operational and protected by preflight/verify
- Supported host baseline is locked
- System is ready for TTS proof-of-concept work

## Recommended order
1. Build TTS baseline with one engine and one approved voice
2. Build API v1 around STT/TTS/health endpoints
3. Add controlled voice registry for synthetic voices
4. Benchmark quality, latency, and stability
5. Add external integration features (auth, limits, versioning)

## Engine strategy
- Piper: prefer for simple, local, operational TTS
- XTTS v2: prefer for voice cloning / multilingual synthetic voice work
- StyleTTS2: evaluate later, not as first production baseline

## API v1
- POST /stt/transcribe
- POST /tts/synthesize
- GET /health
- GET /voices
- GET /runs/{run_id}

## Governance
- No production synthetic voice without explicit consent/licensing metadata
- Keep run-dir and status observability for all API calls
