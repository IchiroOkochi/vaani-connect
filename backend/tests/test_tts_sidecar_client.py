import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from app.tts import tts_generate_with_metadata


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str) -> None:
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class TTSSidecarClientTests(unittest.TestCase):
    def test_sidecar_provider_downloads_wav_audio(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {
                    "VAANI_TTS_PROVIDER": "parler_sidecar",
                    "VAANI_TTS_SIDECAR_URL": "http://sidecar.test:8010",
                },
                clear=False,
            ),
            patch(
                "app.tts.request.urlopen",
                return_value=_FakeResponse(b"fake-wav-audio", "audio/wav"),
            ) as mock_urlopen,
        ):
            generation = tts_generate_with_metadata("hello world", "Hindi")

        self.assertIsNotNone(generation)
        assert generation is not None
        self.assertEqual(generation.provider, "indic_parler_sidecar")
        self.assertEqual(generation.voice_language, "Hindi")
        self.assertEqual(generation.path[-4:], ".wav")
        called_request = mock_urlopen.call_args[0][0]
        self.assertEqual(called_request.full_url, "http://sidecar.test:8010/tts")
        Path(generation.path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
