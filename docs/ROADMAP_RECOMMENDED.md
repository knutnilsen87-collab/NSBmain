# NorwegianSpeechBase — Recommended Roadmap

## Phase 1 — Stabilize the green baseline
- Lock .\nsb-speak.ps1 as canonical speak entrypoint
- Keep .\nsb.ps1 speak as secondary/experimental until explicitly verified
- Keep device_index=1 / 44100 / 2ch as canonical baseline
- Keep CPU-safe transcription baseline as default
- Preserve distinction between bundle status and speech status

## Phase 2 — Hardening and regression protection
- Add preflight checks for venv, python packages, config, device resolution
- Standardize failure taxonomy in code and status
- Add one-command verification against known_good_speak_run.json
- Ensure transcribe.json always exists even on failure
- Standardize UTF-8 encoding

## Phase 3 — Operator productization
- Improve status and health output
- Make latest known-good reference easier to inspect
- Show device, engine, and speech-vs-bundle state clearly
- Align docs and terminal messaging

## Phase 4 — Controlled quality and performance improvements
- Test GPU as opt-in, not as default
- Benchmark CPU-safe baseline vs alternatives
- Test multiple known Norwegian phrases
- Compare WER/CER across models

## Phase 5 — Optional v2 expansion
- Support .\nsb.ps1 speak fully
- Add more microphones/hosts
- Improve dashboarding and release process

## Recommended execution order
1. Lock baseline
2. Add regression protection
3. Improve operator UX
4. Benchmark improvements
5. Expand scope later
