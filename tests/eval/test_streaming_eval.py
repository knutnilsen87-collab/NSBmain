import numpy as np

from nsb_engine.streaming import SAMPLE_RATE, StreamingRecognizer, Word
from nsb_eval.manifest import Item
from nsb_eval.streaming_eval import build_streams, confidence_table, simulate, word_errors


class Scripted:
    script = [("han", 0.1, 0.4), ("nektet", 0.5, 1.0), ("straffskyld", 1.1, 1.9), ("for", 2.0, 2.2), ("alt", 2.3, 2.6)]

    def transcribe(self, audio, prompt=None, hotwords=None):
        start = self.rec.buffer_offset
        end = start + len(audio) / SAMPLE_RATE
        return [Word(t, s - start, e - start, 0.9) for t, s, e in self.script if s >= start - 0.05 and e <= end]


def test_simulate_measures_latency_and_changes():
    backend = Scripted()
    ticks = iter(range(10_000))
    rec = StreamingRecognizer(backend, min_step=0.5, clock=lambda: next(ticks) * 0.01)
    backend.rec = rec
    res = simulate(rec, np.zeros(int(3.0 * SAMPLE_RATE), dtype=np.float32), chunk=0.25)
    assert [w.text for w in res["words"]] == [t for t, _, _ in Scripted.script]
    assert all(lat >= 0 for lat in res["commit_latency"])
    assert all(d <= c + 1e-9 for d, c in zip(res["display_latency"], res["commit_latency"], strict=True))
    assert res["changes"] == 0  # skriptet endrer aldri et vist ord


def test_word_errors_maps_normalized_tokens_back_to_words():
    words = [Word("Han", 0, 1), Word("nekta", 1, 2), Word("2025.", 2, 3), Word("ja", 3, 4)]
    assert word_errors("han nektet to tusen og tjuefem", words) == [False, True, False, True]


def test_confidence_table_precision_and_recall():
    pairs = [(0.2, True), (0.4, True), (0.6, False), (0.95, False), (0.95, True)]
    t = confidence_table(pairs)
    half = next(x for x in t["thresholds"] if x["below"] == 0.5)
    assert half["flagged_share"] == 0.4 and half["precision"] == 1.0 and half["recall"] == round(2 / 3, 4)
    assert t["bins"][0]["words"] == 1 and t["bins"][-1]["error_rate"] == 0.5


def test_build_streams_respects_length():
    items = [Item(str(i), "", "x") for i in range(5)]
    streams = build_streams(items, 10.0, {str(i): 4.0 for i in range(5)})
    assert [len(s) for s in streams] == [2, 2, 1]
