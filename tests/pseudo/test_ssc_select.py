import json

import pytest

from pseudo_label import Segment, chunk_stats
from ssc_select import (
    FieldMap,
    SelectThresholds,
    decide,
    detect_fields,
    detect_standard,
    inspect,
    main,
    run,
    sample,
)

SR = 16000


def seg(text, start=0.0, end=5.0, logprob=-0.2, no_speech=0.02, compression=1.4):
    return Segment(start, end, text, logprob, no_speech, compression)


class FakeTranscriber:
    """Faste svar per lydfil (filnavn). Lyden er stillhet med riktig lengde."""

    def __init__(self, answers, label="fake", seconds=5.0, follows=None):
        self.answers = answers
        self.follows = follows  # kontrollmodellen svarer for samme fil som hovedmodellen
        self.label = label
        self.seconds = seconds
        self.calls = 0

    def describe(self):
        return {"model": self.label}

    def load_audio(self, path):
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name not in self.answers:
            raise FileNotFoundError(path)
        self._current = name
        return [0.0] * int(SR * self.seconds)

    def segments(self, audio, language):
        assert language == "no"
        return [seg(self.answers[self._current])]

    def text(self, audio, language):
        self.calls += 1
        return self.answers[(self.follows or self)._current]


def stats(text, **kw):
    return chunk_stats([seg(text, **kw)])


def test_detect_standard():
    assert detect_standard("Eg meiner at dette ikkje er rett, og vi må sjå på kva som skjer") == "nn"
    assert detect_standard("Jeg mener at dette ikke er riktig, og vi må se på hva som skjer") == "bm"
    assert detect_standard("Takk, president.") is None


def test_detect_fields_and_overrides():
    rows = [{"segment_id": "a", "audio_path": "x.wav", "proceedings": "t", "speaker_name": "Ola", "meeting_date": "2019-01-01",
             "start": 0, "end": 5}] * 3
    fm = detect_fields(rows)
    assert (fm.id, fm.audio, fm.text, fm.speaker, fm.date, fm.start, fm.end) == (
        "segment_id", "audio_path", "proceedings", "speaker_name", "meeting_date", "start", "end")
    assert detect_fields(rows, {"text": "other"}).text == "other"


TH = SelectThresholds()
BM = "Vi må sikre at alle kommuner får nok penger til eldreomsorgen i hele landet."


def test_decide_uses_referat_when_model_confirms_it():
    hyp = "vi må sikre at alle kommuner får nok penger til eldreomsorgen i hele landet"
    d = decide(BM, "bm", hyp, stats(hyp), 5.0, TH)
    assert (d.reason, d.label_source, d.text) == ("ok", "referat", BM)
    assert d.referat_wer == 0.0


def test_decide_edited_referat_needs_second_model():
    hyp = "vi må jo sikre at alle kommunene får nok penger til eldreomsorgen rundt omkring i hele landet"
    d = decide(BM, "bm", hyp, stats(hyp), 5.0, TH)
    assert d.reason == "needs_second_model"
    agree = decide(BM, "bm", hyp, stats(hyp), 5.0, TH, second_text=lambda: hyp)
    assert (agree.reason, agree.label_source, agree.text) == ("ok", "model", hyp)
    disagree = decide(BM, "bm", hyp, stats(hyp), 5.0, TH, second_text=lambda: "vi må sikre kommunene penger")
    assert disagree.reason == "models_disagree"


def test_decide_nynorsk_referat_gives_bokmal_model_text():
    nn = "Vi må sikre at alle kommunane får nok pengar til eldreomsorga i heile landet, det er ikkje godt nok i dag."
    hyp = "vi må sikre at alle kommunene får nok penger til eldreomsorgen i hele landet det er ikke godt nok i dag"
    d = decide(nn, "nn", hyp, stats(hyp), 6.0, TH, second_text=lambda: hyp)
    assert (d.reason, d.label_source, d.text) == ("ok", "model", hyp)


def test_decide_rejects_omissions_and_mismatch():
    short = "vi må sikre at alle kommuner får nok penger"
    d = decide(BM, "bm", short, stats(short), 5.0, TH, second_text=lambda: short)
    assert d.reason == "omits_words" and d.referat_deletion > 0.15
    other = "dette handler om noe helt annet enn det som står i referatet"
    assert decide(BM, "bm", other, stats(other), 5.0, TH, second_text=lambda: other).reason == "referat_mismatch"


@pytest.mark.parametrize(
    "kw,duration,reason",
    [
        ({"no_speech": 0.9}, 5.0, "no_speech"),
        ({"logprob": -1.0}, 5.0, "low_confidence"),
        ({"compression": 3.0}, 5.0, "compression_ratio"),
        ({}, 0.5, "too_short"),
        ({}, 31.0, "too_long"),
    ],
)
def test_decide_model_checks(kw, duration, reason):
    hyp = BM.lower()
    assert decide(BM, "bm", hyp, stats(hyp, **kw), duration, TH).reason == reason


