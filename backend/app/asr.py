from __future__ import annotations  # Keep type hints as strings until runtime (avoids some import/type issues).

import logging
import os
import time
from threading import Lock
from typing import Any

import torch  # PyTorch: tensor math + deep learning runtime.
import torchaudio  # Audio loading helpers from PyTorch ecosystem.
import torchaudio.functional as AF  # Audio utility functions (we use resample below).
from transformers import AutoModel, AutoModelForCTC, AutoModelForSpeechSeq2Seq, AutoProcessor  # Hugging Face model/processor loaders.

logger = logging.getLogger(__name__)

# Map language names used by your app to Whisper language codes.
WHISPER_LANG_MAP = {
    "English": "en",  # English -> "en"
    "Assamese": "as",  # Assamese -> "as"
    "Hindi": "hi",  # Hindi -> "hi"
    "Telugu": "te",  # Telugu -> "te"
    "Tamil": "ta",  # Tamil -> "ta"
    "Kannada": "kn",  # Kannada -> "kn"
    "Malayalam": "ml",  # Malayalam -> "ml"
    "Bengali": "bn",  # Bengali -> "bn"
    "Gujarati": "gu",  # Gujarati -> "gu"
    "Marathi": "mr",  # Marathi -> "mr"
    "Nepali": "ne",  # Nepali -> "ne"
    "Odia": "or",  # Odia -> "or"
    "Punjabi": "pa",  # Punjabi -> "pa"
    "Sanskrit": "sa",  # Sanskrit -> "sa"
    "Sindhi": "sd",  # Sindhi -> "sd"
    "Urdu": "ur",  # Urdu -> "ur"
}

# For some Indian languages, use language-specific IndicWav2Vec models.
INDIC_ASR_MODEL_IDS = {
    "Hindi": "ai4bharat/indicwav2vec-hindi",  # Hugging Face repo id for Hindi ASR.
    "Telugu": "ai4bharat/indicwav2vec_v1_telugu",  # Hugging Face repo id for Telugu ASR.
    "Tamil": "ai4bharat/indicwav2vec_v1_tamil",  # Hugging Face repo id for Tamil ASR.
    "Bengali": "ai4bharat/indicwav2vec_v1_bengali",  # Hugging Face repo id for Bengali ASR.
    "Marathi": "ai4bharat/indicwav2vec_v1_marathi",  # Hugging Face repo id for Marathi ASR.
}

DEFAULT_ASR_PROVIDER = "legacy"
SUPPORTED_ASR_PROVIDERS = {DEFAULT_ASR_PROVIDER, "indic_conformer_multi"}
DEFAULT_INDIC_CONFORMER_MODEL_ID = "ai4bharat/indic-conformer-600m-multilingual"
SUPPORTED_INDIC_CONFORMER_DECODERS = {"ctc", "rnnt"}

# Language codes expected by IndicConformer multilingual model.
INDIC_CONFORMER_LANG_CODES = {
    "Assamese": "as",
    "Bengali": "bn",
    "Bodo": "brx",
    "Dogri": "doi",
    "Gujarati": "gu",
    "Hindi": "hi",
    "Kannada": "kn",
    "Kashmiri": "ks",
    "Konkani": "kok",
    "Maithili": "mai",
    "Malayalam": "ml",
    "Manipuri": "mni",
    "Marathi": "mr",
    "Nepali": "ne",
    "Odia": "or",
    "Punjabi": "pa",
    "Sanskrit": "sa",
    "Santali": "sat",
    "Sindhi": "sd",
    "Tamil": "ta",
    "Telugu": "te",
    "Urdu": "ur",
}


