"""Example backend entrypoint for translation + ASR + TTS services."""

from app.asr import ASRService
from app.config import login_huggingface
from app.translation import TranslationService
from app.tts import tts_generate


def build_services():
    hf_token = login_huggingface()
    translation_service = TranslationService()
    asr_service = ASRService(hf_token=hf_token)
    return translation_service, asr_service


if __name__ == "__main__":
    translation_service, _ = build_services()
    demo_text = "Hello, how are you?"
    translated = translation_service.translate_text(demo_text, "eng_Latn", "hin_Deva")
    print("Translated:", translated)

    audio_path = tts_generate(translated, "Hindi")
    print("TTS MP3:", audio_path)
