from __future__ import annotations  # Postpone evaluation of type hints until runtime.

import json
import logging  # Standard logging for startup/warmup diagnostics.
import os  # OS/environment/file helpers.
import shutil  # File copy helpers.
import tempfile  # Temporary file/directory helpers.
import time  # Time helpers for rate limit and cleanup windows.
import uuid  # Unique id generator for audio filenames.
from collections import defaultdict, deque  # Data structures used by in-memory rate limiting.
from pathlib import Path  # Safer file path handling.
from threading import Lock  # Thread lock for shared global state.
from typing import Any, Deque  # Type hint for deque of timestamps.

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile  # FastAPI core types.
from fastapi.middleware.cors import CORSMiddleware  # CORS middleware for browser apps.
from fastapi.responses import FileResponse  # Return files (mp3) from endpoints.
from pydantic import BaseModel  # Request body schema model.

from app.main import build_services  # Builds translation + ASR services.
from app.tts import tts_generate  # Converts translated text into speech audio.

# Module logger for operational visibility.
logger = logging.getLogger(__name__)

# Canonical language names mapped to IndicTrans language codes.
LANGUAGE_TO_CODE = {
    "English": "eng_Latn",
    "Assamese": "asm_Beng",
    "Bodo": "brx_Deva",
    "Dogri": "doi_Deva",
    "Gujarati": "guj_Gujr",
    "Hindi": "hin_Deva",
    "Kannada": "kan_Knda",
    "Kashmiri": "kas_Arab",
    "Konkani": "gom_Deva",
    "Maithili": "mai_Deva",
    "Malayalam": "mal_Mlym",
    "Bengali": "ben_Beng",
    "Manipuri": "mni_Mtei",
    "Marathi": "mar_Deva",
    "Nepali": "npi_Deva",
    "Odia": "ory_Orya",
    "Punjabi": "pan_Guru",
    "Sanskrit": "san_Deva",
    "Santali": "sat_Olck",
    "Sindhi": "snd_Arab",
    "Tamil": "tam_Taml",
    "Telugu": "tel_Telu",
    "Urdu": "urd_Arab",
}

# Dialect and alternate names that are normalized to canonical names above.
LANGUAGE_ALIASES = {
    # Hindi cluster dialects.
    "Awadhi": "Hindi",
    "Avadhi": "Hindi",
    "Bhojpuri": "Hindi",
    "Braj": "Hindi",
    "Bundeli": "Hindi",
    "Chhattisgarhi": "Hindi",
    "Garhwali": "Hindi",
    "Haryanvi": "Hindi",
    "Kumaoni": "Hindi",
    "Magahi": "Hindi",
    "Marwari": "Hindi",
    # Bengali cluster dialects.
    "Sylheti": "Bengali",
    "Chittagonian": "Bengali",
    # Urdu variants.
    "Dakhini": "Urdu",
    "Hyderabadi Urdu": "Urdu",
    # Kannada variants.
    "Tulu": "Kannada",
    "Kodava": "Kannada",
    # Common alternate spellings.
    "Bangla": "Bengali",
    "Oriya": "Odia",
    "Meitei": "Manipuri",
}

# Read uploaded audio in 1MB chunks to avoid loading everything into memory at once.
UPLOAD_CHUNK_BYTES = 1024 * 1024
# Default CORS origins for local frontend development.
DEFAULT_ALLOWED_ORIGINS = "http://localhost:8081,http://127.0.0.1:8081,http://localhost:3000"
# Allowed audio file extensions for speech upload endpoint.
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}


# Read an integer env var safely; return default when missing/invalid.
def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)  # Read raw string from environment.
    if raw is None:  # Missing variable -> use fallback.
        return default
    try:
        return int(raw)  # Convert string to integer.
    except ValueError:  # Invalid integer string -> fallback.
        return default


# Read comma-separated env var safely; trim spaces and remove empty items.
def _env_csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)  # Use env value or provided default.
    values = [item.strip() for item in raw.split(",") if item.strip()]  # Normalize entries.
    return values or [item.strip() for item in default.split(",") if item.strip()]  # Never return empty list.


# Read a boolean env var safely.
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Normalize language tokens to make matching resilient to casing and separators.
def _normalize_language_key(value: str) -> str:
    return " ".join(
        value.strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace("(", " ")
        .replace(")", " ")
        .split()
    )


