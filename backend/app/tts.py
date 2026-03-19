from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
from urllib import error, request

from gtts import gTTS

from app.languages import LANGUAGE_TO_CODE

DEFAULT_TTS_PROVIDER = "gtts"
SUPPORTED_TTS_PROVIDERS = {DEFAULT_TTS_PROVIDER, "parler_sidecar"}
DEFAULT_TTS_SIDECAR_URL = "http://127.0.0.1:8010"
DEFAULT_TTS_SIDECAR_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class TTSRoute:
    requested_language: str
    voice_language: str
    language_code: str

    @property
    def uses_fallback_voice(self) -> bool:
        return self.requested_language != self.voice_language


@dataclass(frozen=True)
class TTSGeneration:
    path: str | None
    provider: str
    requested_language: str
    voice_language: str | None
    language_code: str | None
    uses_fallback_voice: bool | None


# gTTS does not offer native voices for every supported translation target, so
# unsupported targets are routed to the closest available Indic voice instead
# of silently falling all the way back to English.
TTS_VOICE_LANGUAGE_MAP = {
    "English": "English",
    "Assamese": "Assamese",
    "Bodo": "Hindi",
    "Dogri": "Hindi",
    "Gujarati": "Gujarati",
    "Hindi": "Hindi",
    "Kannada": "Kannada",
    "Kashmiri": "Urdu",
    "Konkani": "Hindi",
    "Maithili": "Hindi",
    "Malayalam": "Malayalam",
    "Bengali": "Bengali",
    "Manipuri": "Bengali",
    "Marathi": "Marathi",
    "Nepali": "Nepali",
    "Odia": "Odia",
    "Punjabi": "Punjabi",
    "Sanskrit": "Hindi",
    "Santali": "Hindi",
    "Sindhi": "Urdu",
    "Tamil": "Tamil",
    "Telugu": "Telugu",
    "Urdu": "Urdu",
}

GTTS_LANGUAGE_CODES = {
    "English": "en",
    "Assamese": "as",
    "Bengali": "bn",
    "Gujarati": "gu",
    "Hindi": "hi",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Marathi": "mr",
    "Nepali": "ne",
    "Odia": "or",
    "Punjabi": "pa",
    "Tamil": "ta",
    "Telugu": "te",
    "Urdu": "ur",
}


def resolve_tts_route(tgt_lang_name: str) -> TTSRoute:
    if tgt_lang_name not in LANGUAGE_TO_CODE:
        raise ValueError(f"Unsupported language for TTS: {tgt_lang_name}")

    voice_language = TTS_VOICE_LANGUAGE_MAP.get(tgt_lang_name)
    if voice_language is None:
        raise ValueError(f"No TTS route configured for: {tgt_lang_name}")

    language_code = GTTS_LANGUAGE_CODES.get(voice_language)
    if language_code is None:
        raise ValueError(f"No gTTS language code configured for voice language: {voice_language}")

    return TTSRoute(
        requested_language=tgt_lang_name,
        voice_language=voice_language,
        language_code=language_code,
    )


def _selected_tts_provider() -> str:
    requested_provider = os.getenv("VAANI_TTS_PROVIDER", DEFAULT_TTS_PROVIDER).strip().lower()
    if requested_provider not in SUPPORTED_TTS_PROVIDERS:
        return DEFAULT_TTS_PROVIDER
    return requested_provider


def _sidecar_base_url() -> str:
    return os.getenv("VAANI_TTS_SIDECAR_URL", DEFAULT_TTS_SIDECAR_URL).rstrip("/")


def _sidecar_timeout_seconds() -> float:
    raw = os.getenv("VAANI_TTS_SIDECAR_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_TTS_SIDECAR_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        return DEFAULT_TTS_SIDECAR_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_TTS_SIDECAR_TIMEOUT_SECONDS


def _temp_audio_file(suffix: str):
    temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    return temp_audio, temp_audio.name


def _write_temp_audio(content: bytes, suffix: str) -> str:
    temp_audio, temp_path = _temp_audio_file(suffix)
    try:
        temp_audio.write(content)
    finally:
        temp_audio.close()
    return temp_path


def _suffix_from_content_type(content_type: str | None) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized == "audio/mpeg":
        return ".mp3"
    if normalized in {"audio/wav", "audio/x-wav", "audio/wave"}:
        return ".wav"
    if normalized == "audio/flac":
        return ".flac"
    return ".wav"


def _gtts_generate(text: str, tgt_lang_name: str) -> TTSGeneration:
    route = resolve_tts_route(tgt_lang_name)

    temp_audio, temp_path = _temp_audio_file(".mp3")
    temp_audio.close()

    try:
        tts = gTTS(text=text, lang=route.language_code)
    except ValueError:
        # If gTTS rejects a configured code in the local build, keep translation
        # functional with the universal English fallback.
        tts = gTTS(text=text, lang="en")
        route = TTSRoute(
            requested_language=tgt_lang_name,
            voice_language="English",
            language_code="en",
        )

    tts.save(temp_path)
    return TTSGeneration(
        path=temp_path,
        provider="gTTS",
        requested_language=tgt_lang_name,
        voice_language=route.voice_language,
        language_code=route.language_code,
        uses_fallback_voice=route.uses_fallback_voice,
    )


def _sidecar_generate(text: str, tgt_lang_name: str) -> TTSGeneration:
    payload = json.dumps(
        {
            "text": text,
            "target_language": tgt_lang_name,
        }
    ).encode("utf-8")
    sidecar_request = request.Request(
        url=f"{_sidecar_base_url()}/tts",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(sidecar_request, timeout=_sidecar_timeout_seconds()) as response:
            audio_bytes = response.read()
            if not audio_bytes:
                return TTSGeneration(
                    path=None,
                    provider="indic_parler_sidecar",
                    requested_language=tgt_lang_name,
                    voice_language=tgt_lang_name,
                    language_code=None,
                    uses_fallback_voice=False,
                )
            content_type = response.headers.get("Content-Type")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"TTS sidecar returned HTTP {exc.code}: {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"TTS sidecar request failed: {exc.reason}") from exc

    temp_path = _write_temp_audio(audio_bytes, _suffix_from_content_type(content_type))
    return TTSGeneration(
        path=temp_path,
        provider="indic_parler_sidecar",
        requested_language=tgt_lang_name,
        voice_language=tgt_lang_name,
        language_code=None,
        uses_fallback_voice=False,
    )


def tts_generate_with_metadata(text: str, tgt_lang_name: str) -> TTSGeneration | None:
    if not text or not text.strip():
        return None

    if _selected_tts_provider() == "parler_sidecar":
        return _sidecar_generate(text, tgt_lang_name)
    return _gtts_generate(text, tgt_lang_name)


def tts_generate(text: str, tgt_lang_name: str) -> str | None:
    generation = tts_generate_with_metadata(text, tgt_lang_name)
    return generation.path if generation else None
