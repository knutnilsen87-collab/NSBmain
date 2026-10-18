import json
import wave

import pytest

from pseudo_label import (
    ChunkStats,
    Segment,
    Thresholds,
    check_chunk,
    check_license,
    chunk_segments,
    chunk_stats,
    load_exclusions,
    run,
    write_wav,
)

SR = 16000


def seg(start, end, text, logprob=-0.2, no_speech=0.05, compression=1.4):
    return Segment(start, end, text, logprob, no_speech, compression)


class FakeTranscriber:
    """Svarer med faste segmenter per fil. Lyden er stillhet med riktig lengde."""

    def __init__(self, segments_by_file, label="fake", seconds=60.0, texts=None, fail=()):
        self.segments_by_file = segments_by_file
        self.label = label
        self.seconds = seconds
        self.texts = texts or []
        self.fail = set(fail)
        self.text_calls = 0

    def describe(self):
        return {"model": self.label}

    def load_audio(self, path):
        if path in self.fail:
            raise RuntimeError("ødelagt fil")
        self._current = path
        return [0.0] * int(SR * self.seconds)

    def segments(self, audio, language):
        return list(self.segments_by_file.get(self._current, []))

    def text(self, audio, language):
        t = self.texts[self.text_calls]
        self.text_calls += 1
        return t


def test_license_check():
    check_license("CC0 1.0")
    check_license("CC BY 4.0")
    check_license("CC BY-SA 4.0")
    for bad in ("CC BY-NC 4.0", "CC BY-ND 4.0", "CLARIN ACA-NC-LOC-PRIV-ND", ""):
        with pytest.raises(ValueError):
            check_license(bad)


def test_chunking_respects_length_and_pauses():
    segs = [
        seg(0, 10, "a"),
        seg(10.5, 20, "b"),
        seg(20.2, 29, "c"),
        seg(29.5, 35, "d"),  # ville gjort klippet 35 s langt
        seg(40, 45, "e"),  # pause på 5 s
        seg(45.1, 46, "   "),  # tom tekst hoppes over
    ]
    chunks = chunk_segments(segs, max_seconds=30, max_gap=1.5)
    assert [[s.text for s in c] for c in chunks] == [["a", "b", "c"], ["d"], ["e"]]


def test_chunk_stats_weights_logprob_by_duration():
    st = chunk_stats([seg(0, 9, "en to tre", logprob=-0.1), seg(9, 10, "fire", logprob=-1.0, no_speech=0.3)])
    assert st.words == 4
    assert st.duration == 10
    assert st.avg_logprob == pytest.approx((-0.1 * 9 - 1.0) / 10)
    assert st.max_no_speech_prob == 0.3


def _stats(**kw):
    base = dict(start=0.0, end=4.0, text="dette er en helt vanlig setning", words=6, avg_logprob=-0.2,
                max_no_speech_prob=0.05, max_compression_ratio=1.5)
    base.update(kw)
    return ChunkStats(**base)


@pytest.mark.parametrize(
    "kw,reason",
    [
        ({}, "ok"),
        ({"end": 0.5}, "too_short"),
        ({"end": 31.0, "words": 60}, "too_long"),
        ({"max_no_speech_prob": 0.9}, "no_speech"),
        ({"avg_logprob": -0.9}, "low_confidence"),
        ({"max_compression_ratio": 3.0}, "compression_ratio"),
        ({"text": "ja ja ja ja ja ja", "words": 6}, "repetition_loop"),
        ({"text": "ja takk", "words": 2}, "too_few_words"),
        ({"end": 20.0}, "too_few_words_per_second"),  # 6 ord på 20 s: modellen har trolig utelatt tale
        ({"end": 1.0, "words": 8, "text": "en to tre fire fem seks sju åtte"}, "too_many_words_per_second"),
        ({"agreement_wer": 0.5}, "models_disagree"),
        ({"agreement_wer": 0.1}, "ok"),
    ],
)
def test_check_chunk_reasons(kw, reason):
    assert check_chunk(_stats(**kw), Thresholds()) == reason


def test_write_wav_cuts_requested_span(tmp_path):
    samples = [0.5] * SR * 3
    p = tmp_path / "x.wav"
    write_wav(p, samples, 1.0, 2.5)
    with wave.open(str(p), "rb") as w:
        assert w.getframerate() == SR
        assert w.getnchannels() == 1
        assert w.getnframes() == int(SR * 1.5)


