# NorwegianSpeechBase – Methodology (ASR Evaluation)

## Purpose
NorwegianSpeechBase provides a stable, deterministic, and reproducible evaluation foundation for Norwegian ASR.
The goal is trustworthy WER numbers for comparison and decision-making, independent of legacy code.

## Core mental model (invariants)
Evaluation is **only**:
1. Read a manifest (JSONL)
2. Transcribe audio
3. Compute WER
4. Log results

Nothing else. No training. No “smart” heuristics in the evaluator.

## Data contract (manifest)
- Format: JSON Lines (one JSON object per line)
- Required fields:
  - udio_filepath (absolute path recommended on Windows)
  - 	ext (reference transcript)
- No extra fields are allowed for evaluation manifests (strict contract).

Manifest is a JSONL file with fields udio_filepath and 	ext.

## Evaluation runner (single source of truth)
- Canonical runner: scripts/run_eval_clean.py
- Legacy scripts (e.g. scripts/eval_npsc.py) must not be edited or used for official evaluation.

## Separation of concerns: eval vs training
- Evaluation uses **only** the evaluation split(s).
- Training must never use test data. Any leakage invalidates results.

## Determinism & reproducibility
A result is considered reproducible if:
- The same manifest (by SHA256) is evaluated
- The Python environment is pinned (venv + dependency snapshot)
- The same evaluation backend/model settings are used
- Logs and results are consistent

## Evidence pack (audit-ready baseline)
Each baseline is frozen into a folder under:
eports/baselines/<dataset>_<split>_<date>/

Minimum contents:
- manifest.jsonl + manifest.sha256
- source.txt (Språkbanken provenance: resource id/url + license)
- nv.txt (python executable + pip freeze)
- esults.json (machine-readable result contract)
- MAIN.log, TRACE.log, ULF.jsonl
- VERIFY_OK.txt (consistency checks passed)

## Operational convention
- The most recent run is always copied to:
  logs/LATEST/
- Start debugging from logs/LATEST/TRACE.log, then logs/LATEST/MAIN.log.

## Metrics
- Primary metric: Word Error Rate (WER)

Example (from last run in logs/LATEST):
- WER: 0.549054 (ok=1195 bad=0 items=1195 backend=faster-whisper)


## Data source
All datasets used for official baselines come from Språkbanken (Nasjonalbiblioteket) with documented provenance and licensing in each baseline folder.

## Non-goals (current phase)
- GPU optimization
- CI/CD
- Training pipelines
- Production API

## Failure modes (stop conditions)
Stop immediately if any of the following occur:
- MANIFEST_OK items=0
- "No usable (audio,text) pairs"
- Any indication that training data and test data have been mixed

---
Generated at: 2026-01-26T09:58:53.7008559+01:00
