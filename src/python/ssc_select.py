"""Velger og merker treningsdata fra Stortinget Speech Corpus (SSC), med bokmål som fasit.

SSC har stortingslyd delt i segmenter på inntil 30 sekunder, med tekst fra det
offisielle referatet. Referatet er ikke ordrett, og det er skrevet på talerens
målform (bokmål eller nynorsk). NSB trener med bokmål som fasit. Derfor
transkriberes hvert segment med en modell (bokmål), og fasiten velges slik:

1. Referatet er på bokmål og nesten likt modellsvaret (WER høyst
   ``--max-referat-wer``): **referatet** brukes. Det er skrevet av mennesker,
   med riktige navn og tall, og modellen bekrefter at det ble sagt.
2. Ellers (referatet er redigert eller på nynorsk): **modellsvaret** brukes,
   men bare når en kontrollmodell er enig (``--max-disagreement``), og
   modellsvaret ikke utelater mye mot referatet (``--max-referat-deletion``).
   Referatet fungerer da som en tredje kontroll mot hull og oppdiktet tekst.
3. Alt annet forkastes, med grunn.

Kjør først ``--inspect`` på maskinen der korpuset ligger. Den viser feltene i
filen, hvilke felt verktøyet har valgt, timer, talere og målform, og et
anslag over GPU-tid. Ingen modell lastes::

    python src/python/ssc_select.py --inspect --manifest "dataset/Stortinget Speech Corpus versjon 1.0/ssc.jsonl"

Deretter et lite utvalg, og til slutt hele kjøringen::

    python src/python/ssc_select.py --manifest "dataset/Stortinget Speech Corpus versjon 1.0/ssc.jsonl" \
        --out-dir build/ssc/v1 --model models/benchmark/nb-whisper-large/ct2 --label nb-whisper-large \
        --second-model models/benchmark/whisper-large-v3/ct2 --second-label whisper-large-v3 \
        --max-hours-per-speaker 3 --device cuda --compute-type float16 --limit 200

Feltnavn finnes automatisk; overstyr med ``--audio-field``, ``--text-field``
osv. hvis ``--inspect`` viser feil valg. En tekstverdi som er en sti til en
``.txt``-fil, leses fra fila. Talerdata (for eksempel dialekt fra
metadatautvidelsen av SSC) kan kobles på med ``--speaker-meta``.

Møtene som de faste NPSC-testsettene kommer fra (7. og 9. februar 2017),
hoppes alltid over. Utdata har samme form som ``pseudo_label.py``
(``labels.jsonl``, ``rejected.jsonl``, ``summary.json``) og skal videre gjennom
``split_by_group.py`` før trening. Se ``docs/SSC_TRAINING_DATA.md``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nsb_eval.metrics import repetition_loop, word_counts  # noqa: E402
from nsb_eval.normalize import normalize  # noqa: E402
from pseudo_label import SAMPLE_RATE, FasterWhisperTranscriber, agreement, check_license, chunk_stats  # noqa: E402

__all__ = [
    "Decision",
    "FieldMap",
    "SelectThresholds",
    "decide",
    "detect_fields",
    "detect_standard",
    "inspect",
    "main",
    "run",
]

SOURCE = "Stortinget Speech Corpus 1.0"
LICENSE = "CC0 1.0"
# Møtedatoene til de faste NPSC-testsettene. SSC og NPSC er fra samme sal.
LOCKED_TEST_DATES = ("20170207", "20170209")

CANDIDATES = {
    "audio": ("audio", "audio_path", "audio_filepath", "path", "segment_path", "file", "wav", "audio_file"),
    "text": ("text", "proceedings", "proceedings_text", "transcription", "transcript", "sentence_text",
             "normalized_text", "proceedings_file", "text_file"),
    "id": ("id", "segment_id", "sentence_id", "utterance_id", "uid"),
    "speaker": ("speaker_id", "speaker", "speaker_name", "name", "person_id"),
    "standard": ("standard", "language", "language_code", "sentence_language_code", "lang", "written_standard"),
    "date": ("date", "meeting_date", "session_date", "meeting", "meeting_id"),
    "duration": ("duration", "length", "seconds", "segment_duration"),
    "start": ("start", "start_time", "begin", "segment_start"),
    "end": ("end", "end_time", "stop", "segment_end"),
    "dialect": ("dialect", "speaker_dialect", "dialect_area", "dialect_region"),
}

# Ord som bare finnes i én av målformene (former som er tillatt i begge, som
# «også», «blir» og «derfor», er utelatt). Brukes når filen ikke sier noe om målform.
_NN_ONLY = frozenset({
    "ikkje", "eg", "kva", "korleis", "kvifor", "kven", "frå", "berre", "noko", "nokon", "nokre", "mykje",
    "eit", "vere", "vore", "dei", "deira", "heile", "òg", "sjølv", "framleis", "difor", "kjem", "meir",
    "ho", "medan", "saman", "fleire", "vert", "vart", "blei", "høve", "verksemd", "verksemder", "sjå",
    "seie", "seier", "gjere", "gjer", "ynskje", "ynskjer", "korkje", "berekraftig", "kommunane", "fylka",
})
_BM_ONLY = frozenset({
    "ikke", "jeg", "hva", "hvordan", "hvorfor", "hvem", "fra", "bare", "noe", "noen", "mye", "et",
    "være", "vært", "de", "deres", "hele", "selv", "fortsatt", "kommer", "mer", "hun", "mens", "sammen",
    "flere", "ble", "anledning", "virksomhet", "virksomheter", "se", "si", "sier", "gjøre", "gjør",
    "ønske", "ønsker", "verken", "bærekraftig", "kommunene", "fylkene",
})


def detect_standard(text: str, min_markers: int = 2) -> str | None:
    """«bm», «nn» eller ``None`` (for få kjennetegn til å avgjøre)."""
    words = re.findall(r"[a-zæøåòéü]+", text.lower())
    nn = sum(w in _NN_ONLY for w in words)
    bm = sum(w in _BM_ONLY for w in words)
    if nn + bm < min_markers or nn == bm:
        return None
    return "nn" if nn > bm else "bm"


def _standard_from_value(value) -> str | None:
    if value in (None, ""):
        return None
    v = str(value).lower().strip()
    if v.startswith(("nn", "nno", "nynorsk")):
        return "nn"
    if v.startswith(("nb", "bm", "nob", "no", "bokmål", "bokmal")):
        return "bm"
    return None


@dataclass
class FieldMap:
    audio: str | None = None
    text: str | None = None
    id: str | None = None
    speaker: str | None = None
    standard: str | None = None
    date: str | None = None
    duration: str | None = None
    start: str | None = None
    end: str | None = None
    dialect: str | None = None


def detect_fields(rows: list[dict], overrides: dict | None = None) -> FieldMap:
    """Velger felt ut fra vanlige navn. Et felt må finnes i de fleste radene."""
    keys = Counter(k for r in rows for k, v in r.items() if v not in (None, ""))
    need = max(1, int(0.8 * len(rows)))
    fm = FieldMap()
    for name, cands in CANDIDATES.items():
        for c in cands:
            if keys.get(c, 0) >= need:
                setattr(fm, name, c)
                break
    for k, v in (overrides or {}).items():
        if v:
            setattr(fm, k, v)
    return fm


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _duration(row: dict, fm: FieldMap) -> float | None:
    try:
        if fm.duration and row.get(fm.duration) not in (None, ""):
            d = float(row[fm.duration])
            return d / 1000.0 if d > 1000 else d  # millisekunder
        if fm.start and fm.end and row.get(fm.start) not in (None, "") and row.get(fm.end) not in (None, ""):
            d = float(row[fm.end]) - float(row[fm.start])
            return d / 1000.0 if d > 1000 else d
    except (TypeError, ValueError):
        return None
    return None


def _resolve(path: str, base: Path) -> Path:
    p = Path(str(path).replace("\\", "/"))
    return p if p.is_absolute() else base / p


def _text(row: dict, fm: FieldMap, base: Path) -> str:
    value = str(row.get(fm.text) or "")
    if value.lower().endswith(".txt"):
        p = _resolve(value, base)
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""
    return value.strip()


def _bucket(key: str) -> int:
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], 16)


def _read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_speaker_meta(path: str, key: str | None = None) -> dict[str, dict]:
    """Talerdata fra JSONL eller CSV, nøkkel = taler-id eller navn."""
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    else:
        rows = _read_jsonl(path)
    if not rows:
        return {}
    k = key or next((c for c in CANDIDATES["speaker"] + ("id",) if c in rows[0]), None)
    if not k:
        raise ValueError(f"Fant ikke taler-id i {path}; oppgi --speaker-meta-key")
    return {str(r[k]): r for r in rows if r.get(k) not in (None, "")}


# -------------------- beslutning (testes uten modell)


@dataclass
class SelectThresholds:
    min_seconds: float = 1.0
    max_seconds: float = 30.0
    min_referat_words: int = 3
    min_avg_logprob: float = -0.6
    max_no_speech_prob: float = 0.5
    max_compression_ratio: float = 2.4
    min_words_per_second: float = 1.0
    max_words_per_second: float = 6.0
    max_referat_wer: float = 0.10
    max_referat_wer_model: float = 0.40
    max_referat_wer_model_nn: float = 0.60
    max_referat_deletion: float = 0.15
    max_disagreement: float = 0.10


@dataclass
class Decision:
    reason: str
    text: str | None = None
    label_source: str | None = None
    referat_wer: float | None = None
    referat_deletion: float | None = None
    agreement_wer: float | None = None


def referat_distance(referat: str, hypothesis: str) -> tuple[float, float]:
    """(WER, andel utelatte ord) for modellsvaret med referatet som fasit."""
    ref = normalize(referat)
    hyp = normalize(hypothesis)
    c = word_counts(ref, hyp)
    n = max(1, c.reference_length)
    return c.error_rate if c.reference_length else float("inf"), c.deletions / n


def decide(referat: str, referat_standard: str | None, model_text: str, model_stats, duration: float,
           th: SelectThresholds, second_text=None) -> Decision:
    """Velger fasit for ett segment. ``second_text`` er en funksjon som gir
    kontrollmodellens svar; den kalles bare når den trengs (sparer GPU-tid)."""
    if duration < th.min_seconds:
        return Decision("too_short")
    if duration > th.max_seconds:
        return Decision("too_long")
    if len(normalize(referat).split()) < th.min_referat_words:
        return Decision("too_few_words")
    if model_stats.max_no_speech_prob > th.max_no_speech_prob:
        return Decision("no_speech")
    if model_stats.avg_logprob < th.min_avg_logprob:
        return Decision("low_confidence")
    if model_stats.max_compression_ratio > th.max_compression_ratio:
        return Decision("compression_ratio")
    hyp_words = normalize(model_text).split()
    if repetition_loop(hyp_words):
        return Decision("repetition_loop")
    wer, deletion = referat_distance(referat, model_text)
    d = Decision("", referat_wer=wer, referat_deletion=deletion)
    if referat_standard != "nn" and wer <= th.max_referat_wer:
        d.reason, d.text, d.label_source = "ok", referat, "referat"
        return d
    wps = len(hyp_words) / duration if duration > 0 else 0.0
    if wps < th.min_words_per_second:
        d.reason = "too_few_words_per_second"
        return d
    if wps > th.max_words_per_second:
        d.reason = "too_many_words_per_second"
        return d
    limit = th.max_referat_wer_model_nn if referat_standard == "nn" else th.max_referat_wer_model
    if wer > limit:
        d.reason = "referat_mismatch"
        return d
    if deletion > th.max_referat_deletion:
        d.reason = "omits_words"
        return d
    if second_text is None:
        d.reason = "needs_second_model"
        return d
    d.agreement_wer = agreement(model_text, second_text())
    if d.agreement_wer > th.max_disagreement:
        d.reason = "models_disagree"
        return d
    d.reason, d.text, d.label_source = "ok", model_text, "model"
    return d


# -------------------- inspeksjon og kjøring


def _prepare(rows: list[dict], fm: FieldMap, base: Path, speaker_meta: dict | None, exclude_dates: tuple[str, ...]):
    """Gir (rad, id, lydsti, taler, dato, varighet, dialekt) og antall utelukket per grunn."""
    out = []
    excluded = Counter()
    for i, row in enumerate(rows):
        audio = row.get(fm.audio) if fm.audio else None
        if not audio:
            excluded["missing_audio_field"] += 1
            continue
        sid = str(row.get(fm.id) or audio) if fm.id else str(audio)
        date = _digits(row.get(fm.date)) if fm.date else ""
        haystack = date + " " + _digits(audio) + " " + sid
        if any(d in haystack for d in exclude_dates):
            excluded["excluded_locked_test_meeting"] += 1
            continue
        speaker = str(row.get(fm.speaker) or "") if fm.speaker else ""
        dialect = str(row.get(fm.dialect) or "") if fm.dialect else ""
        if not dialect and speaker_meta and speaker in speaker_meta:
            m = speaker_meta[speaker]
            dialect = str(next((m[c] for c in CANDIDATES["dialect"] if m.get(c)), "") or "")
        out.append({"row": row, "index": i, "id": sid, "audio": str(_resolve(str(audio), base)),
                    "speaker": speaker, "date": date, "duration": _duration(row, fm), "dialect": dialect or "ukjent"})
    return out, excluded


def sample(items: list[dict], max_hours: float | None, max_hours_per_speaker: float | None,
           max_hours_per_dialect: float | None) -> list[dict]:
    """Deterministisk utvalg med tak på timer totalt, per taler og per dialekt.
    Rekkefølgen er stokket med hash av id, så utvalget blir spredt over møter."""
    if not (max_hours or max_hours_per_speaker or max_hours_per_dialect):
        return items
    total = 0.0
    per_speaker: dict[str, float] = defaultdict(float)
    per_dialect: dict[str, float] = defaultdict(float)
    kept = []
    for it in sorted(items, key=lambda x: _bucket(x["id"])):
        h = (it["duration"] or 15.0) / 3600  # ukjent lengde: anslag
        if max_hours and total + h > max_hours:
            continue
        if max_hours_per_speaker and it["speaker"] and per_speaker[it["speaker"]] + h > max_hours_per_speaker:
            continue
        if max_hours_per_dialect and per_dialect[it["dialect"]] + h > max_hours_per_dialect:
            continue
        total += h
        per_speaker[it["speaker"]] += h
        per_dialect[it["dialect"]] += h
        kept.append(it)
    return kept


def inspect(rows: list[dict], fm: FieldMap, base: Path, speaker_meta: dict | None = None,
            exclude_dates: tuple[str, ...] = LOCKED_TEST_DATES, sample_rows: int = 2000) -> dict:
    items, excluded = _prepare(rows, fm, base, speaker_meta, exclude_dates)
    durations = [it["duration"] for it in items if it["duration"] is not None]
    hours = sum(durations) / 3600
    standards = Counter()
    for r in rows[:sample_rows]:
        s = _standard_from_value(r.get(fm.standard)) if fm.standard else None
        if s is None and fm.text:
            s = detect_standard(_text(r, fm, base))
        standards[s or "ukjent"] += 1
    by_dialect = defaultdict(float)
    for it in items:
        by_dialect[it["dialect"]] += (it["duration"] or 0) / 3600
    missing_audio = sum(1 for it in items[:200] if not Path(it["audio"]).exists())
    return {
        "rows": len(rows),
        "fields_in_file": sorted({k for r in rows[:200] for k in r}),
        "field_map": asdict(fm),
        "example": rows[0] if rows else None,
        "example_text": _text(rows[0], fm, base)[:300] if rows and fm.text else None,
        "segments_after_exclusion": len(items),
        "excluded": dict(excluded),
        "hours": round(hours, 1) if durations else None,
        "segments_without_duration": len(items) - len(durations),
        "speakers": len({it["speaker"] for it in items if it["speaker"]}),
        "standard_in_first_rows": dict(standards),
        "hours_by_dialect": {k: round(v, 1) for k, v in sorted(by_dialect.items())} if durations else None,
        "audio_missing_in_first_200": missing_audio,
        "gpu_hours_estimate_rtf_0.1": round(hours * 0.1, 1) if durations else None,
    }


def _append(path: Path, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run(rows: list[dict], fm: FieldMap, base: Path, transcriber, out_dir: str | Path,
        th: SelectThresholds | None = None, second=None, speaker_meta: dict | None = None,
        exclude_dates: tuple[str, ...] = LOCKED_TEST_DATES, max_hours: float | None = None,
        max_hours_per_speaker: float | None = None, max_hours_per_dialect: float | None = None,
        limit: int | None = None) -> dict:
    check_license(LICENSE)
    th = th or SelectThresholds()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    labels_path, rejected_path, done_path = out / "labels.jsonl", out / "rejected.jsonl", out / "done.txt"
    identity = {
        "source": SOURCE, "license": LICENSE, "target_standard": "bm", "field_map": asdict(fm),
        "model": transcriber.describe(), "second_model": second.describe() if second else None,
        "thresholds": asdict(th), "exclude_dates": list(exclude_dates),
        "max_hours": max_hours, "max_hours_per_speaker": max_hours_per_speaker,
        "max_hours_per_dialect": max_hours_per_dialect,
    }
    meta_path = out / "run_meta.json"
    if meta_path.exists() and json.loads(meta_path.read_text(encoding="utf-8")) != identity:
        raise SystemExit(f"{out} inneholder en kjøring med andre innstillinger. Bruk en ny --out-dir.")
    meta_path.write_text(json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf-8")
    done = set(done_path.read_text(encoding="utf-8").splitlines()) if done_path.exists() else set()

    items, excluded = _prepare(rows, fm, base, speaker_meta, exclude_dates)
    items = sample(items, max_hours, max_hours_per_speaker, max_hours_per_dialect)
    if limit:
        items = items[:limit]
    for it in items:
        if it["id"] in done:
            continue
        row = it["row"]
        referat = _text(row, fm, base)
        standard = (_standard_from_value(row.get(fm.standard)) if fm.standard else None) or detect_standard(referat)
        base_row = {"id": it["id"], "audio": it["audio"], "speaker_id": it["speaker"] or None,
                    "date": it["date"] or None, "dialect": it["dialect"], "referat": referat,
                    "referat_standard": standard or "ukjent"}
        try:
            samples = transcriber.load_audio(it["audio"])
            duration = len(samples) / SAMPLE_RATE
            segs = transcriber.segments(samples, "no")
        except Exception as exc:  # noqa: BLE001 - en ødelagt fil skal ikke stoppe kjøringen
            _append(rejected_path, {**base_row, "reason": "audio_error", "error": f"{type(exc).__name__}: {exc}"})
            segs, duration, samples = None, 0.0, None
        if segs is not None:
            if not segs:
                dec = Decision("no_speech")
                model_text = ""
            else:
                stats = chunk_stats(segs)
                model_text = stats.text
                dec = decide(referat, standard, model_text, stats, duration, th,
                             second_text=(lambda s=samples: second.text(s, "no")) if second else None)
            measures = {"duration": round(duration, 3), "model_text": model_text,
                        "referat_wer": None if dec.referat_wer is None else round(dec.referat_wer, 4),
                        "referat_deletion": None if dec.referat_deletion is None else round(dec.referat_deletion, 4),
                        "agreement_wer": None if dec.agreement_wer is None else round(dec.agreement_wer, 4)}
            if dec.reason == "ok":
                _append(labels_path, {**base_row, "text": dec.text, "standard": "bm", "label_source": dec.label_source,
                                      "source": SOURCE, "license": LICENSE, "pseudo_label": dec.label_source == "model",
                                      "label_model": identity["model"]["model"], **measures})
            else:
                _append(rejected_path, {**base_row, "reason": dec.reason, **measures})
        with open(done_path, "a", encoding="utf-8") as f:
            f.write(it["id"] + "\n")
        done.add(it["id"])

    summary = summarize(labels_path, rejected_path)
    summary["excluded_before_transcription"] = dict(excluded)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def summarize(labels_path: Path, rejected_path: Path) -> dict:
    def read(p: Path) -> list[dict]:
        return _read_jsonl(str(p)) if p.exists() else []

    kept, rejected = read(labels_path), read(rejected_path)

    def hours(rows):
        return round(sum(r.get("duration") or 0 for r in rows) / 3600, 3)

    def by(rows, key):
        groups = defaultdict(list)
        for r in rows:
            groups[str(r.get(key) or "ukjent")].append(r)
        return {k: {"segments": len(v), "hours": hours(v)} for k, v in sorted(groups.items())}

    return {
        "kept_segments": len(kept),
        "kept_hours": hours(kept),
        "rejected_segments": len(rejected),
        "rejected_hours": hours(rejected),
        "kept_by_label_source": by(kept, "label_source"),
        "kept_by_referat_standard": by(kept, "referat_standard"),
        "kept_by_dialect": by(kept, "dialect"),
        "rejected_by_reason": by(rejected, "reason"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, help="SSC-filen (JSONL)")
    ap.add_argument("--audio-root", default=None, help="Mappe relative lydstier gjelder fra (standard: mappen til --manifest)")
    ap.add_argument("--inspect", action="store_true", help="Vis felt, timer og målform uten å laste modell")
    ap.add_argument("--out-dir")
    ap.add_argument("--model")
    ap.add_argument("--label", default=None)
    ap.add_argument("--second-model", default=None)
    ap.add_argument("--second-label", default=None)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--compute-type", default="default")
    for name in asdict(FieldMap()):
        ap.add_argument(f"--{name}-field", default=None, help=f"Feltnavn for {name} (overstyrer automatisk valg)")
    ap.add_argument("--speaker-meta", default=None, help="JSONL eller CSV med talerdata (dialekt)")
    ap.add_argument("--speaker-meta-key", default=None)
    ap.add_argument("--exclude-date", action="append", default=[], help="Flere møtedatoer å hoppe over (ÅÅÅÅMMDD)")
    ap.add_argument("--max-hours", type=float, default=None)
    ap.add_argument("--max-hours-per-speaker", type=float, default=None)
    ap.add_argument("--max-hours-per-dialect", type=float, default=None)
    ap.add_argument("--limit", type=int, default=None)
    defaults = SelectThresholds()
    for name, value in asdict(defaults).items():
        ap.add_argument("--" + name.replace("_", "-"), type=type(value), default=value)
    args = ap.parse_args(argv)

    rows = _read_jsonl(args.manifest)
    base = Path(args.audio_root) if args.audio_root else Path(args.manifest).resolve().parent
    fm = detect_fields(rows[:2000], {k: getattr(args, f"{k}_field") for k in asdict(FieldMap())})
    meta = load_speaker_meta(args.speaker_meta, args.speaker_meta_key) if args.speaker_meta else None
    dates = LOCKED_TEST_DATES + tuple(_digits(d) for d in args.exclude_date)
    if args.inspect:
        print(json.dumps(inspect(rows, fm, base, meta, dates), ensure_ascii=False, indent=2, default=str))
        return 0
    if not (args.out_dir and args.model):
        ap.error("--out-dir og --model er påkrevd (eller bruk --inspect)")
    if not (fm.audio and fm.text):
        ap.error(f"Fant ikke lyd- eller tekstfelt automatisk ({asdict(fm)}). Kjør --inspect og oppgi --audio-field/--text-field")
    th = SelectThresholds(**{k: getattr(args, k) for k in asdict(defaults)})
    first = FasterWhisperTranscriber(args.model, args.label, args.device, args.compute_type, vad_filter=False)
    second = (FasterWhisperTranscriber(args.second_model, args.second_label, args.device, args.compute_type, vad_filter=False)
              if args.second_model else None)
    summary = run(rows, fm, base, first, args.out_dir, th, second, meta, dates, args.max_hours,
                  args.max_hours_per_speaker, args.max_hours_per_dialect, args.limit)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