def _build_language_name_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}

    # Canonical names map to themselves.
    for canonical_name in LANGUAGE_TO_CODE:
        lookup[_normalize_language_key(canonical_name)] = canonical_name

    # Language codes can be accepted as input and converted to canonical names.
    for canonical_name, lang_code in LANGUAGE_TO_CODE.items():
        lookup[_normalize_language_key(lang_code)] = canonical_name

    # Aliases map to canonical names.
    for alias, canonical_name in LANGUAGE_ALIASES.items():
        if canonical_name in LANGUAGE_TO_CODE:
            lookup[_normalize_language_key(alias)] = canonical_name

    return lookup


LANGUAGE_NAME_LOOKUP = _build_language_name_lookup()


# Optional API key. If unset, API key auth is disabled.
API_KEY = os.getenv("VAANI_API_KEY")
# Max requests allowed in a rate-limit window per client ip.
RATE_LIMIT_MAX_REQUESTS = _env_int("VAANI_RATE_LIMIT_REQUESTS", 30)
# Duration of rate-limit window in seconds.
RATE_LIMIT_WINDOW_SECONDS = _env_int("VAANI_RATE_LIMIT_WINDOW_SECONDS", 60)
# Upload size cap (bytes) for incoming audio files.
MAX_UPLOAD_BYTES = _env_int("VAANI_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
# Generated mp3 lifetime in seconds before cleanup.
AUDIO_TTL_SECONDS = _env_int("VAANI_AUDIO_TTL_SECONDS", 60 * 60)
# Allowed CORS origins.
ALLOWED_ORIGINS = _env_csv("VAANI_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
# CORS credential support cannot be true with wildcard origin.
ALLOW_CREDENTIALS = "*" not in ALLOWED_ORIGINS
# Enables model warmup during startup to reduce first-request latency.
ENABLE_STARTUP_WARMUP = _env_bool("VAANI_ENABLE_STARTUP_WARMUP", True)
# Optional list of ASR languages to preload Indic ASR models for.
WARMUP_ASR_LANGUAGES = _env_csv("VAANI_WARMUP_ASR_LANGUAGES", "Hindi,Telugu,Tamil")
# In-memory history size for debug metrics endpoint.
RECENT_METRICS_LIMIT = max(1, _env_int("VAANI_RECENT_METRICS_LIMIT", 100))

# In-memory map: client ip -> deque of request timestamps.
_client_request_times: dict[str, Deque[float]] = defaultdict(deque)
# Lock to protect rate-limit map updates.
_rate_limit_lock = Lock()
# Lock to protect one-time service initialization.
_service_lock = Lock()
# Lock to protect metrics history appends/reads.
_metrics_lock = Lock()
# Lazy-initialized tuple: (translation_service, asr_service).
_services: tuple[object, object] | None = None
# Stores service startup failure reason to reuse in later responses.
_service_init_error: str | None = None
# Ring buffer for recently emitted metrics events.
_recent_metrics: deque[dict[str, Any]] = deque(maxlen=RECENT_METRICS_LIMIT)


# Resolve any canonical/alias/code input to a canonical language name.
def _canonical_language_name(name: str) -> str:
    canonical = LANGUAGE_NAME_LOOKUP.get(_normalize_language_key(name))
    if canonical is None:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {name}")
    return canonical


# Convert incoming language text to internal IndicTrans code.
def _to_lang_code(name: str) -> str:
    return LANGUAGE_TO_CODE[_canonical_language_name(name)]


# Dependency that validates API key from `X-API-Key` header when API key auth is enabled.
def _require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not API_KEY:  # No configured key -> skip auth.
        return
    if x_api_key != API_KEY:  # Wrong or missing key -> reject.
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


# In-memory sliding-window rate limit by client IP.
def _enforce_rate_limit(request: Request) -> None:
    if RATE_LIMIT_MAX_REQUESTS <= 0 or RATE_LIMIT_WINDOW_SECONDS <= 0:
        return  # Non-positive settings disable rate limiting.

    client = request.client.host if request.client else "unknown"  # Source client ip.
    now = time.monotonic()  # Monotonic clock avoids wall-clock jumps.
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS  # Old timestamps before this are expired.

    with _rate_limit_lock:
        requests = _client_request_times[client]  # Get deque for this client.
        while requests and requests[0] < cutoff:
            requests.popleft()  # Remove expired entries from left side.

        if len(requests) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
            )
        requests.append(now)  # Record this request timestamp.


# Lazy-load backend model services once, with thread safety.
def get_services():
    global _services
    global _service_init_error

    if _services is not None:
        return _services  # Fast path if already initialized.

    with _service_lock:
        if _services is not None:
            return _services  # Double-checked lock pattern.
        if _service_init_error is not None:
            raise HTTPException(status_code=503, detail=_service_init_error)  # Reuse known startup error.

        try:
            _services = build_services()  # Initialize translation and ASR models.
        except Exception as exc:  # noqa: BLE001 - return service init state to client
            _service_init_error = f"Backend models failed to initialize: {exc}"  # Cache failure reason.
            raise HTTPException(status_code=503, detail=_service_init_error) from exc

    return _services


# Warm up translation and selected ASR models at startup.
def _warmup_services() -> None:
    try:
        translation_service, asr_service = get_services()
    except HTTPException:
        logger.exception("Service initialization failed during startup warmup.")
        return

    # Warm translation models to avoid first-user latency spikes.
    try:
        if hasattr(translation_service, "warmup"):
            translation_service.warmup()
        else:
            translation_service.translate_text("hello", "eng_Latn", "hin_Deva")
    except Exception:  # noqa: BLE001 - warmup should not crash API startup.
        logger.exception("Translation warmup failed.")

    # Optionally preload selected Indic ASR models if helper is available.
    get_indic_asr = getattr(asr_service, "_get_indic_asr", None)
    if not callable(get_indic_asr):
        return

    for lang_name in WARMUP_ASR_LANGUAGES:
        try:
            canonical = _canonical_language_name(lang_name)
        except HTTPException:
            logger.warning("Skipping unknown ASR warmup language: %s", lang_name)
            continue

        try:
            get_indic_asr(canonical)
        except Exception:  # noqa: BLE001 - skip languages without an Indic ASR model.
            logger.debug("ASR warmup skipped for %s.", canonical, exc_info=True)


# Delete old generated mp3 files to keep temp folder from growing forever.
def _cleanup_expired_audio_files() -> None:
    if AUDIO_TTL_SECONDS <= 0:
        return  # Non-positive ttl disables cleanup.

    cutoff = time.time() - AUDIO_TTL_SECONDS  # Files older than this should be removed.
    for candidate in audio_dir.glob("*.mp3"):  # Only manage mp3 files created by this app.
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)
        except OSError:
            continue  # Ignore files that fail due to race/permissions.


