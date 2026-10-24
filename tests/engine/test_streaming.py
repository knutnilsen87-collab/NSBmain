import numpy as np
import pytest

from nsb_engine.streaming import SAMPLE_RATE, StreamingRecognizer, Word, common_prefix

# Talen i strømmen: (ord, start, slutt) i sekunder.
SCRIPT = [
    ("Tiltalte", 0.2, 0.8), ("nektet", 0.9, 1.4), ("straffskyld", 1.5, 2.3), ("for", 2.4, 2.6),
    ("forholdet", 2.7, 3.4), ("i", 3.5, 3.6), ("tiltalebeslutningen.", 3.7, 4.8),
    # pause 4.8–7.0
    ("Vitnet", 7.0, 7.5), ("forklarte", 7.6, 8.2), ("seg.", 8.3, 8.8),
]


class ScriptedBackend:
    """Gir ordene som er ferdig uttalt i bufferen. Det siste ordet som akkurat
    er påbegynt, blir gjettet feil (som en ekte modell midt i et ord)."""

    def __init__(self, script=SCRIPT):
        self.script = script
        self.offset = 0.0  # settes av testen via recognizer.buffer_offset
        self.calls = 0
        self.prompts = []

    def transcribe(self, audio, prompt=None, hotwords=None):
        self.calls += 1
        self.prompts.append((prompt, hotwords))
        start = self.rec.buffer_offset
        end = start + len(audio) / SAMPLE_RATE
        out = []
        for text, s, e in self.script:
            if s >= start - 0.05 and e <= end:
                out.append(Word(text, s - start, e - start, 0.9))
            elif s >= start and s < end < e:
                out.append(Word(text[:2] + "x", s - start, end - start, 0.3))  # halvt ord, feil
        return out


def script_detector(rec):
    def detect(audio):
        start = rec.buffer_offset
        end = start + len(audio) / SAMPLE_RATE
        spans = []
        for _, s, e in SCRIPT:
            if e > start and s < end:
                spans.append((max(s, start) - start, min(e, end) - start))
        return spans

    return detect


def run(rec, seconds, chunk=0.25):
    updates = []
    n = int(round(seconds / chunk))
    for _ in range(n):
        rec.insert_audio(np.zeros(int(chunk * SAMPLE_RATE), dtype=np.float32))
        updates.append(rec.process())
    updates.append(rec.finish())
    return updates


def make(**kw):
    backend = ScriptedBackend()
    rec = StreamingRecognizer(backend, **kw)
    backend.rec = rec
    return rec, backend


def test_all_words_committed_once_in_order():
    rec, _ = make(min_step=0.5)
    run(rec, 9.5)
    assert [w.text for w in rec.committed] == [t for t, _, _ in SCRIPT]


def test_half_words_are_never_committed():
    rec, _ = make(min_step=0.5)
    updates = run(rec, 9.5)
    committed = [w.text for u in updates for w in u.committed]
    assert not any(t.endswith("x") for t in committed)
    # men de vises som foreløpige underveis
    assert any(w.text.endswith("x") for u in updates for w in u.tentative)


def test_words_need_two_agreeing_decodings():
    rec, _ = make(min_step=0.5)
    rec.insert_audio(np.zeros(int(1.5 * SAMPLE_RATE), dtype=np.float32))
    first = rec.process()
    assert first.committed == [] and [w.text for w in first.tentative][:2] == ["Tiltalte", "nektet"]
    rec.insert_audio(np.zeros(int(0.5 * SAMPLE_RATE), dtype=np.float32))
    second = rec.process()
    assert [w.text for w in second.committed] == ["Tiltalte", "nektet"]


def test_pause_ends_utterance_with_vad():
    rec, backend = make(min_step=0.5, endpoint_silence=0.8)
    rec.detector = script_detector(rec)
    updates = run(rec, 9.5)
    endpoints = [u for u in updates[:-1] if u.endpoint]
    assert endpoints, "pausen etter første setning skal avslutte ytringen"
    first = endpoints[0]
    assert first.audio_end < 7.0  # før neste setning begynner
    assert rec.committed[6].text == "tiltalebeslutningen."
    assert [w.text for w in rec.committed] == [t for t, _, _ in SCRIPT]


