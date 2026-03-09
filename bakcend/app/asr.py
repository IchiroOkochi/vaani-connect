from __future__ import annotations  # Keep type hints as strings until runtime (avoids some import/type issues).

import time
from typing import Any

import torch  # PyTorch: tensor math + deep learning runtime.
import torchaudio  # Audio loading helpers from PyTorch ecosystem.
import torchaudio.functional as AF  # Audio utility functions (we use resample below).
from transformers import AutoModelForCTC, AutoModelForSpeechSeq2Seq, AutoProcessor  # Hugging Face model/processor loaders.

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
        # Load matching processor (handles audio preprocessing + decoding).
        self.asr_processor_en = AutoProcessor.from_pretrained(self.asr_model_id_en)

        # Cache dict for loaded Indic models (lazy loaded on first use per language).
        self.indic_asr_models = {}
        # Cache dict for loaded Indic processors (one per language model).
        self.indic_asr_processors = {}

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
        # Fail fast if language is not configured for Whisper.
        if lang_code is None:
            raise ValueError(f"Unsupported language for Whisper ASR: {src_lang_name}")

        # Load and normalize audio to 16kHz mono.
        waveform, sr = self._load_and_resample_audio(audio_path, target_sr=16000)
        # Convert tensor to NumPy because processor accepts array-like audio input.
        audio_np = waveform.cpu().numpy()

        # Create model input features as PyTorch tensors, then move them to GPU/CPU device.
        inputs = self.asr_processor_en(
            audio_np, sampling_rate=sr, return_tensors="pt"
        ).to(self.device)

        # Force decoder to use selected language and transcription task (not translation).
        forced_decoder_ids = self.asr_processor_en.get_decoder_prompt_ids(
            language=lang_code,
            task="transcribe",
        )

        # Inference mode: no gradients needed for prediction.
        with torch.no_grad():
            # Generate token ids from input audio features.
            generated_ids = self.asr_model_en.generate(
                inputs["input_features"],
                max_new_tokens=200,
                forced_decoder_ids=forced_decoder_ids,
            )

        # Convert generated token ids into text and return first result string.
        return self.asr_processor_en.batch_decode(generated_ids, skip_special_tokens=True)[0]

    # Internal helper: get cached Indic model + processor for a language, or load them if not loaded yet.
    def _get_indic_asr(self, lang_name: str):
        # Validate that this language has an Indic model configured.
        if lang_name not in INDIC_ASR_MODEL_IDS:
            raise ValueError(f"No IndicWav2Vec model configured for: {lang_name}")

        # Lazy loading: load model only first time this language is requested.
        if lang_name not in self.indic_asr_models:
            # Look up model id for this language.
            model_id = INDIC_ASR_MODEL_IDS[lang_name]
            # Download/load CTC model and move to GPU/CPU.
            self.indic_asr_models[lang_name] = AutoModelForCTC.from_pretrained(
                model_id,
                token=self.hf_token,
            ).to(self.device)
            # Download/load matching processor for that model.
            self.indic_asr_processors[lang_name] = AutoProcessor.from_pretrained(
                model_id,
                token=self.hf_token,
            )

        # Return already-loaded (or newly loaded) model and processor.
        return self.indic_asr_models[lang_name], self.indic_asr_processors[lang_name]

    # Internal path: transcribe using IndicWav2Vec (CTC) model.
    def _indicwav2vec_transcribe(self, audio_path: str, src_lang_name: str) -> str:
        # Get model + processor for requested language.
        model, processor = self._get_indic_asr(src_lang_name)
        # Load and normalize audio to 16kHz mono.
        waveform, sr = self._load_and_resample_audio(audio_path, target_sr=16000)
        # Convert waveform tensor to NumPy for processor input.
        audio_np = waveform.cpu().numpy()

        # Build model-ready input tensor(s).
        inputs = processor(audio_np, sampling_rate=sr, return_tensors="pt")

        # Inference mode: no gradients needed for prediction.
        with torch.no_grad():
            # Run model forward pass and move logits back to CPU for decoding.
            logits = model(inputs.input_values.to(self.device)).logits.cpu()

        # Decode logits to text and return first transcription result.
        return processor.batch_decode(logits.numpy())[0]

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
                "device": self.device,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "output_chars": len(text),
            }

        # Use Indic model when one is available for this language.
        if src_lang_name in INDIC_ASR_MODEL_IDS:
            text = self._indicwav2vec_transcribe(audio_path, src_lang_name)
            return text, {
                "route": "indicwav2vec_direct",
                "model_id": INDIC_ASR_MODEL_IDS[src_lang_name],
                "language": src_lang_name,
                "device": self.device,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "output_chars": len(text),
            }

        # Fallback: use Whisper for other configured languages.
        text = self._whisper_transcribe(audio_path, src_lang_name)
        return text, {
            "route": "whisper_fallback",
            "model_id": self.asr_model_id_en,
            "language": src_lang_name,
            "device": self.device,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "output_chars": len(text),
        }

    def transcribe(self, audio_path: str, src_lang_name: str) -> str:
        text, _ = self.transcribe_with_stats(audio_path=audio_path, src_lang_name=src_lang_name)
        return text
