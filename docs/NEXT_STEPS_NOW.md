# NorwegianSpeechBase — Next Steps

## Current state
- Golden path operationally stable enough
- Speak path has a locked known-good baseline
- Canonical entrypoint: .\nsb-speak.ps1
- Reference run locked in repo
- End product state and done marker already written

## Next steps
1. Freeze current baseline
2. Add one-command verify against reference\known_good_speak_run.json
3. Add preflight checks for venv, config, device, packages
4. Keep SPEAK_LAST_STATUS.json as speech truth source
5. Clean up UTF-8 encoding in status/text output
6. Treat GPU path as optional optimization, not default
7. Keep nsb.ps1 speak secondary until explicitly verified green

## Non-blocking later
- Better operator UX
- Better dashboard segmentation
- Optional GPU benchmarking
- Optional multi-device support
