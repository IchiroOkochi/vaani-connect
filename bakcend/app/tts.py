import tempfile

from gtts import gTTS

GTTS_LANG_MAP = {
    "English": "en",
    "Assamese": "as",
    "Hindi": "hi",
    "Gujarati": "gu",
    "Telugu": "te",
    "Tamil": "ta",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Bengali": "bn",
    "Marathi": "mr",
    "Nepali": "ne",
    "Odia": "or",
    "Punjabi": "pa",
    "Urdu": "ur",
}


def tts_generate(text: str, tgt_lang_name: str) -> str | None:
    if not text or not text.strip():
        return None

    lang_code = GTTS_LANG_MAP.get(tgt_lang_name, "en")

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp_path = tmp_file.name
    tmp_file.close()

    try:
        tts = gTTS(text=text, lang=lang_code)
    except ValueError:
        # Some mapped language codes may not be available in current gTTS build.
        # Fallback to English speech so text translation still succeeds.
        tts = gTTS(text=text, lang="en")
    tts.save(tmp_path)
    return tmp_path
