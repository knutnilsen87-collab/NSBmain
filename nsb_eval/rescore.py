"""Regner resultater på nytt fra lagrede transkripsjoner, uten å kjøre modellene.

Brukes når normaliseringen eller feilmålene er endret. Leser
``items.jsonl`` i hver resultatmappe, scorer med gjeldende kode og skriver
``summary.json`` på nytt. Modell- og miljøfeltene fra den opprinnelige
kjøringen beholdes.

    python -m nsb_eval.rescore --results eval/results --models-json models/benchmark/models.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from .runner import NORMALIZER, rescore_rows, summarize


def _load_items(path: Path) -> list[dict]:
    rows: dict[str, dict] = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            prev = rows.get(row["id"])
            # Siste vellykkede rad vinner; en feilet rad overskriver aldri en vellykket.
            if prev is None or not row.get("error") or prev.get("error"):
                rows[row["id"]] = row
    return list(rows.values())


def rescore_dir(run_dir: Path, models: dict | None = None) -> dict:
    old = json.loads((run_dir / "summary.json").read_text(encoding="utf-8-sig"))
    rows = rescore_rows(_load_items(run_dir / "items.jsonl"))
    group_by = [k[3:] for k in old if k.startswith("by_")]
    keep = {k: v for k, v in old.items() if k in (
        "schema", "testset", "manifest", "manifest_sha256", "model", "started_utc", "finished_utc",
        "git_sha", "python", "platform",
    )}
    model = dict(keep.get("model") or {})
    entry = (models or {}).get(model.get("model") or "")
    if entry:
        for k in ("revision", "model_sha256"):
            if entry.get(k):
                model["model_revision" if k == "revision" else k] = entry[k]
    keep["model"] = model
    summary = {
        **keep,
        "normalizer": NORMALIZER,
        "rescored_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        **summarize(rows, group_by=group_by),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--models-json", default=None, help="models.json fra download_models.py (revisjon og sjekksum)")
    args = ap.parse_args(argv)
    models = None
    if args.models_json and Path(args.models_json).exists():
        models = json.loads(Path(args.models_json).read_text(encoding="utf-8-sig"))
    n = 0
    for summary_path in sorted(Path(args.results).glob("**/summary.json")):
        run_dir = summary_path.parent
        if not (run_dir / "items.jsonl").exists():
            continue
        s = rescore_dir(run_dir, models)
        n += 1
        print(f"{run_dir}: WER={s['speech']['wer']} feilet={s['items_failed']}")
    print(f"{n} resultatmapper scoret på nytt med {NORMALIZER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