def test_load_exclusions(tmp_path):
    m = tmp_path / "test.jsonl"
    m.write_text(
        json.dumps({"audio": "dataset/nb_samtale/data/test/bm/a.wav", "text": "x", "speaker_id": "P1"}) + "\n",
        encoding="utf-8",
    )
    tails, speakers = load_exclusions([str(m)], "speaker_id")
    assert tails == {"test/bm/a.wav"}
    assert speakers == {"P1"}


def _good_file_segments():
    return [
        seg(0.0, 4.0, "Det var en gang en gutt som bodde på gården."),
        seg(4.2, 8.0, "Han gikk ut hver morgen for å se til dyra."),
        seg(12.0, 12.4, "ja"),  # for kort
        seg(14.0, 18.0, "Men så en dag kom det en fremmed.", logprob=-1.2),  # lav sikkerhet
    ]


def test_run_end_to_end(tmp_path):
    rows = [
        {"audio": "podkast/vest/ep1.mp3", "dialect": "vest", "speaker_id": "S1"},
        {"audio": "podkast/vest/ep2.mp3", "speaker_id": "S2"},
        {"audio": "dataset/nb_samtale/data/test/bm/a.wav", "dialect": "øst"},
        {"audio": "podkast/vest/broken.mp3", "dialect": "vest"},
    ]
    t = FakeTranscriber(
        {"podkast/vest/ep1.mp3": _good_file_segments(), "podkast/vest/ep2.mp3": _good_file_segments()[:2]},
        fail={"podkast/vest/broken.mp3"},
    )
    out = tmp_path / "out"
    summary = run(rows, t, out, "Podkast X", "CC BY 4.0", exclude_tails={"test/bm/a.wav"}, default_dialect="ukjent-vest")

    labels = [json.loads(line) for line in (out / "pseudo_labels.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(labels) == 2
    first = labels[0]
    assert first["text"].startswith("Det var en gang")
    assert first["dialect"] == "vest" and first["speaker_id"] == "S1"
    assert first["source"] == "Podkast X" and first["license"] == "CC BY 4.0" and first["pseudo_label"] is True
    assert first["origin_audio"] == "podkast/vest/ep1.mp3"
    assert first["start"] == 0.0 and first["end"] == 8.0
    assert labels[1]["dialect"] == "ukjent-vest"
    with wave.open(first["audio"], "rb") as w:
        assert w.getnframes() == 8 * SR

    reasons = summary["rejected_by_reason"]
    assert reasons == {"audio_error": 1, "excluded_fixed_testset": 1, "low_confidence": 1, "too_short": 1}
    assert summary["kept_clips"] == 2
    assert summary["kept_by_dialect"]["vest"]["clips"] == 1


def test_run_resume_skips_done_files_and_refuses_changed_settings(tmp_path):
    rows = [{"audio": "a.mp3"}]
    t = FakeTranscriber({"a.mp3": _good_file_segments()[:2]})
    out = tmp_path / "out"
    run(rows, t, out, "Kilde", "CC0 1.0")
    run(rows + [{"audio": "b.mp3"}], t, out, "Kilde", "CC0 1.0")
    labels = (out / "pseudo_labels.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(labels) == 1  # a.mp3 ble ikke merket på nytt; b.mp3 har ingen segmenter
    assert (out / "done.txt").read_text(encoding="utf-8").splitlines() == ["a.mp3", "b.mp3"]
    with pytest.raises(SystemExit):
        run(rows, t, out, "Kilde", "CC0 1.0", thresholds=Thresholds(min_avg_logprob=-0.3))


def test_second_model_must_agree(tmp_path):
    segs = {
        "a.mp3": [seg(0, 4, "Vi skal ikke reise i morgen.")],
        "b.mp3": [seg(0, 4, "Vi skal ikke reise i morgen.")],
    }
    first = FakeTranscriber(segs)
    second = FakeTranscriber({}, label="kontroll", texts=["vi skal ikke reise i morgen", "vi skal reise i morgen tidlig"])
    out = tmp_path / "out"
    summary = run([{"audio": "a.mp3"}, {"audio": "b.mp3"}], first, out, "Kilde", "CC0 1.0", second=second)
    assert summary["kept_clips"] == 1
    assert summary["rejected_by_reason"] == {"models_disagree": 1}
    rejected = json.loads((out / "rejected.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert rejected["second_text"] == "vi skal reise i morgen tidlig"
    assert rejected["agreement_wer"] > 0.15


def test_forbidden_license_stops_before_any_work(tmp_path):
    with pytest.raises(ValueError, match="kommersiell"):
        run([{"audio": "a.mp3"}], FakeTranscriber({}), tmp_path / "out", "LIA", "CLARIN ACA-NC-LOC-PRIV-ND")
    assert not (tmp_path / "out").exists()
