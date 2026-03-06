from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.main import build_services
from app.tts import tts_generate

LANGUAGE_TO_CODE = {
    "English": "eng_Latn",
    "Hindi": "hin_Deva",
    "Telugu": "tel_Telu",
    "Tamil": "tam_Taml",
    "Kannada": "kan_Knda",
    "Malayalam": "mal_Mlym",
    "Bengali": "ben_Beng",
    "Marathi": "mar_Deva",
}


def _to_lang_code(name: str) -> str:
    try:
        return LANGUAGE_TO_CODE[name]
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {name}") from exc


class TextTranslateRequest(BaseModel):
    text: str
    source_language: str
    target_language: str
    include_speech: bool = True


app = FastAPI(title="Vaani Connect API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

translation_service, asr_service = build_services()
audio_dir = Path(tempfile.gettempdir()) / "vaani_connect_audio"
audio_dir.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/languages")
def languages() -> list[str]:
    return list(LANGUAGE_TO_CODE.keys())


@app.post("/translate/text")
def translate_text(payload: TextTranslateRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    src = _to_lang_code(payload.source_language)
    tgt = _to_lang_code(payload.target_language)

    translated_text = translation_service.translate_text(payload.text, src, tgt)
    audio_url = None

    if payload.include_speech:
        tts_path = tts_generate(translated_text, payload.target_language)
        if tts_path:
            audio_id = f"{uuid.uuid4()}.mp3"
            stable_path = audio_dir / audio_id
            shutil.copyfile(tts_path, stable_path)
            audio_url = f"/audio/{audio_id}"

    return {
        "source_text": payload.text,
        "translated_text": translated_text,
        "audio_url": audio_url,
    }


@app.post("/translate/speech")
async def translate_speech(
    audio: UploadFile = File(...),
    source_language: str = Form(...),
    target_language: str = Form(...),
):
    _to_lang_code(source_language)
    tgt_lang_code = _to_lang_code(target_language)

    suffix = Path(audio.filename or "recording.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
        temp_audio.write(await audio.read())
        temp_audio_path = temp_audio.name

    try:
        transcribed_text = asr_service.transcribe(temp_audio_path, source_language)
        translated_text = translation_service.translate_text(
            transcribed_text,
            _to_lang_code(source_language),
            tgt_lang_code,
        )

        audio_url = None
        tts_path = tts_generate(translated_text, target_language)
        if tts_path:
            audio_id = f"{uuid.uuid4()}.mp3"
            stable_path = audio_dir / audio_id
            shutil.copyfile(tts_path, stable_path)
            audio_url = f"/audio/{audio_id}"

        return {
            "transcribed_text": transcribed_text,
            "translated_text": translated_text,
            "audio_url": audio_url,
        }
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)


@app.get("/audio/{filename}")
def get_audio(filename: str):
    path = audio_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg")
