from __future__ import annotations  # Delay evaluation of type hints until runtime.

from dataclasses import dataclass  # Decorator that auto-creates init/representation methods.
import logging
import time
from typing import Any

import torch  # PyTorch for tensor operations and model inference.
from IndicTransToolkit.processor import IndicProcessor  # Text pre/post-processor for IndicTrans models.
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # Hugging Face model/tokenizer loaders.

ENGLISH_CODE = "eng_Latn"  # Language code used in this project for English.
EN_INDIC_MODEL_ID = "ai4bharat/indictrans2-en-indic-dist-200M"
INDIC_EN_MODEL_ID = "ai4bharat/indictrans2-indic-en-dist-200M"
INDIC_INDIC_MODEL_ID = "ai4bharat/indictrans2-indic-indic-dist-320M"

logger = logging.getLogger(__name__)


@dataclass
class TranslationService:
    """IndicTrans2 translation wrapper for backend usage."""

    # Choose GPU if available, otherwise use CPU.
    device: str = "cuda" if torch.cuda.is_available() else "cpu"

    # Runs automatically after dataclass __init__ finishes.
    def __post_init__(self) -> None:
        # Create processor that normalizes text for model input and output.
        self.ip = IndicProcessor(inference=True)

        # Tokenizer for English -> Indic model.
        self.en_indic_tokenizer = AutoTokenizer.from_pretrained(
            EN_INDIC_MODEL_ID,
            trust_remote_code=True,
        )
        # Model for English -> Indic translation, moved to selected device.
        self.en_indic_model = AutoModelForSeq2SeqLM.from_pretrained(
            EN_INDIC_MODEL_ID,
            trust_remote_code=True,
        ).to(self.device)
        self.en_indic_model.eval()

        # Tokenizer for Indic -> English model.
        self.indic_en_tokenizer = AutoTokenizer.from_pretrained(
            INDIC_EN_MODEL_ID,
            trust_remote_code=True,
        )
        # Model for Indic -> English translation, moved to selected device.
        self.indic_en_model = AutoModelForSeq2SeqLM.from_pretrained(
            INDIC_EN_MODEL_ID,
            trust_remote_code=True,
        ).to(self.device)
        self.indic_en_model.eval()

        # Tokenizer for direct Indic -> Indic model.
        self.indic_indic_tokenizer = AutoTokenizer.from_pretrained(
            INDIC_INDIC_MODEL_ID,
            trust_remote_code=True,
        )
        # Model for direct Indic -> Indic translation, moved to selected device.
        self.indic_indic_model = AutoModelForSeq2SeqLM.from_pretrained(
            INDIC_INDIC_MODEL_ID,
            trust_remote_code=True,
        ).to(self.device)
        self.indic_indic_model.eval()

    # Internal helper that runs one translation pass with a selected model/tokenizer.
    def _run_translation_with_stats(
        self,
        texts: list[str],  # One or more input texts to translate.
        src_lang: str,  # Source language code (for example, hin_Deva).
        tgt_lang: str,  # Target language code (for example, eng_Latn).
        model,  # Chosen seq2seq model.
        tokenizer,  # Matching tokenizer for the chosen model.
        model_id: str,
        stage_name: str,
    ) -> tuple[list[str], dict[str, Any]]:
        stage_start = time.perf_counter()

        # Normalize inputs for model expectations (script/format handling).
        preprocess_start = time.perf_counter()
        batch = self.ip.preprocess_batch(texts, src_lang=src_lang, tgt_lang=tgt_lang)
        preprocess_ms = (time.perf_counter() - preprocess_start) * 1000

        # Convert text to token tensors; pad/truncate to build a proper batch.
        tokenize_start = time.perf_counter()
        inputs = tokenizer(
            batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
        ).to(self.device)
        tokenize_ms = (time.perf_counter() - tokenize_start) * 1000

        input_tokens = None
        if "input_ids" in inputs:
            input_tokens = int(inputs["input_ids"].shape[-1])

        # Disable gradients because this is inference, not training.
        generate_start = time.perf_counter()
        with torch.no_grad():
            # Generate translated token ids.
            generated = model.generate(
                **inputs,
                num_beams=5,  # Beam search width for better quality.
                num_return_sequences=1,  # Return only best hypothesis.
                max_length=256,  # Safety cap on output length.
            )
        generate_ms = (time.perf_counter() - generate_start) * 1000

        output_tokens = int(generated.shape[-1]) if hasattr(generated, "shape") else None

        # Convert token ids to strings.
        decode_start = time.perf_counter()
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        # Post-process text (cleanup/normalization) for target language.
        outputs = self.ip.postprocess_batch(decoded, lang=tgt_lang)
        decode_ms = (time.perf_counter() - decode_start) * 1000

        stage_total_ms = (time.perf_counter() - stage_start) * 1000
        stats = {
            "stage": stage_name,
            "model_id": model_id,
            "src_lang": src_lang,
            "tgt_lang": tgt_lang,
            "device": self.device,
            "batch_size": len(texts),
            "input_chars": sum(len(item) for item in texts),
            "output_chars": sum(len(item) for item in outputs),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "preprocess_ms": round(preprocess_ms, 2),
            "tokenize_ms": round(tokenize_ms, 2),
            "generate_ms": round(generate_ms, 2),
            "decode_ms": round(decode_ms, 2),
            "latency_ms": round(stage_total_ms, 2),
        }
        return outputs, stats

    def _run_translation(
        self,
        texts: list[str],
        src_lang: str,
        tgt_lang: str,
        model,
        tokenizer,
    ) -> list[str]:
        outputs, _ = self._run_translation_with_stats(
            texts=texts,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            model=model,
            tokenizer=tokenizer,
            model_id="unknown",
            stage_name="legacy",
        )
        return outputs

    # Public method used by the API: translate one text string.
    def translate_text_with_stats(
        self,
        text: str,
        src_lang: str,
        tgt_lang: str,
    ) -> tuple[str, dict[str, Any]]:
        request_start = time.perf_counter()
        steps: list[dict[str, Any]] = []
        route = ""
        fallback_reason: str | None = None

        # If source is English, do direct English -> Indic translation.
        if src_lang == ENGLISH_CODE:
            route = "en_to_indic_direct"
            outputs, step_stats = self._run_translation_with_stats(
                [text],
                src_lang,
                tgt_lang,
                self.en_indic_model,
                self.en_indic_tokenizer,
                model_id=EN_INDIC_MODEL_ID,
                stage_name="en_to_indic",
            )
            steps.append(step_stats)
            translated = outputs[0]
            return translated, {
                "route": route,
                "used_fallback": False,
                "device": self.device,
                "model_ids": [EN_INDIC_MODEL_ID],
                "steps": steps,
                "input_chars": len(text),
                "output_chars": len(translated),
                "total_latency_ms": round((time.perf_counter() - request_start) * 1000, 2),
            }

        # If target is English, do direct Indic -> English translation.
        if tgt_lang == ENGLISH_CODE:
            route = "indic_to_en_direct"
            outputs, step_stats = self._run_translation_with_stats(
                [text],
                src_lang,
                tgt_lang,
                self.indic_en_model,
                self.indic_en_tokenizer,
                model_id=INDIC_EN_MODEL_ID,
                stage_name="indic_to_en",
            )
            steps.append(step_stats)
            translated = outputs[0]
            return translated, {
                "route": route,
                "used_fallback": False,
                "device": self.device,
                "model_ids": [INDIC_EN_MODEL_ID],
                "steps": steps,
                "input_chars": len(text),
                "output_chars": len(translated),
                "total_latency_ms": round((time.perf_counter() - request_start) * 1000, 2),
            }

        # For Indic -> Indic, prefer the direct model (better latency than two-step pivoting).
        try:
            route = "indic_to_indic_direct"
            outputs, step_stats = self._run_translation_with_stats(
                [text],
                src_lang,
                tgt_lang,
                self.indic_indic_model,
                self.indic_indic_tokenizer,
                model_id=INDIC_INDIC_MODEL_ID,
                stage_name="indic_to_indic",
            )
            steps.append(step_stats)
            translated = outputs[0]
            return translated, {
                "route": route,
                "used_fallback": False,
                "device": self.device,
                "model_ids": [INDIC_INDIC_MODEL_ID],
                "steps": steps,
                "input_chars": len(text),
                "output_chars": len(translated),
                "total_latency_ms": round((time.perf_counter() - request_start) * 1000, 2),
            }
        except Exception:  # noqa: BLE001 - fallback keeps API robust for edge language-code/model issues.
            fallback_reason = "direct_indic_to_indic_failed"
            logger.exception(
                "Direct Indic->Indic translation failed for %s -> %s; using English pivot fallback.",
                src_lang,
                tgt_lang,
            )

        # Fallback path: Indic -> English -> Indic.
        route = "indic_to_indic_via_english_fallback"
        english_intermediate, step_1_stats = self._run_translation_with_stats(
            [text],
            src_lang,
            ENGLISH_CODE,
            self.indic_en_model,
            self.indic_en_tokenizer,
            model_id=INDIC_EN_MODEL_ID,
            stage_name="indic_to_en_pivot",
        )
        steps.append(step_1_stats)
        translated_outputs, step_2_stats = self._run_translation_with_stats(
            english_intermediate,
            ENGLISH_CODE,
            tgt_lang,
            self.en_indic_model,
            self.en_indic_tokenizer,
            model_id=EN_INDIC_MODEL_ID,
            stage_name="en_to_indic_pivot",
        )
        steps.append(step_2_stats)
        translated = translated_outputs[0]
        return translated, {
            "route": route,
            "used_fallback": True,
            "fallback_reason": fallback_reason,
            "device": self.device,
            "model_ids": [INDIC_EN_MODEL_ID, EN_INDIC_MODEL_ID],
            "steps": steps,
            "input_chars": len(text),
            "output_chars": len(translated),
            "total_latency_ms": round((time.perf_counter() - request_start) * 1000, 2),
        }

    def translate_text(self, text: str, src_lang: str, tgt_lang: str) -> str:
        translated, _ = self.translate_text_with_stats(text=text, src_lang=src_lang, tgt_lang=tgt_lang)
        return translated

    # Optional startup warmup to reduce first-request latency.
    def warmup(self) -> None:
        warmup_pairs = [
            ("hello", ENGLISH_CODE, "hin_Deva"),
            ("namaste", "hin_Deva", ENGLISH_CODE),
            ("namaste", "hin_Deva", "tam_Taml"),
        ]

        for text, src_lang, tgt_lang in warmup_pairs:
            try:
                self.translate_text(text, src_lang, tgt_lang)
            except Exception:  # noqa: BLE001 - warmup should not crash service boot.
                logger.exception("Translation warmup failed for %s -> %s", src_lang, tgt_lang)
