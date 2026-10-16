"""Deler et treningsmanifest i train/val/test per taler (eller opptak),
ikke per setning, og fjerner lekkasje mot de faste testsettene.

Den gamle splitten (``split_dataset.py``) hashet hver setning for seg. Da
havner samme taler, og i NST samme manus, både i trening og validering, og
valideringstallet måler pugging.

    python src/python/split_by_group.py --in data/manifest.trainable.jsonl \
        --out-dir build/splits_v2 --group-regex "(no\\d+x\\d+)" \
        --exclude-manifest eval/testsets/npsc_test_20170207.jsonl \
        --exclude-manifest eval/testsets/npsc_eval_20170209.jsonl \
        --exclude-manifest eval/testsets/nb_samtale_test.jsonl \
        --exclude-path-contains 20170207 --exclude-path-contains 20170209

Utelukkelse skjer på tre måter: samme lydfil (de tre siste leddene i stien),
samme fasittekst (minst fire ord, etter normalisering) og stier som inneholder
en oppgitt streng, for eksempel NPSC-møtedatoene.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nsb_eval.normalize import normalize  # noqa: E402
from nsb_train_utils import group_bucket  # noqa: E402

AUDIO_KEYS = ("audio", "path", "audio_filepath", "audio_path")


def _audio(row: dict) -> str:
    for k in AUDIO_KEYS:
        if row.get(k):
            return str(row[k])
    raise KeyError("mangler lydsti")


def _tail(path: str, parts: int = 3) -> str:
    return "/".join(path.replace("\\", "/").lower().split("/")[-parts:])


def group_of(row: dict, group_field: str | None, group_regex: str | None) -> str:
    if group_field and row.get(group_field) not in (None, ""):
        return str(row[group_field])
    audio = _audio(row).replace("\\", "/")
    if group_regex:
        m = re.search(group_regex, audio)
        if m:
            return m.group(1)
    return audio.rsplit("/", 2)[-2] if "/" in audio else audio


def split(
    rows: list[dict],
    val_pct: float,
    test_pct: float,
    group_field: str | None = None,
    group_regex: str | None = None,
    exclude_tails: set[str] | None = None,
    text_leakage: str = "drop-train",
    exclude_texts: set[str] | None = None,
    exclude_path_contains: list[str] | None = None,
) -> tuple[dict[str, list[dict]], dict]:
    report = Counter()
    out = {"train": [], "val": [], "test": []}
    val_cut = int(val_pct * 10)
    test_cut = val_cut + int(test_pct * 10)
    groups = {"train": set(), "val": set(), "test": set()}
    for row in rows:
        if exclude_tails and _tail(_audio(row)) in exclude_tails:
            report["excluded_fixed_testset"] += 1
            continue
        audio_norm = _audio(row).replace("\\", "/").lower()
        if exclude_path_contains and any(sub.lower() in audio_norm for sub in exclude_path_contains):
            report["excluded_path_match"] += 1
            continue
        if exclude_texts and normalize(row.get("text", "")) in exclude_texts:
            report["excluded_fixed_testset_text"] += 1
            continue
        g = group_of(row, group_field, group_regex)
        b = group_bucket(g, 1000)
        part = "val" if b < val_cut else "test" if b < test_cut else "train"
        out[part].append(row)
        groups[part].add(g)

    if text_leakage != "ignore":
        eval_texts = {normalize(r.get("text", "")) for p in ("val", "test") for r in out[p]}
        train_texts = {normalize(r.get("text", "")) for r in out["train"]}
        if text_leakage == "drop-train":
            kept = [r for r in out["train"] if normalize(r.get("text", "")) not in eval_texts]
            report["dropped_train_text_overlap"] = len(out["train"]) - len(kept)
            out["train"] = kept
        elif text_leakage == "drop-eval":
            for p in ("val", "test"):
                kept = [r for r in out[p] if normalize(r.get("text", "")) not in train_texts]
                report[f"dropped_{p}_text_overlap"] = len(out[p]) - len(kept)
                out[p] = kept
        else:
            raise ValueError(text_leakage)

    overlap = (groups["train"] & groups["val"]) | (groups["train"] & groups["test"]) | (groups["val"] & groups["test"])
    assert not overlap, f"grupper i flere deler: {sorted(overlap)[:5]}"
    summary = {
        "counts": {k: len(v) for k, v in out.items()},
        "groups": {k: len(v) for k, v in groups.items()},
        **dict(report),
    }
    return out, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--val-pct", type=float, default=1.0, help="Prosent grupper til validering")
    ap.add_argument("--test-pct", type=float, default=1.0, help="Prosent grupper til test")
    ap.add_argument("--group-field", default=None, help="Felt i manifestet med taler-id")
    ap.add_argument("--group-regex", default=None, help="Regex med én gruppe som henter taler-id fra lydstien")
    ap.add_argument("--exclude-manifest", action="append", default=[], help="Faste testsett som aldri skal trenes på")
    ap.add_argument("--exclude-path-contains", action="append", default=[],
                    help="Utelukk lyd der stien inneholder dette (f.eks. møtedato 20170207)")
    ap.add_argument("--text-leakage", choices=["drop-train", "drop-eval", "ignore"], default="drop-train")
    args = ap.parse_args(argv)

    with open(args.inp, encoding="utf-8-sig") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    exclude = set()
    exclude_texts = set()
    for m in args.exclude_manifest:
        with open(m, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    exclude.add(_tail(_audio(row)))
                    text = normalize(row.get("text", ""))
                    if len(text.split()) >= 4:  # korte fraser («ja takk») er for vanlige til å utelukke
                        exclude_texts.add(text)
    parts, summary = split(
        rows, args.val_pct, args.test_pct, args.group_field, args.group_regex, exclude, args.text_leakage,
        exclude_texts=exclude_texts, exclude_path_contains=args.exclude_path_contains,
    )
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, items in parts.items():
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in items:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "split_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