class ASRService:
    # Service object that loads ASR models and provides one `transcribe(...)` method.
    def __init__(self, hf_token: str):
        # Use GPU when available; otherwise use CPU.
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # Save Hugging Face token (needed by some model repos).
        self.hf_token = hf_token

        # Whisper model id used for English and fallback languages.
        self.asr_model_id_en = "openai/whisper-large-v3-turbo"
        # Download/load Whisper model and move it to chosen device.
        self.asr_model_en = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.asr_model_id_en
        ).to(self.device)
        self.asr_model_en.eval()
        # Load matching processor (handles audio preprocessing + decoding).
        self.asr_processor_en = AutoProcessor.from_pretrained(self.asr_model_id_en)

        # Cache dict for loaded Indic models (lazy loaded on first use per language).
        self.indic_asr_models = {}
        # Cache dict for loaded Indic processors (one per language model).
        self.indic_asr_processors = {}
        # Protect lazy model cache initialization from concurrent first-use requests.
        self._indic_asr_lock = Lock()
        # Optional provider override: indic_conformer_multi (fallbacks to legacy stack on failure).
        requested_provider = os.getenv("ASR_PROVIDER", DEFAULT_ASR_PROVIDER).strip().lower()
        if requested_provider not in SUPPORTED_ASR_PROVIDERS:
            logger.warning(
                "Unsupported ASR_PROVIDER=%s. Falling back to %s.",
                requested_provider,
                DEFAULT_ASR_PROVIDER,
            )
            requested_provider = DEFAULT_ASR_PROVIDER
        self.asr_provider = requested_provider

        self.indic_conformer_model_id = (
            os.getenv("ASR_INDIC_CONFORMER_MODEL_ID", DEFAULT_INDIC_CONFORMER_MODEL_ID).strip()
            or DEFAULT_INDIC_CONFORMER_MODEL_ID
        )
        requested_decoder = os.getenv("ASR_INDIC_CONFORMER_DECODER", "ctc").strip().lower()
        if requested_decoder not in SUPPORTED_INDIC_CONFORMER_DECODERS:
            logger.warning(
                "Unsupported ASR_INDIC_CONFORMER_DECODER=%s. Falling back to ctc.",
                requested_decoder,
            )
            requested_decoder = "ctc"
        self.indic_conformer_decoder = requested_decoder
        self.indic_conformer_model = None
        self._indic_conformer_model_load_error: Exception | None = None
        self._indic_conformer_lock = Lock()

    def _get_indic_conformer_model(self):
        if self._indic_conformer_model_load_error is not None:
            raise self._indic_conformer_model_load_error
        if self.indic_conformer_model is not None:
            return self.indic_conformer_model

        with self._indic_conformer_lock:
            if self.indic_conformer_model is not None:
                return self.indic_conformer_model
            if self._indic_conformer_model_load_error is not None:
                raise self._indic_conformer_model_load_error

            try:
                model = AutoModel.from_pretrained(
                    self.indic_conformer_model_id,
                    trust_remote_code=True,
                    token=self.hf_token,
                )
                if hasattr(model, "eval"):
                    model.eval()
                self.indic_conformer_model = model
                logger.info(
                    "Loaded IndicConformer model %s (decoder=%s).",
                    self.indic_conformer_model_id,
                    self.indic_conformer_decoder,
                )
            except Exception as exc:  # noqa: BLE001 - cached load errors avoid repeated heavy failures.
                self._indic_conformer_model_load_error = exc
                raise
        return self.indic_conformer_model

    # Helper: load audio file, convert to mono, and resample to target sample rate (default 16kHz).
    def _load_and_resample_audio(self, audio_path: str, target_sr: int = 16000):
        # Load audio file -> waveform tensor and original sample rate.
        waveform, sr = torchaudio.load(audio_path)

        # If audio has multiple channels (for example stereo), average to single mono channel.
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # If sample rate is not what model expects, resample it.
        if sr != target_sr:
            waveform = AF.resample(waveform, sr, target_sr)
            sr = target_sr

        # Remove the channel dimension and return (1D waveform, sample rate).
        return waveform.squeeze(0), sr

    # Internal path: transcribe using Whisper.
    def _whisper_transcribe(self, audio_path: str, src_lang_name: str) -> str:
        # Convert app language name (like "Hindi") to Whisper code (like "hi").
        lang_code = WHISPER_LANG_MAP.get(src_lang_name)

        # Load and normalize audio to 16kHz mono.
        waveform, sr = self._load_and_resample_audio(audio_path, target_sr=16000)
        # Convert tensor to NumPy because processor accepts array-like audio input.
        audio_np = waveform.cpu().numpy()

        # Create model input features as PyTorch tensors, then move them to GPU/CPU device.
        inputs = self.asr_processor_en(
            audio_np, sampling_rate=sr, return_tensors="pt"
        ).to(self.device)

        generation_kwargs = {"max_new_tokens": 200}
        # Prefer language-constrained decoding when mapping is known.
        if lang_code is not None:
            forced_decoder_ids = self.asr_processor_en.get_decoder_prompt_ids(
                language=lang_code,
                task="transcribe",
            )
            generation_kwargs["forced_decoder_ids"] = forced_decoder_ids
        else:
            # Keep non-English long-tail languages functional via Whisper auto language detection.
            logger.info(
                "Whisper language hint unavailable for %s; using auto-detect transcription.",
                src_lang_name,
            )

        # Inference mode: no gradients needed for prediction.
        with torch.no_grad():
            # Generate token ids from input audio features.
            generated_ids = self.asr_model_en.generate(
                inputs["input_features"],
                **generation_kwargs,
            )

        # Convert generated token ids into text and return first result string.
        return self.asr_processor_en.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

    # Internal helper: get cached Indic model + processor for a language, or load them if not loaded yet.
    def _get_indic_asr(self, lang_name: str):
        # Validate that this language has an Indic model configured.
        if lang_name not in INDIC_ASR_MODEL_IDS:
            raise ValueError(f"No IndicWav2Vec model configured for: {lang_name}")

        if lang_name in self.indic_asr_models:
            return self.indic_asr_models[lang_name], self.indic_asr_processors[lang_name]

        # Lazy loading: load model only first time this language is requested.
        with self._indic_asr_lock:
            if lang_name not in self.indic_asr_models:
                # Look up model id for this language.
                model_id = INDIC_ASR_MODEL_IDS[lang_name]
                # Download/load CTC model and move to GPU/CPU.
                model = AutoModelForCTC.from_pretrained(
                    model_id,
                    token=self.hf_token,
                ).to(self.device)
                model.eval()
                self.indic_asr_models[lang_name] = model
                # Download/load matching processor for that model.
                self.indic_asr_processors[lang_name] = AutoProcessor.from_pretrained(
                    model_id,
                    token=self.hf_token,
                )

        # Return already-loaded (or newly loaded) model and processor.
        return self.indic_asr_models[lang_name], self.indic_asr_processors[lang_name]

    # Internal path: transcribe using IndicWav2Vec (CTC) model.
    def _indicwav2vec_transcribe(self, audio_path: str, src_lang_name: str) -> tuple[str, bool]:
        # Get model + processor for requested language.
        model, processor = self._get_indic_asr(src_lang_name)
        # Load and normalize audio to 16kHz mono.
        waveform, sr = self._load_and_resample_audio(audio_path, target_sr=16000)
        # Convert waveform tensor to NumPy for processor input.
        audio_np = waveform.cpu().numpy()

        # Build model-ready input tensor(s).
        inputs = processor(audio_np, sampling_rate=sr, return_tensors="pt")

        # Inference mode: no gradients needed for prediction.
        input_values = inputs.input_values.to(self.device)
        attention_mask = inputs.get("attention_mask")
        if attention_mask is not None:
            attention_mask = attention_mask.to(self.device)

        with torch.no_grad():
            # Run model forward pass and decode token ids from highest-probability logits.
            logits = model(input_values, attention_mask=attention_mask).logits
            predicted_ids = torch.argmax(logits, dim=-1).cpu()

        # CTC decode expects predicted token ids, not raw logits.
        transcription = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0].strip()
        if transcription:
            return transcription, False

        # Some Indic models can return empty output for edge audio; fallback keeps UX reliable.
        logger.warning(
            "Indic ASR produced empty transcription for %s. Falling back to Whisper.",
            src_lang_name,
        )
        return self._whisper_transcribe(audio_path, src_lang_name), True

    # Optional provider path: IndicConformer multilingual model.
    def _indic_conformer_transcribe(self, audio_path: str, src_lang_name: str) -> str:
        lang_code = INDIC_CONFORMER_LANG_CODES.get(src_lang_name)
        if lang_code is None:
            raise ValueError(f"IndicConformer language is not configured for: {src_lang_name}")

        model = self._get_indic_conformer_model()
        waveform, _ = self._load_and_resample_audio(audio_path, target_sr=16000)
        # Custom model expects shape [batch, time] in float32.
        audio_tensor = waveform.unsqueeze(0).cpu().float()

        with torch.no_grad():
            try:
                result = model(audio_tensor, lang_code, self.indic_conformer_decoder)
            except TypeError:
                # Backward compatibility for custom-code variants with 2-arg signature.
                result = model(audio_tensor, lang_code)

        if isinstance(result, (list, tuple)):
            text = result[0] if result else ""
        else:
            text = result
        transcription = str(text).strip() if text is not None else ""
        if not transcription:
            raise ValueError("IndicConformer returned empty transcription.")
        return transcription

    def _legacy_non_english_transcribe_with_stats(
        self,
        audio_path: str,
        src_lang_name: str,
        started: float,
    ) -> tuple[str, dict[str, Any]]:
        # Use Indic model when one is available for this language.
        if src_lang_name in INDIC_ASR_MODEL_IDS:
            indic_model_id = INDIC_ASR_MODEL_IDS[src_lang_name]
            try:
                text, used_whisper_fallback = self._indicwav2vec_transcribe(audio_path, src_lang_name)
            except Exception:  # noqa: BLE001 - keep ASR available even if Indic model path fails.
                logger.exception(
                    "Indic ASR failed for %s. Falling back to Whisper.",
                    src_lang_name,
                )
                text = self._whisper_transcribe(audio_path, src_lang_name)
                used_whisper_fallback = True

            if used_whisper_fallback:
                return text, {
                    "route": "indicwav2vec_whisper_fallback",
                    "model_id": f"{indic_model_id}|{self.asr_model_id_en}",
                    "language": src_lang_name,
                    "provider": DEFAULT_ASR_PROVIDER,
                    "device": self.device,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "output_chars": len(text),
                }

            return text, {
                "route": "indicwav2vec_direct",
                "model_id": indic_model_id,
                "language": src_lang_name,
                "provider": DEFAULT_ASR_PROVIDER,
                "device": self.device,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "output_chars": len(text),
            }

        # Fallback: use Whisper for other configured languages.
        text = self._whisper_transcribe(audio_path, src_lang_name)
        language_hint_applied = src_lang_name in WHISPER_LANG_MAP
        return text, {
            "route": "whisper_fallback_hinted" if language_hint_applied else "whisper_fallback_autodetect",
            "model_id": self.asr_model_id_en,
            "language": src_lang_name,
            "provider": DEFAULT_ASR_PROVIDER,
            "language_hint_applied": language_hint_applied,
            "device": self.device,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "output_chars": len(text),
        }

    # Public method used by the rest of app: choose model path and return text transcription.
    def transcribe_with_stats(self, audio_path: str, src_lang_name: str) -> tuple[str, dict[str, Any]]:
        started = time.perf_counter()

        # Always use Whisper for English.
        if src_lang_name == "English":
            text = self._whisper_transcribe(audio_path, src_lang_name="English")
            return text, {
                "route": "whisper_direct",
                "model_id": self.asr_model_id_en,
                "language": src_lang_name,
                "provider": self.asr_provider,
                "device": self.device,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "output_chars": len(text),
            }

        # Optional provider: try IndicConformer first for supported non-English languages.
        if self.asr_provider == "indic_conformer_multi":
            if src_lang_name in INDIC_CONFORMER_LANG_CODES:
                try:
                    text = self._indic_conformer_transcribe(audio_path, src_lang_name)
                    return text, {
                        "route": "indic_conformer_multi_direct",
                        "model_id": self.indic_conformer_model_id,
                        "language": src_lang_name,
                        "language_code": INDIC_CONFORMER_LANG_CODES[src_lang_name],
                        "decoder": self.indic_conformer_decoder,
                        "provider": self.asr_provider,
                        "device": self.device,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                        "output_chars": len(text),
                    }
                except Exception as exc:  # noqa: BLE001 - preserve uptime by rolling back to legacy ASR path.
                    logger.exception(
                        "IndicConformer ASR failed for %s. Rolling back to legacy ASR stack.",
                        src_lang_name,
                    )
                    text, legacy_stats = self._legacy_non_english_transcribe_with_stats(
                        audio_path=audio_path,
                        src_lang_name=src_lang_name,
                        started=started,
                    )
                    legacy_stats["route"] = f"indic_conformer_multi_rollback_to_{legacy_stats['route']}"
                    legacy_stats["provider"] = self.asr_provider
                    legacy_stats["rollback_reason"] = str(exc)
                    legacy_stats["rollback_target_provider"] = DEFAULT_ASR_PROVIDER
                    legacy_stats["model_id"] = f"{self.indic_conformer_model_id}|{legacy_stats['model_id']}"
                    return text, legacy_stats

            logger.info(
                "Language %s is not mapped for IndicConformer. Using legacy ASR stack.",
                src_lang_name,
            )

        return self._legacy_non_english_transcribe_with_stats(
            audio_path=audio_path,
            src_lang_name=src_lang_name,
            started=started,
        )

    def transcribe(self, audio_path: str, src_lang_name: str) -> str:
        text, _ = self.transcribe_with_stats(audio_path=audio_path, src_lang_name=src_lang_name)
        return text
