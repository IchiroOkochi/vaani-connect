import tempfile

from gtts import gTTS

GTTS_LANG_MAP = {
    "English": "en",
    "Hindi": "hi",
    "Telugu": "te",
    "Tamil": "ta",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Bengali": "bn",
    "Marathi": "mr",
}


def tts_generate(text: str, tgt_lang_name: str) -> str | None:
    if not text or not text.strip():
        return None

    lang_code = GTTS_LANG_MAP.get(tgt_lang_name, "en")

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp_path = tmp_file.name
    tmp_file.close()

    tts = gTTS(text=text, lang=lang_code)
    tts.save(tmp_path)
    return tmp_path
