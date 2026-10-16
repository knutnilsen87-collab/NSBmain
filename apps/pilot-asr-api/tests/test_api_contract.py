import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


APP_ROOT = Path(__file__).resolve().parents[1]
SMOKE_WAV = APP_ROOT / "smoke_test.wav"


class PilotAsrApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ASR_BACKEND"] = "mock"
        os.environ["ASR_MODEL_NAME"] = "mock-small"
        os.environ["ASR_MODEL_DEVICE"] = "cpu"
        os.environ["ASR_MODEL_COMPUTE_TYPE"] = "int8"
        os.environ["ASR_TEMP_DIR"] = str(APP_ROOT / ".tmp-test")
        os.environ["ASR_MAX_UPLOAD_MB"] = "1"

        from app.main import app

        cls.client = TestClient(app)

    def test_health_contract(self):
        response = self.client.get("/v1/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["backend"], "mock")
        self.assertIn("model_name", body)
        self.assertIn("model_loaded", body)

    def test_readiness_contract(self):
        response = self.client.get("/v1/readiness")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("ready", body)
        self.assertIn(body["status"], {"ready", "not_ready"})

    def test_path_contract(self):
        response = self.client.post(
            "/v1/transcriptions/path",
            json={"audio_path": str(SMOKE_WAV), "language": "no"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["backend"], "mock")
        self.assertEqual(body["audio_source"], str(SMOKE_WAV))
        self.assertIn("transcript", body)
        self.assertIn("segments", body)

    def test_upload_contract(self):
        with SMOKE_WAV.open("rb") as fh:
            response = self.client.post(
                "/v1/transcriptions/upload",
                files={"file": ("smoke_test.wav", fh, "audio/wav")},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["backend"], "mock")
        self.assertEqual(body["audio_source"], "upload:smoke_test.wav")
        self.assertIn("transcript", body)
        self.assertIn("segments", body)

    def test_path_missing_file_returns_structured_error(self):
        response = self.client.post(
            "/v1/transcriptions/path",
            json={"audio_path": str(APP_ROOT / "missing.wav")},
        )
        self.assertEqual(response.status_code, 404)
        body = response.json()["detail"]
        self.assertEqual(body["error"], "audio_not_found")
        self.assertIn("request_id", body)

    def test_upload_rejects_empty_file(self):
        response = self.client.post(
            "/v1/transcriptions/upload",
            files={"file": ("empty.wav", b"", "audio/wav")},
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()["detail"]
        self.assertEqual(body["error"], "empty_upload")

    def test_upload_rejects_unsupported_extension(self):
        response = self.client.post(
            "/v1/transcriptions/upload",
            files={"file": ("bad.txt", b"not-audio", "text/plain")},
        )
        self.assertEqual(response.status_code, 415)
        body = response.json()["detail"]
        self.assertEqual(body["error"], "unsupported_media_type")

    def test_upload_rejects_oversized_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            large_file = Path(tmp_dir) / "large.wav"
            large_file.write_bytes(b"a" * (2 * 1024 * 1024))
            with large_file.open("rb") as fh:
                response = self.client.post(
                    "/v1/transcriptions/upload",
                    files={"file": ("large.wav", fh, "audio/wav")},
                )
        self.assertEqual(response.status_code, 413)
        body = response.json()["detail"]
        self.assertEqual(body["error"], "file_too_large")


if __name__ == "__main__":
    unittest.main()
