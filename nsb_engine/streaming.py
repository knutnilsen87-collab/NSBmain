"""Strømmende gjenkjenning: tekst mens noen snakker.

Whisper er laget for hele lydbiter, ikke for strømming. Motoren bruker derfor
samme metode som whisper_streaming (Macháček mfl., 2023): lyden samles i en
buffer, bufferen dekodes på nytt hver gang det har kommet nok ny lyd, og et ord
regnes som ferdig (*committed*) først når to dekodinger etter hverandre er
enige om det (LocalAgreement-2). Ord som ennå ikke er bekreftet, vises som
foreløpige og kan endre seg.

I tillegg:

- Stemmeaktivitetsdeteksjon (VAD): ingen dekoding når bufferen bare er
  stillhet, og en pause på ``endpoint_silence`` sekunder avslutter ytringen,
  slik at teksten blir ferdig uten å vente på neste ord.
- Ordsikkerhet: hvert ord har modellens sannsynlighet, slik at usikre ord kan
  vises som usikre.
- Kontekst: navn og fagord fra saken kan sendes inn (``hotwords``), og den
  siste ferdige teksten brukes som innledning (prompt) ved neste dekoding.

Motoren er uavhengig av modellen: den tar en *backend* med metoden
``transcribe(audio, prompt, hotwords) -> list[Word]``.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Protocol

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Word:
    text: str  # som modellen skrev det, med tegnsetting
    start: float  # sekunder fra strømmens start
    end: float
    probability: float = 1.0
    joined: bool = False  # del av forrige ord (ingen mellomrom foran), for eksempel «.2» i «13.2»

    def shifted(self, offset: float) -> Word:
        return Word(self.text, self.start + offset, self.end + offset, self.probability, self.joined)


def join_words(words: Sequence[Word]) -> str:
    """Setter ordene sammen til tekst, med mellomrom der modellen hadde det."""
    out = []
    for i, w in enumerate(words):
        if i and not w.joined:
            out.append(" ")
        out.append(w.text)
    return "".join(out).strip()


class Backend(Protocol):
    def transcribe(self, audio: np.ndarray, prompt: str | None = None, hotwords: str | None = None) -> list[Word]:
        """Ord med tider relative til starten av ``audio`` (16 kHz, float32)."""


SpeechDetector = Callable[[np.ndarray], list[tuple[float, float]]]


@dataclass
class Update:
    committed: list[Word] = field(default_factory=list)  # nye ferdige ord siden forrige oppdatering
    tentative: list[Word] = field(default_factory=list)  # foreløpige ord (erstatter forrige foreløpige)
    endpoint: bool = False  # en ytring ble avsluttet av en pause
    audio_end: float = 0.0  # hvor mye lyd som var mottatt
    processing_seconds: float = 0.0
    decoded: bool = False

    def to_dict(self) -> dict:
        return {
            "committed": [asdict(w) for w in self.committed],
            "tentative": [asdict(w) for w in self.tentative],
            "endpoint": self.endpoint,
            "audio_end": round(self.audio_end, 3),
            "processing_seconds": round(self.processing_seconds, 4),
        }


_KEY_RE = re.compile(r"[^\w]+", re.UNICODE)


def _key(word: str) -> str:
    """Sammenligningsnøkkel: små bokstaver uten tegnsetting."""
    return _KEY_RE.sub("", word.lower())


def common_prefix(a: Sequence[Word], b: Sequence[Word]) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if _key(x.text) != _key(y.text):
            break
        n += 1
    return n


def _prefix_alignment(done: list[str], hyp: list[str]) -> tuple[int, int]:
    """Finner hvor de ferdige ordene slutter i hypotesen (Levenshtein der
    hypotesen kan ha ekstra ord foran og bak). Gir (antall hypoteseord til og
    med de ferdige ordene, kostnad). Ved likhet velges det seneste stedet, så
    en ny gjetning på det siste ferdige ordet ikke regnes som et nytt ord."""
    n, m = len(done), len(hyp)
    prev = [0] * (m + 1)
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            same = done[i - 1] == hyp[j - 1]
            cur[j] = min(prev[j - 1] + (0 if same else 1), prev[j] + 1, cur[j - 1] + 1)
        prev = cur
    best = min(range(m + 1), key=lambda j: (prev[j], -j))
    return best, prev[best]


def silero_detector(threshold: float = 0.5, min_silence_ms: int = 300) -> SpeechDetector:
    """Taledeteksjon med Silero-VAD fra faster-whisper (lastes ved første bruk)."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    opts = VadOptions(threshold=threshold, min_silence_duration_ms=min_silence_ms, speech_pad_ms=100)

    def detect(audio: np.ndarray) -> list[tuple[float, float]]:
        spans = get_speech_timestamps(audio, opts)
        return [(s["start"] / SAMPLE_RATE, s["end"] / SAMPLE_RATE) for s in spans]

    return detect


