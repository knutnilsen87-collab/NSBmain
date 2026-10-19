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

LANG = os.environ.get("NSB_SMOKE_LANG", "no")
# Syntetisk tale er vanskelig for små modeller. CI bruker engelsk med Whisper
# tiny for å teste mekanikken; norsk testes med NB-Whisper og ekte opptak.
TEXTS = {
    "no": "Tiltalte nektet straffskyld. Retten mener at forklaringen er troverdig og at vilkårene er oppfylt.",
    "en": "The defendant pleaded not guilty. The court finds the explanation credible and the conditions are met.",
}
TEXT = TEXTS[LANG]


@pytest.fixture(scope="module")
def speech(tmp_path_factory):
    from faster_whisper import decode_audio

    if os.environ.get("NSB_SMOKE_AUDIO"):
        return decode_audio(os.environ["NSB_SMOKE_AUDIO"], sampling_rate=16000), os.environ.get("NSB_SMOKE_TEXT", "")
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        pytest.skip("espeak-ng mangler")
    path = tmp_path_factory.mktemp("smoke") / "speech.wav"
    subprocess.run([exe, "-v", "nb" if LANG == "no" else "en-us", "-s", "140", "-w", str(path), TEXT], check=True)
    audio = decode_audio(str(path), sampling_rate=16000)
    pause = np.zeros(16000, dtype=np.float32)
    return np.concatenate([pause, audio, pause, audio, pause]), TEXT + " " + TEXT


@pytest.fixture(scope="module")
def backend():
    from nsb_engine.streaming import FasterWhisperBackend

    return FasterWhisperBackend(MODEL, device="cpu", compute_type="int8", language=LANG, beam_size=1)


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
        print(f"STRØM: {text}")
        print(f"HEL: {batch}")
        # Små modeller på syntetisk tale vakler mellom like ord («condition»/«conditions»)
        # fra kjøring til kjøring; 32 ord gir 3 pp per ord. Tillat 5 % eller tre ord.
        assert s.errors <= b.errors + max(3, 0.05 * s.reference_length)
    assert all(0 <= w.probability <= 1 for w in res["words"])
    starts = [w.start for w in res["words"]]
    # Tidene fra ny dekoding kan avvike litt; ordene skal likevel komme i rekkefølge.
    assert all(a <= b + 0.2 for a, b in zip(starts, starts[1:], strict=False)), "ord skal komme i rekkefølge"
    assert res["commit_latency"] and max(res["commit_latency"]) < 30


def test_server_transcribes_real_audio(speech, backend, tmp_path):
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
    app = create_app(backend, model_label="smoke", data_root=tmp_path, use_dpapi=False)
    client = TestClient(app, base_url="http://127.0.0.1:8765",
                        headers={"Authorization": f"Bearer {app.state.token.value}"})
    r = client.post("/v1/transcribe", content=buf.getvalue())
    assert r.status_code == 200 and r.json()["words"]
