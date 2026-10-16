# Repo Hygiene

This repository historically mixed source code with local runtime output, archives, backups, and machine-specific files.

The cleanup policy from this point is:

- Keep source code, configuration, contracts, schemas, and intentional documentation in git.
- Keep generated dependencies out of git. Install them locally instead of tracking `node_modules/`.
- Keep local runtime output out of git: logs, temp files, build output, state snapshots, caches, and virtual environments.
- Keep ad hoc archives out of git: `*.zip`, `*.torrent`, export bundles, and one-off handoff packages.
- Keep binary office exports out of git. Convert durable project documentation to Markdown under `docs/`.
- Keep editor and OS noise out of git: `desktop.ini`, `Thumbs.db`, `.DS_Store`, IDE folders.
- Keep timestamped backup files out of git. If a rollback is important, convert it into a named document or a real commit.
- Keep private keys and generated signatures out of git. Public keys may be tracked when they are part of a documented verification flow.

Cleanup performed on 2026-06-04:

- Local archive/docx/torrent bundles, tracked backup files, runtime state, model run output, training logs, generated signatures, and private keys were moved to `NorwegianSpeechBase_local_quarantine/cleanup_20260604/`.
- The already-missing tracked `logs/`, `logs_v3/`, `logs_adb_debug/`, `rollback/`, and `temp/` files should remain removed from git.
- `.gitignore` now explicitly blocks the recurring generated and local-only categories.

Known follow-up cleanup items:

- Rotate any private keys that were ever used outside local testing, because private key material has historically been present in the repository.
- Review whether the duplicate frontend roots (`frontend/` and root-level `src/`) should be consolidated.
- Review whether root-level operational scripts should live under `scripts/`, `service/`, or `ops/` consistently.
- `frontend` should be kept as ordinary source files in this repository unless it is deliberately split into its own public repository with a valid `.gitmodules` entry.
