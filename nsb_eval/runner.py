"""Kjører én modell mot ett testsett og skriver resultatene.

Eksempel::

    python -m nsb_eval.runner --manifest eval/testsets/npsc_test_20170207.jsonl \
        --audio-root F:/prosjekter_MAIN/NorwegianSpeechBase \
        --backend faster-whisper --model models/nb-whisper-large/ct2 \
        --label nb-whisper-large --out-dir eval/results/npsc/nb-whisper-large

Utdata i ``--out-dir``:

- ``items.jsonl``: én linje per setning med fasit, svar, feiltall og flagg
- ``summary.json``: samlet WER, CER, hallusinasjonsmål, tid og miljø

Kjøringen kan avbrytes og startes igjen; setninger som allerede står i
``items.jsonl`` hoppes over (``--resume`` er standard).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from .backends import make_backend
from .manifest import file_sha256, load_manifest
from .metrics import EditCounts, char_counts, item_flags, word_counts
from .normalize import normalize

__all__ = ["evaluate", "main", "summarize"]

SCHEMA = "nsb-eval-2"


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=Path(__file__).resolve().parent,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _load_done(items_path: Path) -> dict:
    done = {}
    if items_path.exists():
        with open(items_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    if row.get("error"):
                        continue  # feilede setninger prøves igjen
                    done[row["id"]] = row
    return done


def score_item(item_id: str, reference: str, hypothesis: str, meta: dict | None = None) -> dict:
    ref_n = normalize(reference)
    hyp_n = normalize(hypothesis)
    w = word_counts(ref_n, hyp_n)
    c = char_counts(ref_n, hyp_n)
    return {
        "id": item_id,
        "reference": reference,
        "hypothesis": hypothesis,
        "reference_norm": ref_n,
        "hypothesis_norm": hyp_n,
        "words": w.to_dict(),
        "chars": c.to_dict(),
        "flags": item_flags(ref_n, hyp_n, w),
        "meta": meta or {},
    }


def summarize(rows: list[dict], group_by: list[str] | None = None) -> dict:
    ok = [r for r in rows if not r.get("error")]
    failed = [r for r in rows if r.get("error")]
    speech = [r for r in ok if r["reference_norm"]]
    # Tom fasit = stillhet/støy. Fasit som bare har fyllord eller
    # «uforståelig» holdes utenfor både WER og stillhetsmålet.
    silence = [r for r in ok if not r["reference_norm"] and not r["reference"].strip()]
    nonlexical = [r for r in ok if not r["reference_norm"] and r["reference"].strip()]

    def agg(subset: list[dict]) -> dict:
        w = EditCounts()
        c = EditCounts()
        for r in subset:
            w = w + EditCounts(**{k: r["words"][k] for k in ("substitutions", "deletions", "insertions", "reference_length")})
            c = c + EditCounts(**{k: r["chars"][k] for k in ("substitutions", "deletions", "insertions", "reference_length")})
        n = len(subset)
        flags = defaultdict(int)
        for r in subset:
            for k, v in r["flags"].items():
                if isinstance(v, bool) and v:
                    flags[k] += 1
        audio = sum(r.get("duration", 0.0) for r in subset)
        proc = sum(r.get("processing_seconds", 0.0) for r in subset)
        return {
            "items": n,
            "wer": round(w.error_rate, 6) if w.reference_length else None,
            "cer": round(c.error_rate, 6) if c.reference_length else None,
            "word_counts": w.to_dict(),
            "substitution_rate": round(w.substitutions / w.reference_length, 6) if w.reference_length else None,
            "deletion_rate": round(w.deletions / w.reference_length, 6) if w.reference_length else None,
            "insertion_rate": round(w.insertions / w.reference_length, 6) if w.reference_length else None,
            "hallucination_items": flags["hallucination"],
            "hallucination_rate": round(flags["hallucination"] / n, 6) if n else None,
            "repetition_loop_items": flags["repetition_loop"],
            "overlong_items": flags["overlong"],
            "empty_output_items": flags["empty_output"],
            "audio_seconds": round(audio, 2),
            "processing_seconds": round(proc, 2),
            "real_time_factor": round(proc / audio, 4) if audio else None,
        }

    summary = {
        "items_total": len(rows),
        "items_failed": len(failed),
        "complete": not failed,
        "items_nonlexical_excluded": len(nonlexical),
        "speech": agg(speech),
    }
    if silence:
        s = agg(silence)
        summary["silence"] = {
            "items": s["items"],
            "hallucination_on_silence_items": sum(1 for r in silence if r["flags"]["hallucination_on_silence"]),
            "hallucination_on_silence_rate": round(
                sum(1 for r in silence if r["flags"]["hallucination_on_silence"]) / len(silence), 6
            ),
            "inserted_words": sum(r["words"]["insertions"] for r in silence),
            "audio_seconds": s["audio_seconds"],
            "real_time_factor": s["real_time_factor"],
        }
    for key in group_by or []:
        groups = defaultdict(list)
        for r in speech:
            groups[str(r.get("meta", {}).get(key, "ukjent"))].append(r)
        summary[f"by_{key}"] = {g: agg(sub) for g, sub in sorted(groups.items())}
    if failed:
        summary["failed_examples"] = [{"id": r["id"], "error": r["error"]} for r in failed[:10]]
    return summary


def evaluate(
    manifest: str,
    out_dir: str,
    backend_kind: str,
    backend_kwargs: dict,
    testset: str | None = None,
    audio_root: str | None = None,
    path_map: dict | None = None,
    limit: int | None = None,
    group_by: list[str] | None = None,
    resume: bool = True,
    log=print,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items_path = out / "items.jsonl"
    items = load_manifest(manifest, audio_root=audio_root, path_map=path_map)
    if limit:
        items = items[:limit]
    done = _load_done(items_path) if resume else {}
    if not resume and items_path.exists():
        items_path.unlink()

    started = dt.datetime.now(dt.timezone.utc)
    backend = make_backend(backend_kind, **backend_kwargs)
    log(f"[nsb_eval] {len(items)} setninger, {len(done)} allerede ferdige, modell {backend.describe().get('model')}")

    t_last = time.time()
    with open(items_path, "a", encoding="utf-8") as f:
        for i, item in enumerate(items, start=1):
            if item.id in done:
                continue
            t0 = time.perf_counter()
            try:
                result = backend.transcribe(item.audio)
                row = score_item(item.id, item.text, result["text"], item.meta)
                row["duration"] = result.get("duration", 0.0)
                row["segments"] = result.get("segments")
            except Exception as exc:  # noqa: BLE001 - én dårlig fil skal ikke stoppe kjøringen
                row = {"id": item.id, "reference": item.text, "error": f"{type(exc).__name__}: {exc}", "meta": item.meta}
            row["audio"] = item.audio
            row["processing_seconds"] = round(time.perf_counter() - t0, 4)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            done[item.id] = row
            if time.time() - t_last > 30 or i == len(items):
                log(f"[nsb_eval] {i}/{len(items)}")
                t_last = time.time()

    rows = [done[it.id] for it in items if it.id in done]
    summary = {
        "schema": SCHEMA,
        "testset": testset or Path(manifest).stem,
        "manifest": str(manifest),
        "manifest_sha256": file_sha256(manifest),
        "model": backend.describe(),
        "started_utc": started.isoformat(),
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "normalizer": "nsb_eval.normalize v1",
        **summarize(rows, group_by=group_by),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    sp = summary["speech"]
    log(
        f"[nsb_eval] ferdig: WER={sp['wer']} CER={sp['cer']} hallusinasjon={sp['hallucination_rate']} "
        f"feilet={summary['items_failed']}"
    )
    return summary


def _parse_path_map(values: list[str] | None) -> dict:
    mapping = {}
    for v in values or []:
        if "=" not in v:
            raise SystemExit(f"--path-map må ha formen GAMMEL=NY, fikk {v!r}")
        old, new = v.split("=", 1)
        mapping[old] = new
    return mapping


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mål en talegjenkjenningsmodell mot et fast testsett.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--testset", default=None, help="Navn på testsettet i rapporten")
    ap.add_argument("--audio-root", default=None, help="Rot for relative lydstier")
    ap.add_argument("--path-map", action="append", help="Skriv om stiprefiks, GAMMEL=NY (kan gjentas)")
    ap.add_argument("--backend", default="faster-whisper", choices=["faster-whisper", "mock"])
    ap.add_argument("--model", help="Modellsti eller Hugging Face-id (faster-whisper)")
    ap.add_argument("--label", default=None, help="Modellnavn i rapporten")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--compute-type", default="default")
    ap.add_argument("--language", default="no")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--vad", action="store_true", help="Slå på VAD-filter (av som standard)")
    ap.add_argument("--answers-file", default=None, help="Kun for --backend mock")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--group-by", action="append", default=None, help="Metadatafelt å bryte ned på")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args(argv)

    if args.backend == "faster-whisper":
        if not args.model:
            ap.error("--model kreves for faster-whisper")
        kwargs = {
            "model": args.model,
            "device": args.device,
            "compute_type": args.compute_type,
            "language": args.language,
            "beam_size": args.beam_size,
            "vad_filter": args.vad,
            "label": args.label,
        }
    else:
        kwargs = {"answers_file": args.answers_file, "label": args.label}

    summary = evaluate(
        manifest=args.manifest,
        out_dir=args.out_dir,
        backend_kind=args.backend,
        backend_kwargs=kwargs,
        testset=args.testset,
        audio_root=args.audio_root,
        path_map=_parse_path_map(args.path_map),
        limit=args.limit,
        group_by=args.group_by,
        resume=not args.no_resume,
    )
    return 0 if summary["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