# Best-effort file deletion helper that never raises to caller.
def _safe_unlink(path: str | Path | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _log_metrics(event: str, payload: dict[str, Any]) -> None:
    record = {
        "event": event,
        "logged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **payload,
    }
    with _metrics_lock:
        _recent_metrics.append(record)

    # JSON log line makes it easier to search/ship metrics from terminal logs.
    logger.info("VAANI_METRICS %s", json.dumps(record, ensure_ascii=True, sort_keys=True))


# Validate requested audio filename and return safe absolute path under audio directory.
def _safe_audio_path(filename: str) -> Path:
    if not filename or Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid audio filename")  # Blocks path traversal input.

    resolved = (audio_dir / filename).resolve()  # Resolve to absolute normalized path.
    if resolved.parent != audio_dir_resolved:
        raise HTTPException(status_code=400, detail="Invalid audio filename")  # Ensures file stays in allowed dir.
    if resolved.suffix.lower() != ".mp3":
        raise HTTPException(status_code=400, detail="Unsupported audio format")  # Only mp3 served by this endpoint.
    return resolved


# Copy generated TTS file to stable temp location and return URL path.
def _persist_audio_file(tts_path: str) -> str:
    audio_id = f"{uuid.uuid4()}.mp3"  # Unique output filename.
    stable_path = audio_dir / audio_id  # Final destination in app audio dir.
    try:
        shutil.copyfile(tts_path, stable_path)  # Move output into stable publicly served location.
    finally:
        _safe_unlink(tts_path)  # Always remove temporary original file.
    return f"/audio/{audio_id}"  # Public API URL for client to fetch.


# Validate uploaded audio file extension and content type.
def _validate_audio_upload(audio: UploadFile) -> str:
    suffix = Path(audio.filename or "recording.wav").suffix.lower() or ".wav"  # Default extension if absent.
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {suffix}")
    if audio.content_type and not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an audio file")
    return suffix


# Request body model for /translate/text endpoint.
class TextTranslateRequest(BaseModel):
    text: str  # Input text to translate.
    source_language: str  # Human-readable source language name.
    target_language: str  # Human-readable target language name.
    include_speech: bool = True  # Whether response should include generated speech audio URL.


# Create FastAPI app instance.
app = FastAPI(title="Vaani Connect API", version="1.0.0")

# Add CORS middleware so frontend apps can call this API from browsers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create directory in OS temp area to store generated mp3 files.
audio_dir = Path(tempfile.gettempdir()) / "vaani_connect_audio"
audio_dir.mkdir(parents=True, exist_ok=True)
audio_dir_resolved = audio_dir.resolve()


# Startup hook: load/warm models so first user request is faster.
@app.on_event("startup")
def startup_warmup() -> None:
    if not ENABLE_STARTUP_WARMUP:
        logger.info("Startup warmup disabled by VAANI_ENABLE_STARTUP_WARMUP.")
        return

    _cleanup_expired_audio_files()
    _warmup_services()


# Simple health-check endpoint for uptime probes.
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Return supported language names for UI dropdowns.
@app.get("/languages")
def languages() -> list[str]:
    return list(LANGUAGE_TO_CODE.keys())


@app.get("/metrics/recent")
def recent_metrics(
    limit: int = 20,
    _: None = Depends(_require_api_key),  # Respect API-key mode when enabled.
) -> dict[str, Any]:
    clamped_limit = max(1, min(limit, RECENT_METRICS_LIMIT))
    with _metrics_lock:
        items = list(_recent_metrics)[-clamped_limit:]
    return {
        "count": len(items),
        "limit": clamped_limit,
        "capacity": RECENT_METRICS_LIMIT,
        "items": items,
    }


# Text translation endpoint (optional TTS output).
@app.post("/translate/text")
def translate_text(
    payload: TextTranslateRequest,
    request: Request,
    _: None = Depends(_require_api_key),  # Enforce API key dependency when configured.
):
    request_started = time.perf_counter()
    request_id = uuid.uuid4().hex[:12]
    _enforce_rate_limit(request)  # Block abusive traffic bursts.
    _cleanup_expired_audio_files()  # Periodic opportunistic cleanup.

    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    source_language = _canonical_language_name(payload.source_language)
    target_language = _canonical_language_name(payload.target_language)
    src = LANGUAGE_TO_CODE[source_language]
    tgt = LANGUAGE_TO_CODE[target_language]

    translation_service, _ = get_services()  # Fetch lazily initialized services.
    translate_with_stats = getattr(translation_service, "translate_text_with_stats", None)
    if callable(translate_with_stats):
        translated_text, translation_stats = translate_with_stats(payload.text, src, tgt)
    else:
        translation_started = time.perf_counter()
        translated_text = translation_service.translate_text(payload.text, src, tgt)
        translation_stats = {
            "route": "unknown",
            "used_fallback": False,
            "model_ids": [],
            "total_latency_ms": round((time.perf_counter() - translation_started) * 1000, 2),
        }

    audio_url = None
    tts_stats: dict[str, Any] = {
        "enabled": payload.include_speech,
        "provider": "gTTS",
        "latency_ms": None,
        "audio_generated": False,
    }

    if payload.include_speech:
        tts_started = time.perf_counter()
        tts_path = tts_generate(translated_text, target_language)  # Generate spoken audio for translated text.
        tts_stats["latency_ms"] = round((time.perf_counter() - tts_started) * 1000, 2)
        if tts_path:
            persist_started = time.perf_counter()
            audio_url = _persist_audio_file(tts_path)  # Store mp3 and return stable URL.
            tts_stats["persist_ms"] = round((time.perf_counter() - persist_started) * 1000, 2)
            tts_stats["audio_generated"] = True

    total_latency_ms = round((time.perf_counter() - request_started) * 1000, 2)
    _log_metrics(
        "translate_text",
        {
            "request_id": request_id,
            "client_ip": _client_ip(request),
            "source_language": source_language,
            "target_language": target_language,
            "source_code": src,
            "target_code": tgt,
            "include_speech": payload.include_speech,
            "input_chars": len(payload.text),
            "output_chars": len(translated_text),
            "input_bytes_utf8": len(payload.text.encode("utf-8")),
            "translation": translation_stats,
            "tts": tts_stats,
            "total_latency_ms": total_latency_ms,
        },
    )

    return {
        "request_id": request_id,
        "source_text": payload.text,
        "translated_text": translated_text,
        "audio_url": audio_url,
    }


# Speech translation endpoint: audio upload -> ASR -> translation -> TTS.
@app.post("/translate/speech")
async def translate_speech(
    request: Request,
    audio: UploadFile = File(...),  # Multipart uploaded file.
    source_language: str = Form(...),  # Source language string from form field.
    target_language: str = Form(...),  # Target language string from form field.
    _: None = Depends(_require_api_key),  # Enforce API key dependency when configured.
):
    request_started = time.perf_counter()
    request_id = uuid.uuid4().hex[:12]
    _enforce_rate_limit(request)  # Apply request rate limiting.
    _cleanup_expired_audio_files()  # Opportunistic cleanup on each request.

    source_language_name = _canonical_language_name(source_language)
    target_language_name = _canonical_language_name(target_language)
    src_lang_code = LANGUAGE_TO_CODE[source_language_name]
    tgt_lang_code = LANGUAGE_TO_CODE[target_language_name]
    suffix = _validate_audio_upload(audio)  # Validate file extension/content-type.

    temp_audio_path: str | None = None  # Will hold temp file path for ASR processing.

    try:
        bytes_written = 0  # Track size to enforce upload limit.
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
            temp_audio_path = temp_audio.name
            while True:
                chunk = await audio.read(UPLOAD_CHUNK_BYTES)  # Read next chunk from uploaded file stream.
                if not chunk:
                    break  # EOF reached.
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Audio file exceeds max size of {MAX_UPLOAD_BYTES} bytes",
                    )
                temp_audio.write(chunk)  # Write chunk to disk-backed temp file.

        if bytes_written == 0:
            raise HTTPException(status_code=400, detail="Uploaded audio cannot be empty")

        translation_service, asr_service = get_services()  # Get model services.
        try:
            transcribe_with_stats = getattr(asr_service, "transcribe_with_stats", None)
            if callable(transcribe_with_stats):
                transcribed_text, asr_stats = transcribe_with_stats(temp_audio_path, source_language_name)
            else:
                asr_started = time.perf_counter()
                transcribed_text = asr_service.transcribe(temp_audio_path, source_language_name)  # Speech -> source text.
                asr_stats = {
                    "route": "unknown",
                    "model_id": "unknown",
                    "latency_ms": round((time.perf_counter() - asr_started) * 1000, 2),
                    "output_chars": len(transcribed_text),
                }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        translate_with_stats = getattr(translation_service, "translate_text_with_stats", None)
        if callable(translate_with_stats):
            translated_text, translation_stats = translate_with_stats(
                transcribed_text,
                src_lang_code,
                tgt_lang_code,
            )
        else:
            translation_started = time.perf_counter()
            translated_text = translation_service.translate_text(
                transcribed_text,
                src_lang_code,
                tgt_lang_code,
            )  # Source text -> target text.
            translation_stats = {
                "route": "unknown",
                "used_fallback": False,
                "model_ids": [],
                "total_latency_ms": round((time.perf_counter() - translation_started) * 1000, 2),
            }

        audio_url = None
        tts_stats: dict[str, Any] = {
            "enabled": True,
            "provider": "gTTS",
            "latency_ms": None,
            "audio_generated": False,
        }
        tts_started = time.perf_counter()
        tts_path = tts_generate(translated_text, target_language_name)  # Target text -> spoken audio.
        tts_stats["latency_ms"] = round((time.perf_counter() - tts_started) * 1000, 2)
        if tts_path:
            persist_started = time.perf_counter()
            audio_url = _persist_audio_file(tts_path)  # Persist and expose audio URL.
            tts_stats["persist_ms"] = round((time.perf_counter() - persist_started) * 1000, 2)
            tts_stats["audio_generated"] = True

        total_latency_ms = round((time.perf_counter() - request_started) * 1000, 2)
        _log_metrics(
            "translate_speech",
            {
                "request_id": request_id,
                "client_ip": _client_ip(request),
                "source_language": source_language_name,
                "target_language": target_language_name,
                "source_code": src_lang_code,
                "target_code": tgt_lang_code,
                "upload_bytes": bytes_written,
                "audio_suffix": suffix,
                "transcribed_chars": len(transcribed_text),
                "translated_chars": len(translated_text),
                "asr": asr_stats,
                "translation": translation_stats,
                "tts": tts_stats,
                "total_latency_ms": total_latency_ms,
            },
        )

        return {
            "request_id": request_id,
            "transcribed_text": transcribed_text,
            "translated_text": translated_text,
            "audio_url": audio_url,
        }
    finally:
        await audio.close()  # Always close uploaded file handle.
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)  # Always cleanup temp upload file from disk.


# Serve generated mp3 files by filename.
@app.get("/audio/{filename}")
def get_audio(filename: str):
    _cleanup_expired_audio_files()  # Cleanup old files before serving.
    path = _safe_audio_path(filename)  # Validate path to avoid traversal.
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg")
