# Repo Hygiene

This repository currently mixes source code with local runtime output, archives, backups, and machine-specific files.

The cleanup policy from this point is:

- Keep source code, configuration, contracts, schemas, and intentional documentation in git.
- Keep generated dependencies out of git. Install them locally instead of tracking `node_modules/`.
- Keep local runtime output out of git: logs, temp files, build output, state snapshots, caches, and virtual environments.
- Keep ad hoc archives out of git: `*.zip`, `*.torrent`, export bundles, and one-off handoff packages.
- Keep editor and OS noise out of git: `desktop.ini`, `Thumbs.db`, `.DS_Store`, IDE folders.
- Keep timestamped backup files out of git. If a rollback is important, convert it into a named document or a real commit.

Known follow-up cleanup items that still need explicit review before broader removal:

- The repo contains many archived bundles and backup copies at the root and under `scripts/` and `rollback/`.
- `frontend` should be kept as ordinary source files in this repository unless it is deliberately split into its own public repository with a valid `.gitmodules` entry.
- The repository has historically tracked runtime logs and other generated assets. Those should be pruned in controlled batches, not blindly.
- There is a tracked private key under `FBL/security/keys/`. That should be audited and rotated if it has ever been used outside local testing.