def test_second_model_only_called_when_needed():
    calls = []

    def second():
        calls.append(1)
        return BM

    decide(BM, "bm", BM, stats(BM), 5.0, TH, second_text=second)
    assert calls == []


def test_sample_caps_speaker_hours():
    items = [{"id": f"s{i}", "speaker": "A" if i % 2 else "B", "dialect": "ukjent", "duration": 1800.0} for i in range(10)]
    kept = sample(items, None, 1.0, None)
    assert sorted(it["speaker"] for it in kept) == ["A", "A", "B", "B"]
    assert sample(items, None, None, None) is items


def _corpus(tmp_path):
    root = tmp_path / "ssc"
    (root / "text").mkdir(parents=True)
    (root / "text" / "c.txt").write_text(
        "Eg meiner at kommunane må få meir pengar til skulen, og det er ikkje gjort i dag.", encoding="utf-8")
    rows = [
        {"segment_id": "a", "audio_path": "audio/a.wav", "text": BM, "speaker_id": "S1", "meeting_date": "2019-03-01",
         "duration": 5.0},
        {"segment_id": "b", "audio_path": "audio/b.wav", "text": BM, "speaker_id": "S2", "meeting_date": "2019-03-01",
         "duration": 5.0},
        {"segment_id": "c", "audio_path": "audio/c.wav", "text": "text/c.txt", "speaker_id": "S3",
         "meeting_date": "2019-03-02", "duration": 5.0},
        {"segment_id": "d", "audio_path": "audio/d.wav", "text": BM, "speaker_id": "S1", "meeting_date": "2017-02-07",
         "duration": 5.0},
        {"segment_id": "e", "audio_path": "audio/missing.wav", "text": BM, "speaker_id": "S4",
         "meeting_date": "2019-03-03", "duration": 5.0},
    ]
    manifest = root / "ssc.jsonl"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    meta = tmp_path / "speakers.csv"
    meta.write_text("speaker_id,dialect\nS1,vest\nS2,nord\nS3,vest\n", encoding="utf-8")
    answers = {
        "a.wav": BM.lower(),  # bekrefter referatet
        "b.wav": "noe helt annet som ikke står i referatet i det hele tatt",  # forkastes
        "c.wav": "jeg mener at kommunene må få mer penger til skolen og det er ikke gjort i dag",  # nynorsk -> bokmål
    }
    return root, manifest, meta, rows, answers


def test_run_end_to_end(tmp_path):
    from ssc_select import load_speaker_meta

    root, manifest, meta, rows, answers = _corpus(tmp_path)
    fm = detect_fields(rows)
    out = tmp_path / "out"
    first = FakeTranscriber(answers)
    second = FakeTranscriber(answers, label="kontroll", follows=first)
    summary = run(rows, fm, root, first, out, second=second, speaker_meta=load_speaker_meta(str(meta)))

    labels = {r["id"]: r for r in map(json.loads, (out / "labels.jsonl").read_text(encoding="utf-8").splitlines())}
    assert set(labels) == {"a", "c"}
    assert labels["a"]["label_source"] == "referat" and labels["a"]["text"] == BM
    assert labels["a"]["dialect"] == "vest" and labels["a"]["standard"] == "bm"
    assert labels["c"]["label_source"] == "model" and labels["c"]["referat_standard"] == "nn"
    assert labels["c"]["text"].startswith("jeg mener") and labels["c"]["pseudo_label"] is True
    assert summary["excluded_before_transcription"] == {"excluded_locked_test_meeting": 1}
    assert set(summary["rejected_by_reason"]) == {"referat_mismatch", "audio_error"}
    assert summary["kept_by_label_source"]["referat"]["segments"] == 1
    assert second.calls == 1  # bare for c; a ble bekreftet av referatet, b forkastet før kontroll

    again = run(rows, fm, root, first, out, second=second, speaker_meta=load_speaker_meta(str(meta)))
    assert again["kept_segments"] == 2  # ingenting merket på nytt
    with pytest.raises(SystemExit):
        run(rows, fm, root, first, out, th=SelectThresholds(max_referat_wer=0.2), second=second)


def test_inspect_and_cli(tmp_path, capsys):
    root, manifest, meta, rows, _ = _corpus(tmp_path)
    info = inspect(rows, detect_fields(rows), root)
    assert info["segments_after_exclusion"] == 4
    assert info["field_map"]["text"] == "text"
    # For få kjennetegn i den korte bokmålssetningen til å avgjøre; nynorsken kjennes igjen.
    assert info["standard_in_first_rows"] == {"ukjent": 4, "nn": 1}
    assert main(["--inspect", "--manifest", str(manifest)]) == 0
    assert '"segments_after_exclusion": 4' in capsys.readouterr().out
    assert isinstance(FieldMap(), FieldMap)
