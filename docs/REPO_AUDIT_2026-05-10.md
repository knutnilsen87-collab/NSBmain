# Repository Audit - 2026-05-10

## Current State

- `main` is synchronized with `origin/main`.
- The repository contains a mix of source code, runtime logs, generated data,
  backups, local exports, and security artifacts.
- The most useful product code is split between the tracked TTS scaffold and
  local ASR/runtime prototypes.

## Decisions Applied

- Private key material must not be tracked.
- Generated logs, temporary data, archives, Python caches, local virtual
  environments, and export bundles should stay local.
- The Next frontend is treated as the canonical web frontend.
- `apps/pilot-asr-api`, `runtime`, and `tests/runtime` are the candidate
  product/runtime core for the next baseline.

## Follow-Up Risks

- Private keys that were already pushed should be rotated outside git.
- Old large objects still exist in git history until a deliberate history
  rewrite is performed.
- Real TTS inference is not implemented in `backend/main.py`; it still returns
  a minimal WAV stub.
