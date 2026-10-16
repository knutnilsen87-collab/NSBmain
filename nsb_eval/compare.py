"""Parvis sammenligning av modeller på samme testsett, med bootstrap-intervall.

WER-forskjeller på noen hundre setninger kan skyldes tilfeldigheter. Skriptet
trekker setninger med tilbakelegging (samme trekk for begge modellene) og gir
et 95 %-intervall for forskjellen i WER, i prosentpoeng.

    python -m nsb_eval.compare --results eval/results --testset nb_samtale_test \
        --baseline nb-whisper-large-distil-turbo-beta
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def load_errors(items_path: Path) -> dict[str, tuple[int, int]]:
    """id -> (feil, ord i fasiten) for setninger med tekst i fasiten."""
    out: dict[str, tuple[int, int]] = {}
    with open(items_path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            w = r.get("words")
            if r.get("error") or not w or not w.get("reference_length"):
                continue
            out[r["id"]] = (int(w["errors"]), int(w["reference_length"]))
    return out


def paired_bootstrap(a: dict, b: dict, rounds: int = 2000, seed: int = 0) -> dict:
    """WER(a) − WER(b) i prosentpoeng, med 95 %-intervall, på felles setninger."""
    ids = sorted(set(a) & set(b))
    if not ids:
        raise ValueError("Ingen felles setninger å sammenligne")

    def diff(sample):
        ea = sum(a[i][0] for i in sample)
        eb = sum(b[i][0] for i in sample)
        n = sum(b[i][1] for i in sample)
        return (ea - eb) / n * 100

    rng = random.Random(seed)
    draws = sorted(diff([rng.choice(ids) for _ in ids]) for _ in range(rounds))
    lo = draws[int(0.025 * rounds)]
    hi = draws[int(0.975 * rounds) - 1]
    return {
        "items": len(ids),
        "diff_pp": round(diff(ids), 2),
        "ci95_pp": [round(lo, 2), round(hi, 2)],
        "significant": lo > 0 or hi < 0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--testset", required=True)
    ap.add_argument("--baseline", required=True, help="modellen de andre sammenlignes med")
    ap.add_argument("--rounds", type=int, default=2000)
    args = ap.parse_args(argv)
    root = Path(args.results) / args.testset
    base = load_errors(root / args.baseline / "items.jsonl")
    for run in sorted(p for p in root.iterdir() if p.is_dir() and p.name != args.baseline):
        items = run / "items.jsonl"
        if not items.exists():
            continue
        r = paired_bootstrap(load_errors(items), base, rounds=args.rounds)
        mark = "signifikant" if r["significant"] else "ikke signifikant"
        print(f"{run.name} minus {args.baseline}: {r['diff_pp']:+.1f} pp, "
              f"95 % KI [{r['ci95_pp'][0]:+.1f}, {r['ci95_pp'][1]:+.1f}], {mark} ({r['items']} setninger)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
