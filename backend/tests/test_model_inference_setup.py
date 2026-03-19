import unittest
from threading import Lock
from unittest.mock import patch

from app.asr import ASRService
from app.translation import TranslationService


class _DummyModel:
    def __init__(self) -> None:
        self.to_device: str | None = None
        self.eval_calls = 0

    def to(self, device: str):
        self.to_device = device
        return self

    def eval(self):
        self.eval_calls += 1
        return self


class ModelInferenceSetupTests(unittest.TestCase):
    def test_translation_models_load_in_eval_mode(self) -> None:
        created_models: list[_DummyModel] = []

        def _make_model(*_args, **_kwargs):
            model = _DummyModel()
            created_models.append(model)
            return model

        with (
            patch("app.translation.IndicProcessor", return_value=object()),
            patch("app.translation.AutoTokenizer.from_pretrained", side_effect=[object(), object(), object()]),
            patch("app.translation.AutoModelForSeq2SeqLM.from_pretrained", side_effect=_make_model),
        ):
            service = TranslationService(device="cpu")

        self.assertIsNotNone(service.en_indic_model)
        self.assertEqual(len(created_models), 3)
        self.assertTrue(all(model.to_device == "cpu" for model in created_models))
        self.assertTrue(all(model.eval_calls == 1 for model in created_models))

    def test_indic_asr_model_loads_once_and_enters_eval_mode(self) -> None:
        created_models: list[_DummyModel] = []

        def _make_model(*_args, **_kwargs):
            model = _DummyModel()
            created_models.append(model)
            return model

        service = ASRService.__new__(ASRService)
        service.device = "cpu"
        service.hf_token = "test-token"
        service.indic_asr_models = {}
        service.indic_asr_processors = {}
        service._indic_asr_lock = Lock()

        with (
            patch("app.asr.AutoModelForCTC.from_pretrained", side_effect=_make_model) as mock_model_loader,
            patch("app.asr.AutoProcessor.from_pretrained", return_value=object()) as mock_processor_loader,
        ):
            first_model, first_processor = service._get_indic_asr("Hindi")
            second_model, second_processor = service._get_indic_asr("Hindi")

        self.assertIs(first_model, second_model)
        self.assertIs(first_processor, second_processor)
        self.assertEqual(len(created_models), 1)
        self.assertEqual(created_models[0].to_device, "cpu")
        self.assertEqual(created_models[0].eval_calls, 1)
        self.assertEqual(mock_model_loader.call_count, 1)
        self.assertEqual(mock_processor_loader.call_count, 1)


if __name__ == "__main__":
    unittest.main()
