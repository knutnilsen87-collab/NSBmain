"""Måler strømmende gjenkjenning: ventetid, hvor ofte teksten endres, og om
ordsikkerheten peker ut feilene.

Setninger fra et testsett settes sammen til strømmer på omtrent
``--stream-seconds`` sekunder (med en kort pause mellom setningene), slik at
det ligner sammenhengende diktat. Hver strøm mates til motoren i biter på
``--chunk`` sekunder, som fra en mikrofon. Behandlingstiden er ekte (målt på
maskinen), men klokken er simulert: en oppdatering vises tidligst når lyden
har kommet, og tidligst når forrige oppdatering var ferdig.

    vist_k = max(vist_{k-1}, lydtid_k) + behandlingstid_k

Mål:

- Ventetid til ferdig ord: tid fra ordet slutter i lyden til det er ferdig.
- Ventetid til vist ord: tid fra ordet slutter til det første gang vises
  (også som foreløpig).
- Endringer: antall viste ord som forsvinner eller byttes ut i en senere
  oppdatering, per 100 ferdige ord.
- WER for strømmet tekst mot WER for hele strømmen dekodet på én gang, på
  nøyaktig samme lyd.
- Ordsikkerhet: feilrate per sannsynlighetsintervall, og hvor godt en grense
  (for eksempel 0,5) skiller feil ord fra riktige.

    python -m nsb_eval.streaming_eval --testset npsc_test_20170207 --model models/.../ct2 \\
        --label nb-whisper-large-distil-turbo-beta --out-dir eval/results/streaming/npsc --vad
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from nsb_engine.streaming import SAMPLE_RATE, StreamingRecognizer, Word, _key, join_words
from nsb_eval.critical import align_ops
from nsb_eval.manifest import Item, file_sha256, load_manifest
from nsb_eval.metrics import word_counts
from nsb_eval.normalize import normalize
from nsb_eval.preflight import manifest_for
from nsb_eval.runner import _git_sha

SCHEMA = "nsb-streaming-v1"
PROB_BINS = (0.0, 0.3, 0.5, 0.7, 0.9, 1.01)
THRESHOLDS = (0.3, 0.5, 0.7)


def build_streams(items: list[Item], stream_seconds: float, durations: dict[str, float]) -> list[list[Item]]:
    streams, cur, length = [], [], 0.0
    for it in items:
        d = durations[it.id]
        if cur and length + d > stream_seconds:
            streams.append(cur)
            cur, length = [], 0.0
        cur.append(it)
        length += d
    if cur:
        streams.append(cur)
    return streams


def concat(audios: list[np.ndarray], gap: float) -> np.ndarray:
    pause = np.zeros(int(gap * SAMPLE_RATE), dtype=np.float32)
    parts = []
    for a in audios:
        parts.extend([a, pause])
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def simulate(rec: StreamingRecognizer, audio: np.ndarray, chunk: float) -> dict:
    """Mater lyden i biter. Gir ferdige ord med tider og målinger."""
    step = int(chunk * SAMPLE_RATE)
    wall = 0.0
    final: list[tuple[Word, float]] = []  # (ord, vist som ferdig)
    first_seen: list[tuple[str, float, float]] = []  # (nøkkel, start, vist)
    prev_display: list[str] = []
    changes = 0
    lags = []
    processing = 0.0
    decodes = 0

    def record(update, audio_time):
        nonlocal wall, prev_display, changes, processing, decodes
        wall = max(wall, audio_time) + update.processing_seconds
        processing += update.processing_seconds
        decodes += int(update.decoded)
        lags.append(wall - audio_time)
        for w in update.committed:
            final.append((w, wall))
        shown = update.committed + update.tentative
        for w in shown:
            first_seen.append((_key(w.text), w.start, wall))
        display = [_key(w.text) for w, _ in final] + [_key(w.text) for w in update.tentative]
        n = 0
        for a, b in zip(prev_display, display, strict=False):
            if a != b:
                break
            n += 1
        changes += len(prev_display) - n
        prev_display = display

    for pos in range(0, len(audio), step):
        rec.insert_audio(audio[pos:pos + step])
        record(rec.process(), min(len(audio), pos + step) / SAMPLE_RATE)
    record(rec.finish(), len(audio) / SAMPLE_RATE)

    commit_lat, display_lat = [], []
    for w, t in final:
        commit_lat.append(t - w.end)
        k = _key(w.text)
        seen = [v for key, s, v in first_seen if key == k and abs(s - w.start) < 0.5]
        display_lat.append((min(seen) if seen else t) - w.end)
    return {
        "words": [w for w, _ in final],
        "commit_latency": commit_lat,
        "display_latency": display_lat,
        "changes": changes,
        "processing_seconds": processing,
        "decodes": decodes,
        "max_lag": max(lags) if lags else 0.0,
        "final_lag": lags[-1] if lags else 0.0,
    }


def word_errors(reference: str, words: list[Word]) -> list[bool]:
    """For hvert ord fra modellen: ble det feil (erstattet eller innsatt)?"""
    ref = normalize(reference).split()
    # Ord som henger sammen («13» + «.2»), vurderes som ett ord.
    units: list[list[int]] = []
    for i, w in enumerate(words):
        if w.joined and units:
            units[-1].append(i)
        else:
            units.append([i])
    texts = ["".join(words[i].text for i in idx) for idx in units]
    hyp, src = [], []
    for u, text in enumerate(texts):
        toks = normalize(text).split()
        if u + 1 < len(texts):
            # Normaliseringen avhenger av neste ord («13.» foran «mars» er et
            # ordenstall), så ordet normaliseres sammen med det neste.
            nxt = normalize(texts[u + 1]).split()
            both = normalize(text + " " + texts[u + 1]).split()
            if nxt and both[-len(nxt):] == nxt:
                toks = both[: len(both) - len(nxt)]
        for tok in toks:
            hyp.append(tok)
            src.append(u)
    wrong = [False] * len(words)
    j = 0
    for op, _, h in align_ops(ref, hyp):
        if h is None:
            continue
        if op != "ok":
            for i in units[src[j]]:
                wrong[i] = True
        j += 1
    return wrong


def confidence_table(pairs: list[tuple[float, bool]]) -> dict:
    bins = []
    for lo, hi in zip(PROB_BINS, PROB_BINS[1:], strict=False):
        sel = [wrong for p, wrong in pairs if lo <= p < hi]
        bins.append({
            "from": lo, "to": min(hi, 1.0), "words": len(sel),
            "error_rate": round(sum(sel) / len(sel), 4) if sel else None,
        })
    total_wrong = sum(w for _, w in pairs)
    thresholds = []
    for t in THRESHOLDS:
        flagged = [wrong for p, wrong in pairs if p < t]
        thresholds.append({
            "below": t,
            "flagged_share": round(len(flagged) / len(pairs), 4) if pairs else None,
            "precision": round(sum(flagged) / len(flagged), 4) if flagged else None,  # andel markerte som er feil
            "recall": round(sum(flagged) / total_wrong, 4) if total_wrong else None,  # andel feil som markeres
        })
    return {
        "words": len(pairs), "wrong": total_wrong,
        "error_rate": round(total_wrong / len(pairs), 4) if pairs else None,
        "bins": bins, "thresholds": thresholds,
    }


def flag_table(rows: list[tuple[bool, bool]]) -> dict:
    """(markert, feil) per ord -> andel markert, presisjon og dekning."""
    flagged = [wrong for f, wrong in rows if f]
    total_wrong = sum(w for _, w in rows)
    return {
        "flagged_share": round(len(flagged) / len(rows), 4) if rows else None,
        "precision": round(sum(flagged) / len(flagged), 4) if flagged else None,
        "recall": round(sum(flagged) / total_wrong, 4) if total_wrong else None,
    }


def uncertainty_signals(words: list[Word], wrong: list[bool]) -> dict:
    """Sammenligner måter å peke ut usikre ord på."""
    rows = list(zip(words, wrong, strict=True))
    return {
        "probability_below_0.5": flag_table([(w.probability < 0.5, x) for w, x in rows]),
        "revised": flag_table([(w.revisions > 0, x) for w, x in rows]),
        "revised_or_below_0.5": flag_table([(w.revisions > 0 or w.probability < 0.5, x) for w, x in rows]),
        "revised_twice": flag_table([(w.revisions > 1, x) for w, x in rows]),
    }


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * len(s)))], 3)


def evaluate(args) -> dict:
    from faster_whisper import decode_audio

    from nsb_engine.streaming import FasterWhisperBackend, silero_detector

    root = Path(args.root)
    manifest, audio_root = (Path(args.manifest), Path(args.audio_root or ".")) if args.manifest \
        else manifest_for(root, args.testset)
    items = load_manifest(manifest, audio_root=audio_root)
    if args.limit:
        items = items[: args.limit]
    audios = {it.id: decode_audio(it.audio, sampling_rate=SAMPLE_RATE) for it in items}
    durations = {k: len(v) / SAMPLE_RATE for k, v in audios.items()}
    streams = build_streams(items, args.stream_seconds, durations)
    if args.max_streams:
        streams = streams[: args.max_streams]

    backend = FasterWhisperBackend(args.model, device=args.device, compute_type=args.compute_type,
                                   language=args.language, beam_size=args.beam_size)
    detector = silero_detector() if args.vad else None
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    totals = {"stream": [0, 0], "batch": [0, 0]}
    commit_lat, display_lat, pairs = [], [], []
    all_words, all_wrong = [], []
    changes = final_words = 0
    processing = audio_seconds = 0.0
    max_lag = 0.0
    final_lags = []
    started = datetime.now(timezone.utc)
    with open(out / "streams.jsonl", "w", encoding="utf-8") as f:
        for n, stream in enumerate(streams, start=1):
            audio = concat([audios[it.id] for it in stream], args.gap)
            reference = " ".join(it.text for it in stream)
            rec = StreamingRecognizer(backend, detector=detector, min_step=args.min_step,
                                      endpoint_silence=args.endpoint_silence)
            res = simulate(rec, audio, args.chunk)
            text = join_words(res["words"])
            sc = word_counts(normalize(reference), normalize(text))
            t0 = time.perf_counter()
            batch_words = backend.transcribe(audio)
            batch_seconds = time.perf_counter() - t0
            batch_text = join_words(batch_words)
            bc = word_counts(normalize(reference), normalize(batch_text))
            totals["stream"][0] += sc.errors
            totals["stream"][1] += sc.reference_length
            totals["batch"][0] += bc.errors
            totals["batch"][1] += bc.reference_length
            commit_lat += res["commit_latency"]
            display_lat += res["display_latency"]
            wrong = word_errors(reference, res["words"])
            pairs += [(w.probability, x) for w, x in zip(res["words"], wrong, strict=True)]
            all_words += res["words"]
            all_wrong += wrong
            changes += res["changes"]
            final_words += len(res["words"])
            processing += res["processing_seconds"]
            audio_seconds += len(audio) / SAMPLE_RATE
            max_lag = max(max_lag, res["max_lag"])
            final_lags.append(res["final_lag"])
            f.write(json.dumps({
                "stream": n, "ids": [it.id for it in stream], "seconds": round(len(audio) / SAMPLE_RATE, 2),
                "reference": reference, "streaming": text, "batch": batch_text,
                "wer_streaming": round(sc.errors / max(1, sc.reference_length), 4),
                "wer_batch": round(bc.errors / max(1, bc.reference_length), 4),
                "decodes": res["decodes"], "processing_seconds": round(res["processing_seconds"], 3),
                "batch_seconds": round(batch_seconds, 3), "changes": res["changes"],
                "words": [[w.text, round(w.start, 2), round(w.end, 2), round(w.probability, 3), w.revisions, x]
                          for w, x in zip(res["words"], wrong, strict=True)],
            }, ensure_ascii=False) + "\n")
            print(f"[{n}/{len(streams)}] {len(audio) / SAMPLE_RATE:.0f} s  WER strøm {sc.errors / max(1, sc.reference_length):.1%}"
                  f"  hel {bc.errors / max(1, bc.reference_length):.1%}  ferdig-ventetid median "
                  f"{statistics.median(res['commit_latency']) if res['commit_latency'] else float('nan'):.2f} s", flush=True)

    summary = {
        "schema": SCHEMA,
        "testset": args.testset or str(manifest),
        "manifest_sha256": file_sha256(manifest),
        "model": {"label": args.label, "path": args.model, "revision": args.model_revision, "model_sha256": args.model_sha256, "device": args.device, "compute_type": args.compute_type,
                  "language": args.language, "beam_size": args.beam_size},
        "settings": {"chunk": args.chunk, "min_step": args.min_step, "stream_seconds": args.stream_seconds,
                     "gap": args.gap, "vad": args.vad, "endpoint_silence": args.endpoint_silence},
        "started_utc": started.isoformat(), "finished_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "streams": len(streams), "items": sum(len(s) for s in streams), "audio_seconds": round(audio_seconds, 1),
        "wer_streaming": round(totals["stream"][0] / max(1, totals["stream"][1]), 4),
        "wer_batch": round(totals["batch"][0] / max(1, totals["batch"][1]), 4),
        "commit_latency_s": {"median": _pct(commit_lat, 0.5), "p90": _pct(commit_lat, 0.9), "max": _pct(commit_lat, 1.0)},
        "display_latency_s": {"median": _pct(display_lat, 0.5), "p90": _pct(display_lat, 0.9)},
        "changes_per_100_words": round(100 * changes / max(1, final_words), 2),
        "real_time_factor": round(processing / max(1e-9, audio_seconds), 4),
        "max_lag_s": round(max_lag, 3),
        "final_lag_s": {"median": _pct(final_lags, 0.5), "max": _pct(final_lags, 1.0)},
        "alignment_fallbacks": getattr(backend, "alignment_fallbacks", 0),
        "confidence": confidence_table(pairs),
        "uncertainty_signals": uncertainty_signals(all_words, all_wrong),
    }
    (out / "streaming_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--testset")
    ap.add_argument("--manifest", help="i stedet for --testset")
    ap.add_argument("--audio-root")
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--model-revision")
    ap.add_argument("--model-sha256")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="float16")
    ap.add_argument("--language", default="no")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--limit", type=int, default=0, help="bruk bare de første N setningene")
    ap.add_argument("--max-streams", type=int, default=0)
    ap.add_argument("--stream-seconds", type=float, default=60.0)
    ap.add_argument("--gap", type=float, default=0.5, help="pause mellom setninger i en strøm")
    ap.add_argument("--chunk", type=float, default=0.5, help="lydbit fra mikrofonen, sekunder")
    ap.add_argument("--min-step", type=float, default=1.0, help="ny lyd før ny dekoding, sekunder")
    ap.add_argument("--endpoint-silence", type=float, default=0.8)
    ap.add_argument("--vad", action="store_true")
    args = ap.parse_args(argv)
    if not args.testset and not args.manifest:
        ap.error("--testset eller --manifest må oppgis")
    s = evaluate(args)
    print(json.dumps({k: s[k] for k in ("wer_streaming", "wer_batch", "commit_latency_s", "display_latency_s",
                                        "changes_per_100_words", "real_time_factor")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
