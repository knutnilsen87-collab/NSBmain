# NorwegianSpeechBase — End Product State

Validated at: 2026-03-06T23:31:00

## Canonical supported voice path
- Entrypoint: .\nsb-speak.ps1
- Host: Windows 10
- Shell: PowerShell 7.x
- Venv: .\.venv\nsb_whisper
- Mic: Yeti X
- Device index: 1
- Sample rate: 44100
- Channels: 2

## Verified last good speak run
- Run dir: F:\NorwegianSpeechBase\logs\runs\speak_20260306_231234
- Speech status: GREEN
- Bundle status: GREEN
- Engine: faster_whisper_cpu_int8
- Model: small
- Compute: int8

## Acceptance summary
- mic.wav exists: True
- transcribe.json exists: True
- hyp present: True
- blocked reason: none
- transcribe ok: True
- metrics status: ok

## Canonical truth files
- runtime\known_good_manifest.json
- reference\known_good_speak_run.json
- reference\known_good_golden_run.json
- logs\LATEST\SPEAK_LAST_STATUS.json
- logs\LATEST\FBL_STATUS_BUNDLE.txt
