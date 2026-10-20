import io
import json
import wave

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from nsb_engine.server import create_app  # noqa: E402
from nsb_engine.streaming import SAMPLE_RATE, Word  # noqa: E402

WORDS = ["Tiltalte", "nektet", "straffskyld", "paragraf", "to", "hundre", "og", "syttien", "punktum"]


class CountingBackend:
    """Ett ord per 0,4 s lyd; siste ord i tvil."""

    def __init__(self):
        self.hotwords = []

    def transcribe(self, audio, prompt=None, hotwords=None):
        self.hotwords.append(hotwords)
        n = min(len(WORDS), int(len(audio) / SAMPLE_RATE / 0.4))
        return [Word(WORDS[i], i * 0.4, i * 0.4 + 0.35, 0.3 if i == n - 1 else 0.95) for i in range(n)]


def pcm(seconds):
    return (np.zeros(int(seconds * SAMPLE_RATE)) + 0.01 * 32767).astype("<i2").tobytes()


BASE = "http://127.0.0.1:8765"


@pytest.fixture
def client_and_backend(tmp_path):
    backend = CountingBackend()
    app = create_app(backend, model_label="test", device="cpu", data_root=tmp_path, use_dpapi=False)
    client = TestClient(app, base_url=BASE, headers={"Authorization": f"Bearer {app.state.token.value}"})
    client.token = app.state.token.value
    client.app_ = app
    return client, backend


def test_health(client_and_backend):
    client, _ = client_and_backend
    r = client.get("/v1/health")
    assert r.status_code == 200 and r.json()["model"] == "test"


def test_index_page(client_and_backend):
    client, _ = client_and_backend
    r = client.get("/")
    assert r.status_code == 200 and "/v1/stream" in r.text


def test_stream_gives_updates_and_formatted_final_text(client_and_backend):
    client, backend = client_and_backend
    with client.websocket_connect(f"ws://127.0.0.1:8765/v1/stream?token={client.token}") as ws:
        ws.send_text(json.dumps({"type": "start", "hotwords": "Bjørdal", "format": "legal"}))
        updates = []
        for _ in range(16):
            ws.send_bytes(pcm(0.25))
        ws.send_text(json.dumps({"type": "end"}))
        while True:
            m = json.loads(ws.receive_text())
            updates.append(m)
            if m["type"] == "final":
                break
    final = updates[-1]
    assert final["text"] == "Tiltalte nektet straffskyld § 271."
    assert [w["text"] for w in final["words"]] == WORDS
    assert any(u["tentative"] for u in updates[:-1])
    assert all("preview" in u for u in updates)
    assert final["preview"] == final["text"]
    assert all(h == "Bjørdal" for h in backend.hotwords)


def test_uncertain_words_are_marked(client_and_backend):
    client, _ = client_and_backend
    with client.websocket_connect(f"ws://127.0.0.1:8765/v1/stream?token={client.token}") as ws:
        for _ in range(4):
            ws.send_bytes(pcm(0.25))
        ws.send_text(json.dumps({"type": "end"}))
        while True:
            m = json.loads(ws.receive_text())
            if m["type"] == "final":
                break
    assert m["words"][-1]["uncertain"] is True and m["words"][0]["uncertain"] is False


def _wav(seconds):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm(seconds))
    return buf.getvalue()


def test_transcribe_file(client_and_backend):
    pytest.importorskip("faster_whisper")
    client, _ = client_and_backend
    r = client.post("/v1/transcribe?hotwords=Giske", content=_wav(4.0))
    assert r.status_code == 200
    body = r.json()
    assert body["formatted"].startswith("Tiltalte nektet") and len(body["words"]) == len(WORDS)


def test_transcribe_rejects_empty_and_garbage(client_and_backend):
    pytest.importorskip("faster_whisper")
    client, _ = client_and_backend
    assert client.post("/v1/transcribe", content=b"").status_code == 400
    assert client.post("/v1/transcribe", content=b"ikke lyd").status_code == 415


def test_transcribe_long_recording_with_vad(tmp_path):
    pytest.importorskip("faster_whisper")
    backend = CountingBackend()
    app = create_app(backend, model_label="test", data_root=tmp_path, use_dpapi=False,
                     detector_factory=lambda: (lambda audio: [(1.0, 2.0), (6.0, 7.2)]))
    client = TestClient(app, base_url=BASE, headers={"Authorization": f"Bearer {app.state.token.value}"})
    r = client.post("/v1/transcribe?vad=true&format=none", content=_wav(10.0))
    assert r.status_code == 200
    body = r.json()
    assert body["speech_chunks"] == [[1.0, 2.0], [6.0, 7.2]]
    assert len(backend.hotwords) == 2  # stillheten mellom bitene ble aldri dekodet
    assert min(w["start"] for w in body["words"]) >= 0.8


def test_transcribe_vad_requires_detector(client_and_backend):
    pytest.importorskip("faster_whisper")
    client, _ = client_and_backend
    assert client.post("/v1/transcribe?vad=true", content=_wav(2.0)).status_code == 400