def test_silence_is_not_decoded_with_vad():
    rec, backend = make(min_step=0.5)
    rec.detector = lambda audio: []
    run(rec, 5.0)
    assert backend.calls == 0 and rec.committed == []


def test_long_buffer_is_trimmed_without_losing_words():
    rec, _ = make(min_step=0.5, max_buffer=3.0, trim_to=2.0)
    run(rec, 9.5)
    assert len(rec.buffer) == 0
    assert [w.text for w in rec.committed] == [t for t, _, _ in SCRIPT]


def test_text_before_buffer_is_used_as_prompt_and_hotwords_are_passed():
    rec, backend = make(min_step=0.5, hotwords="Bjørdal Giske", max_buffer=3.0, trim_to=2.0)
    run(rec, 6.0)
    assert backend.prompts[0] == (None, "Bjørdal Giske")
    assert all(h == "Bjørdal Giske" for _, h in backend.prompts)
    prompted = [p for p, _ in backend.prompts if p]
    assert prompted and prompted[-1].startswith("Tiltalte")


def test_prompt_never_contains_audio_still_in_buffer():
    rec, _ = make()
    rec.committed = [Word("a", 0.0, 0.5), Word("b", 0.5, 1.0), Word("c", 1.0, 1.5)]
    rec.buffer_offset = 1.0
    assert rec._prompt() == "a b"


def test_common_prefix_ignores_case_and_punctuation():
    a = [Word("Han", 0, 1), Word("nektet,", 1, 2), Word("ikke", 2, 3)]
    b = [Word("han", 0, 1), Word("nektet", 1, 2), Word("ikkje", 2, 3)]
    assert common_prefix(a, b) == 2


def test_pause_inside_buffer_ends_utterance_even_with_coarse_steps():
    rec, _ = make(min_step=3.0, endpoint_silence=0.8)
    rec.detector = script_detector(rec)
    updates = run(rec, 9.5)
    assert any(u.endpoint for u in updates[:-1])
    assert [w.text for w in rec.committed] == [t for t, _, _ in SCRIPT]


def test_overlapping_guesses_are_not_committed_twice():
    class Jitter(ScriptedBackend):
        def transcribe(self, audio, prompt=None, hotwords=None):
            words = super().transcribe(audio, prompt, hotwords)
            # Ny dekoding gir et ord som overlapper det siste ferdige ordet.
            if self.rec.committed:
                last = self.rec.committed[-1]
                s = last.start - self.rec.buffer_offset
                words.insert(0, Word("gjetning", s - 0.05, s + (last.end - last.start) * 0.9, 0.5))
            return words

    backend = Jitter()
    rec = StreamingRecognizer(backend, min_step=0.5)
    backend.rec = rec
    run(rec, 9.5)
    assert "gjetning" not in [w.text for w in rec.committed]


def test_new_words_found_by_text_when_times_are_wrong():
    from nsb_engine.streaming import _prefix_alignment

    rec, _ = make()
    rec.committed = [Word("pleaded", 1.7, 2.3), Word("guilty.", 2.3, 3.3)]
    rec.buffer_offset = 0.5
    # Ny dekoding gjentar de ferdige ordene, men gir «The court» tider før 3,3 s.
    hyp = [Word("The", 0.5, 1.2), Word("defendant", 1.2, 1.7), Word("pleaded", 1.7, 2.2), Word("guilty.", 2.2, 2.6),
           Word("The", 2.6, 2.8), Word("court", 2.8, 3.0), Word("finds", 3.0, 3.5)]
    assert [w.text for w in rec._new_words(hyp)] == ["The", "court", "finds"]
    assert _prefix_alignment(["a", "b"], ["x", "a", "b", "c"]) == (3, 0)
    assert _prefix_alignment(["a", "b"], ["a", "q", "c"]) == (2, 1)


