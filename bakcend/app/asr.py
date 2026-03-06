from __future__ import annotations

import torch
import torchaudio
import torchaudio.functional as AF
from transformers import AutoModelForCTC, AutoModelForSpeechSeq2Seq, AutoProcessor

WHISPER_LANG_MAP = {
    "English": "en",
    "Hindi": "hi",
    "Telugu": "te",
    "Tamil": "ta",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Bengali": "bn",
    "Marathi": "mr",
}

INDIC_ASR_MODEL_IDS = {
    "Hindi": "ai4bharat/indicwav2vec-hindi",
    "Telugu": "ai4bharat/indicwav2vec_v1_telugu",
    "Tamil": "ai4bharat/indicwav2vec_v1_tamil",
    "Bengali": "ai4bharat/indicwav2vec_v1_bengali",
    "Marathi": "ai4bharat/indicwav2vec_v1_marathi",
}


class ASRService:
    def __init__(self, hf_token: str):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.hf_token = hf_token

        self.asr_model_id_en = "openai/whisper-large-v3-turbo"
        self.asr_model_en = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.asr_model_id_en
        ).to(self.device)
        self.asr_processor_en = AutoProcessor.from_pretrained(self.asr_model_id_en)

        self.indic_asr_models = {}
        self.indic_asr_processors = {}

    def _load_and_resample_audio(self, audio_path: str, target_sr: int = 16000):
        waveform, sr = torchaudio.load(audio_path)

        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        if sr != target_sr:
            waveform = AF.resample(waveform, sr, target_sr)
            sr = target_sr

        return waveform.squeeze(0), sr

    def _whisper_transcribe(self, audio_path: str, src_lang_name: str) -> str:
        lang_code = WHISPER_LANG_MAP.get(src_lang_name)
        if lang_code is None:
            raise ValueError(f"Unsupported language for Whisper ASR: {src_lang_name}")

        waveform, sr = self._load_and_resample_audio(audio_path, target_sr=16000)
        audio_np = waveform.cpu().numpy()

        inputs = self.asr_processor_en(
            audio_np, sampling_rate=sr, return_tensors="pt"
        ).to(self.device)

        forced_decoder_ids = self.asr_processor_en.get_decoder_prompt_ids(
            language=lang_code,
            task="transcribe",
        )

        with torch.no_grad():
            generated_ids = self.asr_model_en.generate(
                inputs["input_features"],
                max_new_tokens=200,
                forced_decoder_ids=forced_decoder_ids,
            )

        return self.asr_processor_en.batch_decode(generated_ids, skip_special_tokens=True)[0]

    def _get_indic_asr(self, lang_name: str):
        if lang_name not in INDIC_ASR_MODEL_IDS:
            raise ValueError(f"No IndicWav2Vec model configured for: {lang_name}")

        if lang_name not in self.indic_asr_models:
            model_id = INDIC_ASR_MODEL_IDS[lang_name]
            self.indic_asr_models[lang_name] = AutoModelForCTC.from_pretrained(
                model_id,
                token=self.hf_token,
            ).to(self.device)
            self.indic_asr_processors[lang_name] = AutoProcessor.from_pretrained(
                model_id,
                token=self.hf_token,
            )

        return self.indic_asr_models[lang_name], self.indic_asr_processors[lang_name]

    def _indicwav2vec_transcribe(self, audio_path: str, src_lang_name: str) -> str:
        model, processor = self._get_indic_asr(src_lang_name)
        waveform, sr = self._load_and_resample_audio(audio_path, target_sr=16000)
        audio_np = waveform.cpu().numpy()

        inputs = processor(audio_np, sampling_rate=sr, return_tensors="pt")

        with torch.no_grad():
            logits = model(inputs.input_values.to(self.device)).logits.cpu()

        return processor.batch_decode(logits.numpy())[0]

    def transcribe(self, audio_path: str, src_lang_name: str) -> str:
        if src_lang_name == "English":
            return self._whisper_transcribe(audio_path, src_lang_name="English")

        if src_lang_name in INDIC_ASR_MODEL_IDS:
            return self._indicwav2vec_transcribe(audio_path, src_lang_name)

        return self._whisper_transcribe(audio_path, src_lang_name)
