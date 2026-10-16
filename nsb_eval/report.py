"""Samler ``summary.json``-filer til én tabell (Markdown og JSON).

    python -m nsb_eval.report --results eval/results --out eval/results/BENCHMARK.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def collect(results_dir: str | Path) -> list[dict]:
    rows = []
    for path in sorted(Path(results_dir).glob("**/summary.json")):
        s = json.loads(path.read_text(encoding="utf-8"))
        sp = s.get("speech", {})
        si = s.get("silence", {})
        rows.append(
            {
                "testset": s.get("testset"),
                "model": s.get("model", {}).get("model"),
                "items": s.get("items_total"),
                "failed": s.get("items_failed"),
                "complete": s.get("complete"),
                "wer": sp.get("wer"),
                "cer": sp.get("cer"),
                "substitution_rate": sp.get("substitution_rate"),
                "deletion_rate": sp.get("deletion_rate"),
                "insertion_rate": sp.get("insertion_rate"),
                "hallucination_rate": sp.get("hallucination_rate"),
                "repetition_loop_items": sp.get("repetition_loop_items"),
                "silence_hallucination_rate": si.get("hallucination_on_silence_rate"),
                "silence_inserted_words": si.get("inserted_words"),
                "real_time_factor": sp.get("real_time_factor") or si.get("real_time_factor"),
                "audio_seconds": sp.get("audio_seconds"),
                "device": s.get("model", {}).get("device"),
                "compute_type": s.get("model", {}).get("compute_type"),
                "manifest_sha256": s.get("manifest_sha256"),
                "git_sha": s.get("git_sha"),
                "finished_utc": s.get("finished_utc"),
                "groups": {k[3:]: v for k, v in s.items() if k.startswith("by_")},
            }
        )
    return rows


def _pct(v) -> str:
    return "–" if v is None else f"{100 * v:.1f} %"


def to_markdown(rows: list[dict]) -> str:
    lines = ["# NSB-målestokk: resultater", ""]
    for testset in sorted({r["testset"] for r in rows}):
        sub = sorted(
            (r for r in rows if r["testset"] == testset),
            key=lambda r: (r["wer"] is None, r["wer"] if r["wer"] is not None else 0, r["model"] or ""),
        )
        lines += [f"## {testset}", ""]
        if all(r["wer"] is None for r in sub):
            lines += ["| Modell | Klipp | Hallusinasjon i stillhet | Innsatte ord | Sanntidsfaktor |", "| --- | ---: | ---: | ---: | ---: |"]
            for r in sub:
                lines.append(
                    f"| {r['model']} | {r['items']} | {_pct(r['silence_hallucination_rate'])} | "
                    f"{r['silence_inserted_words']} | {r['real_time_factor'] or '–'} |"
                )
        else:
            lines += [
                "| Modell | WER | CER | Innsetting | Utelatelse | Hallusinasjon | Sanntidsfaktor | Klipp (feilet) |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
            for r in sub:
                lines.append(
                    f"| {r['model']} | {_pct(r['wer'])} | {_pct(r['cer'])} | {_pct(r['insertion_rate'])} | "
                    f"{_pct(r['deletion_rate'])} | {_pct(r['hallucination_rate'])} | {r['real_time_factor'] or '–'} | "
                    f"{r['items']} ({r['failed']}) |"
                )
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True, help="Markdown-fil; JSON skrives ved siden av")
    args = ap.parse_args(argv)
    rows = collect(args.results)
    out = Path(args.out)
    out.write_text(to_markdown(rows), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(rows)} resultater -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