def test_words_the_model_wavered_on_get_revisions():
    class Wavering(ScriptedBackend):
        def transcribe(self, audio, prompt=None, hotwords=None):
            words = super().transcribe(audio, prompt, hotwords)  # teller kallet
            # «nektet» gjettes som «nekta» i annenhver dekoding før det blir ferdig.
            if self.calls % 2 == 1:
                words = [Word("nekta", w.start, w.end, w.probability) if w.text == "nektet" else w for w in words]
            return words

    backend = Wavering()
    rec = StreamingRecognizer(backend, min_step=0.5)
    backend.rec = rec
    run(rec, 9.5)
    by_text = {w.text: w for w in rec.committed}
    assert by_text["Tiltalte"].revisions == 0
    assert (by_text.get("nektet") or by_text.get("nekta")).revisions >= 1


def test_backend_falls_back_when_word_alignment_fails():
    from types import SimpleNamespace

    from nsb_engine.streaming import FasterWhisperBackend

    class Model:
        def transcribe(self, audio, word_timestamps, **kw):
            if word_timestamps:
                def broken():
                    raise IndexError("boolean index did not match")
                    yield  # pragma: no cover
                return broken(), None
            return iter([SimpleNamespace(text=" Han nektet", start=1.0, end=2.0, words=None)]), None

    b = FasterWhisperBackend.__new__(FasterWhisperBackend)
    b.model, b.language, b.beam_size, b.alignment_fallbacks = Model(), "no", 1, 0
    b._decode, b.collapse = {"temperature": 0.0}, True
    words = b.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))
    assert [(w.text, w.start, w.end) for w in words] == [("Han", 1.0, 1.5), ("nektet", 1.5, 2.0)]
    assert b.alignment_fallbacks == 1 and words[0].probability == 0.0


def test_speech_chunks_merge_short_gaps_and_split_long_speech():
    from nsb_engine.streaming import speech_chunks

    assert speech_chunks([(0.0, 3.0), (3.5, 6.0), (10.0, 12.0)]) == [(0.0, 6.0), (10.0, 12.0)]
    assert speech_chunks([(0.0, 20.0), (20.5, 40.0)], max_chunk=28.0) == [(0.0, 20.0), (20.5, 40.0)]
    assert speech_chunks([(0.0, 60.0)], max_chunk=28.0) == [(0.0, 28.0), (28.0, 56.0), (56.0, 60.0)]


def test_transcribe_long_decodes_only_speech_with_absolute_times():
    import numpy as np

    from nsb_engine.streaming import SAMPLE_RATE, Word, transcribe_long

    calls = []

    class Backend:
        def transcribe(self, audio, prompt=None, hotwords=None):
            calls.append((len(audio) / SAMPLE_RATE, hotwords))
            return [Word("ord", 0.3, 0.6, 0.9)]

    audio = np.zeros(100 * SAMPLE_RATE, dtype=np.float32)
    words, chunks = transcribe_long(Backend(), audio, lambda a: [(10.0, 12.0), (50.0, 51.0)], hotwords="Silje")
    assert chunks == [(10.0, 12.0), (50.0, 51.0)]
    assert len(calls) == 2 and all(h == "Silje" for _, h in calls)
    assert calls[0][0] == pytest.approx(2.4)  # 0,2 s ekstra på hver side
    assert [round(w.start, 2) for w in words] == [10.1, 50.1]


def test_backend_collapses_repetition_loops_and_passes_decoding_profile():
    from types import SimpleNamespace

    from nsb_engine.streaming import FasterWhisperBackend

    seen = {}

    class Model:
        def transcribe(self, audio, **kw):
            seen.update(kw)
            ws = [SimpleNamespace(word=f" {t}", start=i * 0.2, end=i * 0.2 + 0.15, probability=0.9)
                  for i, t in enumerate(["det", "det", "det", "det", "det", "handlar", "om."])]
            return iter([SimpleNamespace(text="", start=0.0, end=2.0, words=ws)]), None

    b = FasterWhisperBackend.__new__(FasterWhisperBackend)
    b.model, b.language, b.beam_size, b.alignment_fallbacks = Model(), "no", 1, 0
    from nsb_eval.decoding import profile

    b._decode, b.collapse = profile("loopvakt"), True
    words = b.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))
    assert [w.text for w in words] == ["det", "det", "handlar", "om."]
    assert seen["temperature"] == (0.0, 0.2, 0.4) and seen["compression_ratio_threshold"] == 2.4
