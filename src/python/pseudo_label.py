"""Pseudo-merking: lager treningsfasit for ekte lyd som mangler transkripsjon.

Ideen: lyden er ekte (for eksempel dialekttale fra podkast eller lokalradio
med kjent lisens), mens teksten lages av en sterk modell og bare beholdes der
modellen med stor sannsynlighet har rett. Lange opptak deles i klipp på
inntil 30 sekunder langs modellens egne segmentgrenser.

    python src/python/pseudo_label.py --in data/unlabeled/podkast_vest.jsonl \
        --out-dir build/pseudo/podkast_vest --source "Podkast X" --license "CC BY 4.0" \
        --model models/benchmark/nb-whisper-large/ct2 --label nb-whisper-large \
        --second-model models/benchmark/whisper-large-v3/ct2 --second-label whisper-large-v3 \
        --exclude-manifest eval/testsets/nb_samtale_test.jsonl \
        --exclude-manifest eval/testsets/npsc_test_20170207.jsonl \
        --exclude-manifest eval/testsets/npsc_eval_20170209.jsonl \
        --device cuda --compute-type float16

Inndata er JSONL med én lydfil per linje (``audio`` eller ``path``) og
valgfrie metadata (``dialect``, ``speaker_id``, ``standard`` ...), eller en
mappe (``--audio-dir``). Metadata følger med til hvert klipp.

Et klipp beholdes bare når alle kravene holder:

- lengde mellom ``--min-seconds`` og ``--max-seconds``
- gjennomsnittlig log-sannsynlighet per token over ``--min-avg-logprob``
- sannsynlighet for «ingen tale» under ``--max-no-speech-prob`` i alle segmenter
- komprimeringsforhold under ``--max-compression-ratio`` (fanger gjentakelser)
- ingen gjentakelsesløkke og minst ``--min-words`` ord
- ord per sekund mellom ``--min-words-per-second`` og ``--max-words-per-second``.
  Nedre grense er viktig: NB-Whisper utelater systematisk ord (17–21 %
  utelatelser på NB Samtale), og en fasit med hull lærer modellen å utelate mer.
- med ``--second-model``: de to modellene er enige (WER mellom dem etter norsk
  normalisering høyst ``--max-disagreement``)

Utdata i ``--out-dir``:

- ``clips/``: 16 kHz mono WAV per beholdt klipp
- ``pseudo_labels.jsonl``: klipp med tekst, kilde, lisens, mål og metadata,
  i samme format som treningsmanifestene (``audio`` + ``text``)
- ``rejected.jsonl``: forkastede klipp med grunn (for å justere terskler)
- ``summary.json``: antall og timer per grunn og per dialekt
- ``run_meta.json`` og ``done.txt``: gjør kjøringen gjenopptakbar

Resultatet skal videre gjennom ``split_by_group.py`` (taler- og
tekstlekkasje) før trening, og pseudo-merket lyd bør være en mindre del av
treningsdataene. Se ``docs/PSEUDO_LABELING.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import wave
from array import array
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nsb_eval.metrics import repetition_loop, word_counts  # noqa: E402
from nsb_eval.normalize import normalize  # noqa: E402

__all__ = [
    "Segment",
    "Thresholds",
    "check_chunk",
    "check_license",
    "chunk_segments",
    "chunk_stats",
    "load_exclusions",
    "main",
    "run",
    "write_wav",
]

SAMPLE_RATE = 16000
AUDIO_KEYS = ("audio", "path", "audio_filepath", "audio_path")
TEXT_KEYS = ("text", "transcript", "sentence_text")
AUDIO_SUFFIXES = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm", ".mp4")
STANDARD_TO_LANGUAGE = {"bm": "no", "nb": "no", "nn": "nn"}
# Lisenser som ikke tillater kommersiell bruk (NC) eller avledede verk (ND).
# Pseudo-merket tekst er et avledet verk, og NSB skal kunne brukes kommersielt.
_FORBIDDEN_LICENSE_RE = re.compile(r"(^|[\s\-_/])(NC|ND)($|[\s\-_/])", flags=re.IGNORECASE)


@dataclass
class Segment:
    """Ett segment fra modellen, med tider i sekunder fra starten av filen."""

    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float


@dataclass
class Thresholds:
    min_seconds: float = 1.0
    max_seconds: float = 30.0
    max_gap_seconds: float = 1.5
    min_avg_logprob: float = -0.5
    max_no_speech_prob: float = 0.5
    max_compression_ratio: float = 2.4
    min_words: int = 3
    min_words_per_second: float = 1.0
    max_words_per_second: float = 6.0
    max_disagreement: float = 0.15


@dataclass
class ChunkStats:
    start: float
    end: float
    text: str
    words: int
    avg_logprob: float
    max_no_speech_prob: float
    max_compression_ratio: float
    segments: int = 0
    agreement_wer: float | None = None
    second_text: str | None = field(default=None, repr=False)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def words_per_second(self) -> float:
        return self.words / self.duration if self.duration > 0 else 0.0


# -------------------- rene funksjoner (testes uten modell)


def check_license(license_name: str) -> None:
    """Stopper lisenser som ikke tillater kommersiell bruk eller avledede verk."""
    if not license_name or not license_name.strip():
        raise ValueError("Oppgi --license. Ingen data uten lisens i dataregisteret (docs/DATA_REGISTER.md).")
    if _FORBIDDEN_LICENSE_RE.search(license_name):
        raise ValueError(
            f"Lisensen {license_name!r} tillater ikke kommersiell bruk eller avledede verk. "
            "Pseudo-merket tekst er et avledet verk; se docs/DATA_REGISTER.md."
        )


def chunk_segments(segments: Sequence[Segment], max_seconds: float = 30.0, max_gap: float = 1.5) -> list[list[Segment]]:
    """Slår sammen påfølgende segmenter til klipp på høyst ``max_seconds``.

    Nytt klipp startes når neste segment ville gjort klippet for langt, eller
    når pausen før det er lengre enn ``max_gap``. Et enkeltsegment som selv er
    for langt, blir eget klipp (og forkastes senere som for langt).
    """
    chunks: list[list[Segment]] = []
    current: list[Segment] = []
    for seg in sorted(segments, key=lambda s: s.start):
        if not seg.text.strip():
            continue
        if current and (seg.end - current[0].start > max_seconds or seg.start - current[-1].end > max_gap):
            chunks.append(current)
            current = []
        current.append(seg)
    if current:
        chunks.append(current)
    return chunks


def chunk_stats(chunk: Sequence[Segment]) -> ChunkStats:
    text = " ".join(s.text.strip() for s in chunk if s.text.strip())
    weights = [max(s.end - s.start, 1e-3) for s in chunk]
    avg = sum(s.avg_logprob * w for s, w in zip(chunk, weights, strict=True)) / sum(weights)
    return ChunkStats(
        start=chunk[0].start,
        end=chunk[-1].end,
        text=text,
        words=len(normalize(text).split()),
        avg_logprob=avg,
        max_no_speech_prob=max(s.no_speech_prob for s in chunk),
        max_compression_ratio=max(s.compression_ratio for s in chunk),
        segments=len(chunk),
    )


def agreement(first: str, second: str) -> float:
    """WER mellom to modellsvar etter norsk normalisering (første som fasit)."""
    ref = normalize(first)
    hyp = normalize(second)
    if not ref:
        return 0.0 if not hyp else float("inf")
    return word_counts(ref, hyp).error_rate


def check_chunk(st: ChunkStats, th: Thresholds) -> str:
    """Gir ``"ok"`` eller grunnen til at klippet forkastes."""
    if st.duration < th.min_seconds:
        return "too_short"
    if st.duration > th.max_seconds:
        return "too_long"
    if st.max_no_speech_prob > th.max_no_speech_prob:
        return "no_speech"
    if st.avg_logprob < th.min_avg_logprob:
        return "low_confidence"
    if st.max_compression_ratio > th.max_compression_ratio:
        return "compression_ratio"
    norm_words = normalize(st.text).split()
    if repetition_loop(norm_words):
        return "repetition_loop"
    if st.words < th.min_words:
        return "too_few_words"
    if st.words_per_second < th.min_words_per_second:
        return "too_few_words_per_second"
    if st.words_per_second > th.max_words_per_second:
        return "too_many_words_per_second"
    if st.agreement_wer is not None and st.agreement_wer > th.max_disagreement:
        return "models_disagree"
    return "ok"


def _tail(path: str, parts: int = 3) -> str:
    return "/".join(path.replace("\\", "/").lower().split("/")[-parts:])


def _first(row: dict, keys: Iterable[str]):
    for k in keys:
        if row.get(k):
            return row[k]
    return None


def load_exclusions(manifests: Iterable[str], speaker_field: str | None = None) -> tuple[set[str], set[str]]:
    """Lydfiler (siste tre ledd i stien) og eventuelt talere fra de faste
    testsettene. Disse skal aldri bli treningsdata."""
    tails: set[str] = set()
    speakers: set[str] = set()
    for m in manifests:
        with open(m, encoding="utf-8-sig") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                audio = _first(row, AUDIO_KEYS)
                if audio:
                    tails.add(_tail(str(audio)))
                if speaker_field and row.get(speaker_field) not in (None, ""):
                    speakers.add(str(row[speaker_field]))
    return tails, speakers


def write_wav(path: Path, samples, start: float, end: float, sample_rate: int = SAMPLE_RATE) -> None:
    """Skriver utsnittet [start, end) som 16-bit mono PCM. ``samples`` er
    flyttall i [-1, 1], enten en numpy-tabell eller en vanlig sekvens."""
    a = max(0, int(round(start * sample_rate)))
    b = min(len(samples), int(round(end * sample_rate)))
    piece = samples[a:b]
    if hasattr(piece, "astype"):  # numpy
        import numpy as np

        data = (np.clip(piece, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    else:
        pcm = array("h", (int(max(-1.0, min(1.0, float(x))) * 32767.0) for x in piece))
        if sys.byteorder != "little":
            pcm.byteswap()
        data = pcm.tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(data)


# -------------------- modeller


class FasterWhisperTranscriber:
    """faster-whisper med faste innstillinger: strålesøk 5, temperatur 0,
    ingen kontekst fra forrige segment og VAD på (her skal stillhet ikke gi
    tekst, i motsetning til målestokken, der VAD er av for å avsløre
    hallusinasjon)."""

    def __init__(self, model: str, label: str | None = None, device: str = "auto", compute_type: str = "default",
                 beam_size: int = 5, vad_filter: bool = True):
        from faster_whisper import WhisperModel  # importeres først her

        self.model_ref = model
        self.label = label or model
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self._model = WhisperModel(model, device=device, compute_type=compute_type)

    def describe(self) -> dict:
        return {
            "model": self.label,
            "model_ref": self.model_ref,
            "device": self.device,
            "compute_type": self.compute_type,
            "beam_size": self.beam_size,
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "vad_filter": self.vad_filter,
        }

    def load_audio(self, path: str):
        from faster_whisper import decode_audio

        return decode_audio(path, sampling_rate=SAMPLE_RATE)

    def _run(self, audio, language: str, vad_filter: bool):
        segments, _info = self._model.transcribe(
            audio,
            language=language,
            task="transcribe",
            beam_size=self.beam_size,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=vad_filter,
        )
        return list(segments)

    def segments(self, audio, language: str) -> list[Segment]:
        return [
            Segment(float(s.start), float(s.end), s.text, float(s.avg_logprob), float(s.no_speech_prob),
                    float(s.compression_ratio))
            for s in self._run(audio, language, self.vad_filter)
        ]

    def text(self, audio, language: str) -> str:
        # Klippet er allerede kuttet langs tale; VAD av for ikke å kutte ord i kantene.
        return " ".join(s.text.strip() for s in self._run(audio, language, False) if s.text.strip())


# -------------------- kjøring


def _read_rows(inp: str | None, audio_dir: str | None) -> list[dict]:
    if inp:
        with open(inp, encoding="utf-8-sig") as f:
            return [json.loads(line) for line in f if line.strip()]
    root = Path(audio_dir)
    return [{"audio": str(p)} for p in sorted(root.rglob("*")) if p.suffix.lower() in AUDIO_SUFFIXES]


def _append(path: Path, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _clip_id(audio: str, index: int, used: set[str]) -> str:
    stem = re.sub(r"[^\w\-]+", "_", Path(audio).stem)[:80] or "lyd"
    base = f"{stem}_{index:04d}"
    cid = base
    n = 1
    while cid in used:
        n += 1
        cid = f"{base}_{n}"
    used.add(cid)
    return cid


def run(
    rows: list[dict],
    transcriber,
    out_dir: str | Path,
    source: str,
    license_name: str,
    thresholds: Thresholds | None = None,
    second=None,
    exclude_tails: set[str] | None = None,
    exclude_speakers: set[str] | None = None,
    speaker_field: str | None = None,
    exclude_path_contains: list[str] | None = None,
    language: str = "no",
    language_from_meta: str | None = None,
    default_dialect: str | None = None,
    resume: bool = True,
) -> dict:
    check_license(license_name)
    th = thresholds or Thresholds()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    labels_path = out / "pseudo_labels.jsonl"
    rejected_path = out / "rejected.jsonl"
    done_path = out / "done.txt"
    meta_path = out / "run_meta.json"

    identity = {
        "source": source,
        "license": license_name,
        "model": transcriber.describe(),
        "second_model": second.describe() if second else None,
        "thresholds": asdict(th),
        "language": language,
        "language_from_meta": language_from_meta,
    }
    if meta_path.exists() and resume:
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        if old != identity:
            raise SystemExit(f"{out} inneholder en kjøring med andre innstillinger. Bruk en ny --out-dir.")
    elif labels_path.exists() and not resume:
        raise SystemExit(f"{out} inneholder allerede pseudo_labels.jsonl. Bruk en ny --out-dir eller --resume.")
    meta_path.write_text(json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf-8")

    done = set(done_path.read_text(encoding="utf-8").splitlines()) if (resume and done_path.exists()) else set()
    used_ids: set[str] = set()
    if resume and labels_path.exists():
        with open(labels_path, encoding="utf-8") as f:
            used_ids.update(json.loads(line)["id"] for line in f if line.strip())

    exclude_tails = exclude_tails or set()
    exclude_speakers = exclude_speakers or set()
    for row in rows:
        audio = _first(row, AUDIO_KEYS)
        if not audio:
            raise ValueError(f"mangler lydsti: {row}")
        audio = str(audio)
        if audio in done:
            continue
        meta = {k: v for k, v in row.items() if k not in AUDIO_KEYS + TEXT_KEYS + ("id",)}
        if default_dialect and not meta.get("dialect"):
            meta["dialect"] = default_dialect
        base = {"origin_audio": audio, **meta}

        skip = None
        if _tail(audio) in exclude_tails:
            skip = "excluded_fixed_testset"
        elif exclude_path_contains and any(s.lower() in audio.replace("\\", "/").lower() for s in exclude_path_contains):
            skip = "excluded_path_match"
        elif speaker_field and str(row.get(speaker_field, "")) in exclude_speakers:
            skip = "excluded_testset_speaker"
        if skip:
            _append(rejected_path, {**base, "reason": skip})
        else:
            lang = language
            if language_from_meta:
                lang = STANDARD_TO_LANGUAGE.get(str(row.get(language_from_meta, "")).lower(), language)
            try:
                samples = transcriber.load_audio(audio)
                segments = transcriber.segments(samples, lang)
            except Exception as exc:  # noqa: BLE001 - en ødelagt fil skal ikke stoppe kjøringen
                _append(rejected_path, {**base, "reason": "audio_error", "error": f"{type(exc).__name__}: {exc}"})
                segments = []
            for i, chunk in enumerate(chunk_segments(segments, th.max_seconds, th.max_gap_seconds)):
                st = chunk_stats(chunk)
                reason = check_chunk(st, th)
                if reason == "ok" and second is not None:
                    a = max(0, int(round(st.start * SAMPLE_RATE)))
                    b = int(round(st.end * SAMPLE_RATE))
                    st.second_text = second.text(samples[a:b], lang)
                    st.agreement_wer = agreement(st.text, st.second_text)
                    reason = check_chunk(st, th)
                measures = {
                    "start": round(st.start, 3),
                    "end": round(st.end, 3),
                    "duration": round(st.duration, 3),
                    "avg_logprob": round(st.avg_logprob, 4),
                    "max_no_speech_prob": round(st.max_no_speech_prob, 4),
                    "compression_ratio": round(st.max_compression_ratio, 3),
                    "words_per_second": round(st.words_per_second, 3),
                    "agreement_wer": None if st.agreement_wer is None else round(st.agreement_wer, 4),
                }
                if reason != "ok":
                    rej = {**base, **measures, "reason": reason, "text": st.text}
                    if st.second_text is not None:
                        rej["second_text"] = st.second_text
                    _append(rejected_path, rej)
                    continue
                cid = _clip_id(audio, i, used_ids)
                clip = out / "clips" / f"{cid}.wav"
                write_wav(clip, samples, st.start, st.end)
                _append(labels_path, {
                    "id": cid,
                    "audio": str(clip.resolve()),
                    "text": st.text,
                    "source": source,
                    "license": license_name,
                    "pseudo_label": True,
                    "label_model": identity["model"]["model"],
                    "second_model": identity["second_model"]["model"] if second else None,
                    **base,
                    **measures,
                })
        with open(done_path, "a", encoding="utf-8") as f:
            f.write(audio + "\n")
        done.add(audio)

    summary = summarize(labels_path, rejected_path)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def summarize(labels_path: Path, rejected_path: Path) -> dict:
    """Tellinger over hele utmappen (også fra tidligere, gjenopptatte kjøringer)."""

    def read(p: Path) -> list[dict]:
        if not p.exists():
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    kept = read(labels_path)
    rejected = read(rejected_path)
    reasons = Counter(r["reason"] for r in rejected)
    reason_hours = defaultdict(float)
    for r in rejected:
        reason_hours[r["reason"]] += r.get("duration", 0.0) / 3600
    dialects = defaultdict(lambda: {"clips": 0, "hours": 0.0})
    for r in kept:
        d = dialects[str(r.get("dialect") or "ukjent")]
        d["clips"] += 1
        d["hours"] += r["duration"] / 3600
    kept_hours = sum(r["duration"] for r in kept) / 3600
    rejected_hours = sum(reason_hours.values())
    return {
        "kept_clips": len(kept),
        "kept_hours": round(kept_hours, 3),
        "rejected_clips": len(rejected),
        "rejected_hours": round(rejected_hours, 3),
        "kept_share_of_hours": round(kept_hours / (kept_hours + rejected_hours), 4) if kept_hours + rejected_hours else None,
        "rejected_by_reason": dict(sorted(reasons.items())),
        "rejected_hours_by_reason": {k: round(v, 3) for k, v in sorted(reason_hours.items())},
        "kept_by_dialect": {k: {"clips": v["clips"], "hours": round(v["hours"], 3)} for k, v in sorted(dialects.items())},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--in", dest="inp", help="JSONL med lydfiler og metadata")
    src.add_argument("--audio-dir", help="Mappe med lydfiler (søker i undermapper)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--source", required=True, help="Kildenavn, slik det står i dataregisteret")
    ap.add_argument("--license", required=True, help="Lisens, slik den står i dataregisteret")
    ap.add_argument("--model", required=True, help="Modell for pseudo-merking (sti til CTranslate2-modell eller navn)")
    ap.add_argument("--label", default=None)
    ap.add_argument("--second-model", default=None, help="Kontrollmodell; klipp beholdes bare når modellene er enige")
    ap.add_argument("--second-label", default=None)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--compute-type", default="default")
    ap.add_argument("--language", default="no")
    ap.add_argument("--language-from-meta", default=None, help="Metadatafelt med målform (bm -> no, nn -> nn)")
    ap.add_argument("--dialect", default=None, help="Dialekt for rader som mangler feltet «dialect»")
    ap.add_argument("--exclude-manifest", action="append", default=[], help="Faste testsett som aldri skal bli treningsdata")
    ap.add_argument("--exclude-path-contains", action="append", default=[])
    ap.add_argument("--exclude-speaker-field", default=None,
                    help="Utelukk talere fra testsettene ut fra dette feltet. Bare når id-ene kommer fra samme kilde")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="Bare de første N filene (for å prøve terskler)")
    defaults = Thresholds()
    for name, value in asdict(defaults).items():
        ap.add_argument("--" + name.replace("_", "-"), type=type(value), default=value)
    args = ap.parse_args(argv)

    check_license(args.license)
    th = Thresholds(**{k: getattr(args, k) for k in asdict(defaults)})
    rows = _read_rows(args.inp, args.audio_dir)
    if args.limit:
        rows = rows[: args.limit]
    tails, speakers = load_exclusions(args.exclude_manifest, args.exclude_speaker_field)
    first = FasterWhisperTranscriber(args.model, args.label, args.device, args.compute_type)
    second = (FasterWhisperTranscriber(args.second_model, args.second_label, args.device, args.compute_type)
              if args.second_model else None)
    summary = run(
        rows, first, args.out_dir, args.source, args.license, th, second,
        exclude_tails=tails, exclude_speakers=speakers, speaker_field=args.exclude_speaker_field,
        exclude_path_contains=args.exclude_path_contains, language=args.language,
        language_from_meta=args.language_from_meta, default_dialect=args.dialect, resume=not args.no_resume,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
