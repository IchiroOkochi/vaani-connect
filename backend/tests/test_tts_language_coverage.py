import unittest
from unittest.mock import patch

from app.languages import LANGUAGE_TO_CODE
from app.tts import GTTS_LANGUAGE_CODES, TTS_VOICE_LANGUAGE_MAP, resolve_tts_route, tts_generate


class _DummyTempFile:
    def __init__(self, name: str) -> None:
        self.name = name

    def close(self) -> None:
        return None


class TTSLanguageCoverageTests(unittest.TestCase):
    def test_every_supported_translation_language_has_a_tts_route(self) -> None:
        self.assertEqual(set(TTS_VOICE_LANGUAGE_MAP), set(LANGUAGE_TO_CODE))

        for language in LANGUAGE_TO_CODE:
            route = resolve_tts_route(language)
            self.assertEqual(route.requested_language, language)
            self.assertIn(route.voice_language, GTTS_LANGUAGE_CODES)
            self.assertIn(route.language_code, GTTS_LANGUAGE_CODES.values())

    def test_unsupported_languages_use_explicit_indic_fallbacks(self) -> None:
        self.assertEqual(resolve_tts_route("Bodo").voice_language, "Hindi")
        self.assertEqual(resolve_tts_route("Dogri").voice_language, "Hindi")
        self.assertEqual(resolve_tts_route("Kashmiri").voice_language, "Urdu")
        self.assertEqual(resolve_tts_route("Manipuri").voice_language, "Bengali")
        self.assertEqual(resolve_tts_route("Santali").voice_language, "Hindi")

    def test_tts_generate_uses_the_resolved_language_code(self) -> None:
        fake_tts = type("FakeTTS", (), {"save": lambda self, _path: None})()

        with (
            patch.dict("os.environ", {"VAANI_TTS_PROVIDER": "gtts"}, clear=False),
            patch("app.tts.tempfile.NamedTemporaryFile", return_value=_DummyTempFile("fake.mp3")),
            patch("app.tts.gTTS", return_value=fake_tts) as mock_gtts,
        ):
            output_path = tts_generate("translated text", "Kashmiri")

        self.assertEqual(output_path, "fake.mp3")
        mock_gtts.assert_called_once_with(text="translated text", lang="ur")


if __name__ == "__main__":
    unittest.main()
