"""Røyktest med ekte modell og ekte lyd.

Kjører bare når ``NSB_SMOKE_MODEL`` peker på en CTranslate2-modell. Lyden er
syntetisk norsk tale fra espeak-ng (CI installerer den), eller filen i
``NSB_SMOKE_AUDIO`` med fasit i ``NSB_SMOKE_TEXT``.
"""

import os
import shutil
import subprocess

import numpy as np
import pytest

MODEL = os.environ.get("NSB_SMOKE_MODEL")
pytestmark = pytest.mark.skipif(not MODEL, reason="NSB_SMOKE_MODEL er ikke satt")

TEXT = "Tiltalte nektet straffskyld. Retten mener at forklaringen er troverdig og at vilkårene er oppfylt."


@pytest.fixture(scope="module")
def speech(tmp_path_factory):
    from faster_whisper import decode_audio

    if os.environ.get("NSB_SMOKE_AUDIO"):
        return decode_audio(os.environ["NSB_SMOKE_AUDIO"], sampling_rate=16000), os.environ.get("NSB_SMOKE_TEXT", "")
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        pytest.skip("espeak-ng mangler")
    path = tmp_path_factory.mktemp("smoke") / "speech.wav"
    subprocess.run([exe, "-v", "nb", "-s", "140", "-w", str(path), TEXT], check=True)
    audio = decode_audio(str(path), sampling_rate=16000)
    pause = np.zeros(16000, dtype=np.float32)
    return np.concatenate([pause, audio, pause, audio, pause]), TEXT + " " + TEXT


@pytest.fixture(scope="module")
def backend():
    from nsb_engine.streaming import FasterWhisperBackend

    return FasterWhisperBackend(MODEL, device="cpu", compute_type="int8", language="no", beam_size=1)


def test_streaming_matches_batch_on_real_model(speech, backend):
    from nsb_engine.streaming import StreamingRecognizer, join_words, silero_detector
    from nsb_eval.metrics import word_counts
    from nsb_eval.normalize import normalize
    from nsb_eval.streaming_eval import simulate

    audio, reference = speech
    rec = StreamingRecognizer(backend, detector=silero_detector(), min_step=1.0)
    res = simulate(rec, audio, chunk=0.5)
    text = join_words(res["words"])
    batch = join_words(backend.transcribe(audio))
    assert text.strip(), "strømmingen ga ingen tekst"
    if reference:
        s = word_counts(normalize(reference), normalize(text))
        b = word_counts(normalize(reference), normalize(batch))
        print(f"WER strøm {s.errors / s.reference_length:.1%}, hel {b.errors / b.reference_length:.1%}")
        assert s.errors / s.reference_length <= b.errors / b.reference_length + 0.15
    assert all(0 <= w.probability <= 1 for w in res["words"])
    starts = [w.start for w in res["words"]]
    assert starts == sorted(starts), "ord skal komme i rekkefølge"
    assert res["commit_latency"] and max(res["commit_latency"]) < 30


def test_server_transcribes_real_audio(speech, backend):
    import io
    import wave

    from fastapi.testclient import TestClient

    from nsb_engine.server import create_app

    audio, _ = speech
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    client = TestClient(create_app(backend, model_label="smoke"))
    r = client.post("/v1/transcribe", content=buf.getvalue())
    assert r.status_code == 200 and r.json()["words"]
