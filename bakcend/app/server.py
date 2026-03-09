from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock
from typing import Deque

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
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

UPLOAD_CHUNK_BYTES = 1024 * 1024
DEFAULT_ALLOWED_ORIGINS = "http://localhost:8081,http://127.0.0.1:8081,http://localhost:3000"
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or [item.strip() for item in default.split(",") if item.strip()]


API_KEY = os.getenv("VAANI_API_KEY")
RATE_LIMIT_MAX_REQUESTS = _env_int("VAANI_RATE_LIMIT_REQUESTS", 30)
RATE_LIMIT_WINDOW_SECONDS = _env_int("VAANI_RATE_LIMIT_WINDOW_SECONDS", 60)
MAX_UPLOAD_BYTES = _env_int("VAANI_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
AUDIO_TTL_SECONDS = _env_int("VAANI_AUDIO_TTL_SECONDS", 60 * 60)
ALLOWED_ORIGINS = _env_csv("VAANI_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
ALLOW_CREDENTIALS = "*" not in ALLOWED_ORIGINS

_client_request_times: dict[str, Deque[float]] = defaultdict(deque)
_rate_limit_lock = Lock()
_service_lock = Lock()
_services: tuple[object, object] | None = None
_service_init_error: str | None = None


def _to_lang_code(name: str) -> str:
    try:
        return LANGUAGE_TO_CODE[name]
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {name}") from exc


def _require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not API_KEY:
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


def _enforce_rate_limit(request: Request) -> None:
    if RATE_LIMIT_MAX_REQUESTS <= 0 or RATE_LIMIT_WINDOW_SECONDS <= 0:
        return

    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS

    with _rate_limit_lock:
        requests = _client_request_times[client]
        while requests and requests[0] < cutoff:
            requests.popleft()

        if len(requests) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
            )
        requests.append(now)


def get_services():
    global _services
    global _service_init_error

    if _services is not None:
        return _services

    with _service_lock:
        if _services is not None:
            return _services
        if _service_init_error is not None:
            raise HTTPException(status_code=503, detail=_service_init_error)

        try:
            _services = build_services()
        except Exception as exc:  # noqa: BLE001 - return service init state to client
            _service_init_error = f"Backend models failed to initialize: {exc}"
            raise HTTPException(status_code=503, detail=_service_init_error) from exc

    return _services


def _cleanup_expired_audio_files() -> None:
    if AUDIO_TTL_SECONDS <= 0:
        return

    cutoff = time.time() - AUDIO_TTL_SECONDS
    for candidate in audio_dir.glob("*.mp3"):
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)
        except OSError:
            continue


def _safe_unlink(path: str | Path | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _safe_audio_path(filename: str) -> Path:
    if not filename or Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid audio filename")

    resolved = (audio_dir / filename).resolve()
    if resolved.parent != audio_dir_resolved:
        raise HTTPException(status_code=400, detail="Invalid audio filename")
    if resolved.suffix.lower() != ".mp3":
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    return resolved


def _persist_audio_file(tts_path: str) -> str:
    audio_id = f"{uuid.uuid4()}.mp3"
    stable_path = audio_dir / audio_id
    try:
        shutil.copyfile(tts_path, stable_path)
    finally:
        _safe_unlink(tts_path)
    return f"/audio/{audio_id}"


def _validate_audio_upload(audio: UploadFile) -> str:
    suffix = Path(audio.filename or "recording.wav").suffix.lower() or ".wav"
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {suffix}")
    if audio.content_type and not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an audio file")
    return suffix


class TextTranslateRequest(BaseModel):
    text: str
    source_language: str
    target_language: str
    include_speech: bool = True


app = FastAPI(title="Vaani Connect API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

audio_dir = Path(tempfile.gettempdir()) / "vaani_connect_audio"
audio_dir.mkdir(parents=True, exist_ok=True)
audio_dir_resolved = audio_dir.resolve()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/languages")
def languages() -> list[str]:
    return list(LANGUAGE_TO_CODE.keys())


@app.post("/translate/text")
def translate_text(
    payload: TextTranslateRequest,
    request: Request,
    _: None = Depends(_require_api_key),
):
    _enforce_rate_limit(request)
    _cleanup_expired_audio_files()

    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    src = _to_lang_code(payload.source_language)
    tgt = _to_lang_code(payload.target_language)

    translation_service, _ = get_services()
    translated_text = translation_service.translate_text(payload.text, src, tgt)
    audio_url = None

    if payload.include_speech:
        tts_path = tts_generate(translated_text, payload.target_language)
        if tts_path:
            audio_url = _persist_audio_file(tts_path)

    return {
        "source_text": payload.text,
        "translated_text": translated_text,
        "audio_url": audio_url,
    }


@app.post("/translate/speech")
async def translate_speech(
    request: Request,
    audio: UploadFile = File(...),
    source_language: str = Form(...),
    target_language: str = Form(...),
    _: None = Depends(_require_api_key),
):
    _enforce_rate_limit(request)
    _cleanup_expired_audio_files()

    _to_lang_code(source_language)
    tgt_lang_code = _to_lang_code(target_language)
    suffix = _validate_audio_upload(audio)

    temp_audio_path: str | None = None

    try:
        bytes_written = 0
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
            temp_audio_path = temp_audio.name
            while True:
                chunk = await audio.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Audio file exceeds max size of {MAX_UPLOAD_BYTES} bytes",
                    )
                temp_audio.write(chunk)

        if bytes_written == 0:
            raise HTTPException(status_code=400, detail="Uploaded audio cannot be empty")

        translation_service, asr_service = get_services()
        transcribed_text = asr_service.transcribe(temp_audio_path, source_language)
        translated_text = translation_service.translate_text(
            transcribed_text,
            _to_lang_code(source_language),
            tgt_lang_code,
        )

        audio_url = None
        tts_path = tts_generate(translated_text, target_language)
        if tts_path:
            audio_url = _persist_audio_file(tts_path)

        return {
            "transcribed_text": transcribed_text,
            "translated_text": translated_text,
            "audio_url": audio_url,
        }
    finally:
        await audio.close()
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)


@app.get("/audio/{filename}")
def get_audio(filename: str):
    _cleanup_expired_audio_files()
    path = _safe_audio_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg")
