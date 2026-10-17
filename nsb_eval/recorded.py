"""Samler egne opptak til ett testsett som kan måles.

Opptakene ligger lokalt (aldri i git) per taler eller økt:
``eval/recording/<sett>/<taler>/manifest.jsonl``. Denne modulen slår dem
sammen til ``eval/recording/<sett>/all.jsonl`` med lydstier relative til
repoets rot. Rader med ``verified: false`` tas ikke med.

    python -m nsb_eval.recorded --root . --set legal_dictation_v1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

RECORDED_SETS = ("legal_dictation_v1", "simulated_interview_v1")


def combined_manifest(root: Path, name: str) -> Path:
    return root / "eval" / "recording" / name / "all.jsonl"


def collect(root: Path, name: str) -> dict:
    """Skriver all.jsonl og returnerer antall rader per taler/økt."""
    if name not in RECORDED_SETS:
        raise ValueError(f"Ukjent opptakssett {name!r}; kjente: {RECORDED_SETS}")
    base = root / "eval" / "recording" / name
    counts: dict[str, int] = {}
    skipped = 0
    rows = []
    for manifest in sorted(base.glob("*/manifest.jsonl")):
        group = manifest.parent.name
        for line in manifest.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("verified") is False:
                skipped += 1
                continue
            row.setdefault("speaker_id", group)
            row["group"] = group
            rows.append(row)
            counts[group] = counts.get(group, 0) + 1
    out = combined_manifest(root, name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return {"set": name, "rows": len(rows), "groups": counts, "unverified_skipped": skipped, "manifest": str(out)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--set", required=True, choices=RECORDED_SETS)
    args = ap.parse_args(argv)
    r = collect(Path(args.root), args.set)
    print(f"[ok] {r['set']}: {r['rows']} opptak fra {len(r['groups'])} talere/økter "
          f"({', '.join(f'{k}: {v}' for k, v in r['groups'].items()) or 'ingen'}); "
          f"{r['unverified_skipped']} uverifiserte hoppet over -> {r['manifest']}")
    return 0 if r["rows"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
