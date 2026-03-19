import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import server


class _DummyTranslationService:
    def translate_text(self, text: str, src: str, tgt: str) -> str:
        return f"{text}::{src}->{tgt}"


class _DummyASRService:
    def transcribe(self, _audio_path: str, _source_language: str) -> str:
        return "hello from asr"


class ServerHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._audio_tmpdir = tempfile.TemporaryDirectory()
        self.audio_dir = Path(self._audio_tmpdir.name)
        self.generated_tts_paths: list[str] = []

        def _fake_tts_generate(_text: str, _target: str):
            temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_audio.write(b"fake-mp3-bytes")
            temp_audio.close()
            self.generated_tts_paths.append(temp_audio.name)
            return SimpleNamespace(
                path=temp_audio.name,
                provider="gTTS",
                requested_language=_target,
                voice_language=_target,
                language_code="hi",
                uses_fallback_voice=False,
            )

        self._patchers = [
            patch.object(server, "audio_dir", self.audio_dir),
            patch.object(server, "audio_dir_resolved", self.audio_dir.resolve()),
            patch.object(
                server,
                "get_services",
                return_value=(_DummyTranslationService(), _DummyASRService()),
            ),
            patch.object(server, "tts_generate_with_metadata", side_effect=_fake_tts_generate),
            patch.object(server, "API_KEY", None),
            patch.object(server, "RATE_LIMIT_MAX_REQUESTS", 1000),
            patch.object(server, "RATE_LIMIT_WINDOW_SECONDS", 60),
            patch.object(server, "MAX_UPLOAD_BYTES", 32),
            patch.object(server, "AUDIO_TTL_SECONDS", 3600),
        ]

        for patcher in self._patchers:
            patcher.start()

        server._client_request_times.clear()
        self.client = TestClient(server.app)

    def tearDown(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._audio_tmpdir.cleanup()

    def test_safe_audio_path_rejects_traversal(self) -> None:
        with self.assertRaises(HTTPException):
            server._safe_audio_path("../secret.mp3")
        with self.assertRaises(HTTPException):
            server._safe_audio_path("..\\secret.mp3")

    def test_safe_audio_path_accepts_wav(self) -> None:
        path = self.audio_dir / "clip.wav"
        path.write_bytes(b"fake-wav")
        self.assertEqual(server._safe_audio_path("clip.wav"), path.resolve())

    def test_get_audio_serves_wav(self) -> None:
        path = self.audio_dir / "clip.wav"
        path.write_bytes(b"fake-wav")

        response = self.client.get("/audio/clip.wav")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")

    def test_translate_speech_rejects_large_upload(self) -> None:
        response = self.client.post(
            "/translate/speech",
            data={"source_language": "English", "target_language": "Hindi"},
            files={"audio": ("clip.wav", b"x" * 40, "audio/wav")},
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("max size", response.json()["detail"])

    def test_translate_text_requires_api_key_when_enabled(self) -> None:
        payload = {
            "text": "hello",
            "source_language": "English",
            "target_language": "Hindi",
            "include_speech": False,
        }

        with patch.object(server, "API_KEY", "test-api-key"):
            unauthorized = self.client.post("/translate/text", json=payload)
            authorized = self.client.post(
                "/translate/text",
                json=payload,
                headers={"X-API-Key": "test-api-key"},
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)

    def test_translate_text_deletes_intermediate_tts_file(self) -> None:
        response = self.client.post(
            "/translate/text",
            json={
                "text": "hello",
                "source_language": "English",
                "target_language": "Hindi",
                "include_speech": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        for generated_path in self.generated_tts_paths:
            self.assertFalse(os.path.exists(generated_path))

        audio_url = response.json()["audio_url"]
        self.assertIsNotNone(audio_url)
        filename = audio_url.split("/")[-1]
        self.assertTrue((self.audio_dir / filename).exists())

    def test_translate_text_survives_tts_failure(self) -> None:
        payload = {
            "text": "hello",
            "source_language": "English",
            "target_language": "Hindi",
            "include_speech": True,
        }

        with patch.object(server, "tts_generate_with_metadata", side_effect=RuntimeError("tts offline")):
            response = self.client.post("/translate/text", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["audio_url"])

    def test_translate_speech_survives_tts_failure(self) -> None:
        with patch.object(server, "tts_generate_with_metadata", side_effect=RuntimeError("tts offline")):
            response = self.client.post(
                "/translate/speech",
                data={"source_language": "English", "target_language": "Hindi"},
                files={"audio": ("clip.wav", b"small-audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transcribed_text"], "hello from asr")
        self.assertIsNone(response.json()["audio_url"])

    def test_rate_limit_returns_429(self) -> None:
        payload = {
            "text": "hello",
            "source_language": "English",
            "target_language": "Hindi",
            "include_speech": False,
        }

        with patch.object(server, "RATE_LIMIT_MAX_REQUESTS", 1):
            server._client_request_times.clear()
            first = self.client.post("/translate/text", json=payload)
            second = self.client.post("/translate/text", json=payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)


if __name__ == "__main__":
    unittest.main()