class StreamingRecognizer:
    """Tar imot lyd i biter og gir ferdige og foreløpige ord.

    Bruk::

        rec = StreamingRecognizer(backend, detector=silero_detector())
        for chunk in mikrofon:
            rec.insert_audio(chunk)
            update = rec.process()
        update = rec.finish()
    """

    def __init__(
        self,
        backend: Backend,
        *,
        detector: SpeechDetector | None = None,
        min_step: float = 1.0,
        max_buffer: float = 20.0,
        trim_to: float = 12.0,
        endpoint_silence: float = 0.8,
        edge_guard: float = 0.3,
        hotwords: str | None = None,
        prompt_chars: int = 200,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.backend = backend
        self.detector = detector
        self.min_step = min_step
        self.max_buffer = max_buffer
        self.trim_to = trim_to
        self.endpoint_silence = endpoint_silence
        self.edge_guard = edge_guard
        self.hotwords = hotwords
        self.prompt_chars = prompt_chars
        self.clock = clock
        self.reset()

    # ---------- tilstand

    def reset(self) -> None:
        self.buffer = np.zeros(0, dtype=np.float32)
        self.buffer_offset = 0.0  # strømtid ved bufferens start
        self.received = 0.0  # strømtid for siste mottatte sample
        self.last_decoded_at = 0.0  # strømtid da bufferen sist ble dekodet
        self.committed: list[Word] = []
        self.previous: list[Word] = []  # forrige hypotese etter siste ferdige ord
        self.tentative: list[Word] = []
        self._forced: list[Word] = []  # ord gjort ferdige ved kutt, meldes i neste oppdatering

    @property
    def committed_end(self) -> float:
        return self.committed[-1].end if self.committed else self.buffer_offset

    def text(self) -> str:
        return join_words(self.committed)

    def insert_audio(self, chunk: np.ndarray) -> None:
        chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
        self.buffer = np.concatenate([self.buffer, chunk])
        self.received += len(chunk) / SAMPLE_RATE

    # ---------- dekoding

    def _prompt(self) -> str | None:
        """Ferdig tekst fra *før* bufferen. Tekst fra lyd som fortsatt er i
        bufferen, brukes ikke: da kan modellen tro at den allerede er skrevet,
        og hoppe over den."""
        if not self.prompt_chars:
            return None
        before = [w for w in self.committed if w.end <= self.buffer_offset + 0.01]
        return join_words(before)[-self.prompt_chars:] or None

    def _decode(self) -> list[Word]:
        words = self.backend.transcribe(self.buffer, prompt=self._prompt(), hotwords=self.hotwords)
        words = [w.shifted(self.buffer_offset) for w in words if w.text.strip()]
        return self._new_words(words)

    def _new_words(self, words: list[Word]) -> list[Word]:
        """Ordene i hypotesen som kommer etter det som allerede er ferdig.

        Bufferen kan begynne foran siste ferdige ord, og da gjentar hypotesen
        de ferdige ordene først. Hvor de slutter, finnes ved å sammenligne
        teksten, fordi ordtidene kan bomme med et halvt sekund eller mer.
        Tidene brukes bare når teksten ikke passer."""
        inside = [w for w in self.committed if w.end > self.buffer_offset + 0.01]
        if inside and words:
            cut, cost = _prefix_alignment([_key(w.text) for w in inside], [_key(w.text) for w in words])
            if cost <= len(inside) / 2:
                return self._drop_repeated_prefix(words[cut:])
        # Midten av ordet må ligge etter siste ferdige ord: et ord som
        # overlapper det forrige, er en ny gjetning på samme lyd.
        words = [w for w in words if (w.start + w.end) / 2 > self.committed_end]
        return self._drop_repeated_prefix(words)

    def _drop_repeated_prefix(self, words: list[Word]) -> list[Word]:
        """Fjerner ord i starten som gjentar de siste ferdige ordene (opptil 5)."""
        if not self.committed or not words:
            return words
        if abs(words[0].start - self.committed_end) > 1.0:
            return words
        tail = [_key(w.text) for w in self.committed[-5:]]
        head = [_key(w.text) for w in words[:5]]
        for n in range(min(len(tail), len(head)), 0, -1):
            if tail[-n:] == head[:n]:
                return words[n:]
        return words

    def _trim(self) -> None:
        """Kutter bufferen ved siste ferdige ord når den blir lang."""
        length = len(self.buffer) / SAMPLE_RATE
        if length <= self.max_buffer:
            return
        # Ord som har stått lenge uten å bli bekreftet, gjøres ferdige før
        # kuttet, slik at ingen tale kastes.
        limit = self.received - self.trim_to
        forced = [w for w in self.previous if w.end <= limit]
        if forced:
            self.committed.extend(forced)
            self._forced.extend(forced)
            self.previous = self.previous[len(forced):]
            self.tentative = list(self.previous)
        cut = int(round((self.committed_end - self.buffer_offset) * SAMPLE_RATE))
        if cut <= 0:
            return
        self.buffer = self.buffer[cut:]
        self.buffer_offset += cut / SAMPLE_RATE
        self.previous = [w for w in self.previous if w.start >= self.buffer_offset]

    def _cut_after_endpoint(self, at: float) -> None:
        cut = int(round((at - self.buffer_offset) * SAMPLE_RATE))
        if cut > 0:
            self.buffer = self.buffer[cut:]
            self.buffer_offset += cut / SAMPLE_RATE
        self.previous = []

    def _find_pause(self, spans: list[tuple[float, float]]) -> tuple[float | None, float | None]:
        """Første pause på minst ``endpoint_silence`` etter siste ferdige ord.

        Gir (pausens start, der bufferen kan kuttes), i strømtid. Pausen kan
        ligge midt i bufferen (tale har startet igjen) eller på slutten."""
        done = self.committed_end
        for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
            a, b = self.buffer_offset + end, self.buffer_offset + start
            if a > done and b - a >= self.endpoint_silence:
                return a, a + min(0.3, (b - a) / 2)
        last = self.buffer_offset + spans[-1][1]
        if last > done - 0.5 and self.received - last >= self.endpoint_silence:
            return last, last + min(0.3, (self.received - last) / 2)
        return None, None

    def process(self) -> Update:
        """Dekoder bufferen hvis det har kommet nok ny lyd. Kalles etter hver lydbit."""
        update = Update(audio_end=self.received)
        if self.received - self.last_decoded_at < self.min_step:
            update.tentative = list(self.tentative)
            return update
        started = self.clock()
        self.last_decoded_at = self.received

        endpoint_at = resume_at = None
        if self.detector is not None:
            spans = self.detector(self.buffer)
            if not spans:
                # Bare stillhet: ingenting å dekode. Behold litt lyd i tilfelle tale starter.
                keep = int(0.5 * SAMPLE_RATE)
                if len(self.buffer) > keep:
                    drop = len(self.buffer) - keep
                    self.buffer = self.buffer[drop:]
                    self.buffer_offset += drop / SAMPLE_RATE
                self.previous, self.tentative = [], []
                update.processing_seconds = self.clock() - started
                return update
            endpoint_at, resume_at = self._find_pause(spans)

        words = self._decode()
        update.decoded = True
        if endpoint_at is not None:
            # Pause etter tale: alt før pausen er ferdig. Tale etter pausen
            # (hvis bufferen har det) dekodes på nytt fra pausen.
            new = [w for w in words if (w.start + w.end) / 2 < endpoint_at + 0.1]
            update.committed = new
            update.endpoint = True
            self.committed.extend(new)
            self._cut_after_endpoint(max(resume_at, self.committed_end))
            self.tentative = [w for w in words[len(new):] if w.start >= self.buffer_offset]
        else:
            n = common_prefix(self.previous, words)
            # Et ord som slutter helt ved bufferens ende, kan være halvt uttalt,
            # og to like gjetninger på et halvt ord skal ikke bli ferdige.
            while n and words[n - 1].end > self.received - self.edge_guard:
                n -= 1
            # Ordtidene varierer mellom dekodinger, og et ord kan få en slutt
            # som strekker seg inn i neste ord. Den tidligste av de to
            # slutt-tidene brukes, så neste ord ikke blir regnet som allerede ferdig.
            new = [
                Word(w.text, w.start, max(w.start, min(w.end, p.end)), w.probability, w.joined)
                for w, p in zip(words[:n], self.previous[:n], strict=True)
            ]
            self.committed.extend(new)
            update.committed = new
            self.previous = words[n:]
            self.tentative = list(self.previous)
            self._trim()
            if self._forced:
                update.committed = update.committed + self._forced
                self._forced = []
        update.tentative = list(self.tentative)
        update.processing_seconds = self.clock() - started
        return update

    def finish(self) -> Update:
        """Slutt på lyden: alt som gjenstår, blir ferdig."""
        started = self.clock()
        update = Update(audio_end=self.received, endpoint=True)
        has_speech = True
        if self.detector is not None and len(self.buffer):
            has_speech = bool(self.detector(self.buffer))
        if len(self.buffer) and has_speech:
            words = self._decode()
            update.decoded = True
            self.committed.extend(words)
            update.committed = words
        self.previous, self.tentative = [], []
        self.buffer = np.zeros(0, dtype=np.float32)
        self.buffer_offset = self.received
        update.processing_seconds = self.clock() - started
        return update


class FasterWhisperBackend:
    """Backend med faster-whisper. Samme dekoding som målestokken, med ordtider."""

    def __init__(
        self,
        model_path: str,
        *,
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = "no",
        beam_size: int = 5,
    ) -> None:
        from faster_whisper import WhisperModel

        if device == "cpu" and compute_type == "float16":
            compute_type = "int8"
        self.model = WhisperModel(model_path, device=device, compute_type=compute_type)
        self.language = language
        self.beam_size = beam_size

    def transcribe(self, audio: np.ndarray, prompt: str | None = None, hotwords: str | None = None) -> list[Word]:
        if len(audio) < SAMPLE_RATE // 10:
            return []
        segments, _ = self.model.transcribe(
            audio,
            language=self.language,
            task="transcribe",
            beam_size=self.beam_size,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=prompt,
            hotwords=hotwords,
            word_timestamps=True,
            vad_filter=False,
        )
        out = []
        for seg in segments:
            for i, w in enumerate(seg.words or []):
                raw = w.word
                if not raw.strip():
                    continue
                joined = i > 0 and not raw[:1].isspace()
                out.append(Word(raw.strip(), float(w.start), float(w.end), float(w.probability), joined))
        return out
