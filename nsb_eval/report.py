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
                "verbatim_wer": sp.get("verbatim_wer"),
                "verbatim_deletion_rate": sp.get("verbatim_deletion_rate"),
                "critical": sp.get("critical"),
                "peak_memory_mb": (s.get("resources") or {}).get("peak_rss_mb"),
                "peak_gpu_memory_mb": (s.get("resources") or {}).get("peak_gpu_mb"),
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


def _crit(r: dict, cat: str) -> str:
    c = (r.get("critical") or {}).get(cat)
    if not c or not c.get("reference"):
        return "–"
    return f"{c['missed']}/{c['reference']}"


def _device(r: dict) -> str:
    return f"{r.get('device') or '–'}/{r.get('compute_type') or '–'}"


def _mem(r: dict) -> str:
    rss, gpu = r.get("peak_memory_mb"), r.get("peak_gpu_memory_mb")
    if rss is None and gpu is None:
        return "–"
    return f"{rss or '–'} RAM / {gpu or '–'} GPU" if gpu else f"{rss} RAM"


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
                "| Modell | Enhet | WER | Ordrett WER | CER | Innsetting | Utelatelse | Hallusinasjon | Tapte negasjoner | Feil tall | Feil navn | Sanntidsfaktor | Minne (MB) | Klipp (feilet) |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
            for r in sub:
                lines.append(
                    f"| {r['model']} | {_device(r)} | {_pct(r['wer'])} | {_pct(r['verbatim_wer'])} | {_pct(r['cer'])} | "
                    f"{_pct(r['insertion_rate'])} | {_pct(r['deletion_rate'])} | {_pct(r['hallucination_rate'])} | "
                    f"{_crit(r, 'negation')} | {_crit(r, 'number')} | {_crit(r, 'name')} | "
                    f"{r['real_time_factor'] or '–'} | {_mem(r)} | {r['items']} ({r['failed']}) |"
                )
            lines += ["", "Tapte negasjoner, feil tall og feil navn: tapte av antall i fasiten. Navn er ord med stor forbokstav i fasiten (grovt mål).", ""]
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
