import unittest
from unittest.mock import patch

import torch

from app.asr import ASRService, DEFAULT_ASR_PROVIDER


class _DummyInputs(dict):
    def to(self, _device: str):
        return self


class _DummyProcessor:
    def __init__(self) -> None:
        self.prompt_calls: list[tuple[str, str]] = []

    def __call__(self, _audio_np, sampling_rate: int, return_tensors: str):
        _ = sampling_rate
        _ = return_tensors
        return _DummyInputs({"input_features": "features"})

    def get_decoder_prompt_ids(self, language: str, task: str):
        self.prompt_calls.append((language, task))
        return [1, 2, 3]

    def batch_decode(self, _generated_ids, skip_special_tokens: bool = True):
        _ = skip_special_tokens
        return ["decoded transcription"]


class _DummyModel:
    def __init__(self) -> None:
        self.generate_calls: list[dict] = []

    def generate(self, input_features, **kwargs):
        self.generate_calls.append({"input_features": input_features, **kwargs})
        return [[1, 2, 3, 4]]


class ASRLanguageFallbackTests(unittest.TestCase):
    def _build_service(self) -> ASRService:
        service = ASRService.__new__(ASRService)
        service.device = "cpu"
        service.asr_model_id_en = "openai/whisper-large-v3-turbo"
        service.asr_processor_en = _DummyProcessor()
        service.asr_model_en = _DummyModel()
        service.hf_token = "test-token"
        service.indic_asr_models = {}
        service.indic_asr_processors = {}
        service.asr_provider = DEFAULT_ASR_PROVIDER
        service.indic_conformer_model_id = "ai4bharat/indic-conformer-600m-multilingual"
        service.indic_conformer_decoder = "ctc"
        service.indic_conformer_model = None
        service._indic_conformer_model_load_error = None
        service._indic_conformer_lock = None
        return service

    def test_whisper_transcribe_uses_forced_language_when_mapping_exists(self) -> None:
        service = self._build_service()
        with patch.object(
            service,
            "_load_and_resample_audio",
            return_value=(torch.zeros(16000), 16000),
        ):
            text = service._whisper_transcribe("dummy.wav", "Hindi")

        self.assertEqual(text, "decoded transcription")
        model_call = service.asr_model_en.generate_calls[0]
        self.assertEqual(model_call["forced_decoder_ids"], [1, 2, 3])
        self.assertEqual(service.asr_processor_en.prompt_calls[0], ("hi", "transcribe"))

    def test_whisper_transcribe_auto_detects_when_mapping_missing(self) -> None:
        service = self._build_service()
        with patch.object(
            service,
            "_load_and_resample_audio",
            return_value=(torch.zeros(16000), 16000),
        ):
            text = service._whisper_transcribe("dummy.wav", "Bodo")

        self.assertEqual(text, "decoded transcription")
        model_call = service.asr_model_en.generate_calls[0]
        self.assertNotIn("forced_decoder_ids", model_call)
        self.assertEqual(service.asr_processor_en.prompt_calls, [])

    def test_transcribe_with_stats_marks_autodetect_for_long_tail_language(self) -> None:
        service = self._build_service()
        with patch.object(service, "_whisper_transcribe", return_value="hello from bodo") as mock_whisper:
            text, stats = service.transcribe_with_stats("dummy.wav", "Bodo")

        self.assertEqual(text, "hello from bodo")
        self.assertEqual(stats["route"], "whisper_fallback_autodetect")
        self.assertFalse(stats["language_hint_applied"])
        mock_whisper.assert_called_once_with("dummy.wav", "Bodo")

    def test_transcribe_with_stats_marks_hinted_for_supported_whisper_language(self) -> None:
        service = self._build_service()
        with patch.object(service, "_whisper_transcribe", return_value="hello from urdu") as mock_whisper:
            text, stats = service.transcribe_with_stats("dummy.wav", "Urdu")

        self.assertEqual(text, "hello from urdu")
        self.assertEqual(stats["route"], "whisper_fallback_hinted")
        self.assertTrue(stats["language_hint_applied"])
        mock_whisper.assert_called_once_with("dummy.wav", "Urdu")

    def test_indic_conformer_provider_runs_first_then_rolls_back(self) -> None:
        service = self._build_service()
        service.asr_provider = "indic_conformer_multi"

        with (
            patch.object(service, "_indic_conformer_transcribe", side_effect=RuntimeError("boom")) as mock_conformer,
            patch.object(
                service,
                "_legacy_non_english_transcribe_with_stats",
                return_value=(
                    "fallback text",
                    {
                        "route": "whisper_fallback_hinted",
                        "model_id": "openai/whisper-large-v3-turbo",
                        "language": "Urdu",
                        "provider": DEFAULT_ASR_PROVIDER,
                        "latency_ms": 12.34,
                        "output_chars": 13,
                    },
                ),
            ) as mock_legacy,
        ):
            text, stats = service.transcribe_with_stats("dummy.wav", "Urdu")

        self.assertEqual(text, "fallback text")
        self.assertEqual(stats["provider"], "indic_conformer_multi")
        self.assertTrue(stats["route"].startswith("indic_conformer_multi_rollback_to_"))
        mock_conformer.assert_called_once_with("dummy.wav", "Urdu")
        self.assertEqual(mock_legacy.call_count, 1)


if __name__ == "__main__":
    unittest.main()
