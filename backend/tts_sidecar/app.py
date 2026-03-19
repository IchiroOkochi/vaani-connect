from __future__ import annotations

import io
import logging
import os
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from huggingface_hub import login
from parler_tts import ParlerTTSForConditionalGeneration
from pydantic import BaseModel
import soundfile as sf
import torch
from transformers import AutoTokenizer

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "ai4bharat/indic-parler-tts"
DEFAULT_VOICE_DESCRIPTION = (
    "A clear studio-quality speaker with natural pacing and expressive delivery. "
    "The voice is warm, articulate, and easy to understand."
)

app = FastAPI(title="Vaani Connect TTS Sidecar", version="1.0.0")

_model_lock = Lock()
_model = None
_prompt_tokenizer = None
_description_tokenizer = None
_model_load_error: str | None = None


class TTSRequest(BaseModel):
    text: str
    target_language: str | None = None
    voice_description: str | None = None


def _hf_token() -> str | None:
    return os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")


def _model_id() -> str:
    return os.getenv("PARLER_TTS_MODEL_ID", DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID


def _device() -> str:
    requested = os.getenv("PARLER_TTS_DEVICE", "auto").strip().lower()
    if requested in {"cpu", "cuda"}:
        if requested == "cuda" and not torch.cuda.is_available():
            logger.warning("PARLER_TTS_DEVICE=cuda requested but CUDA is unavailable. Falling back to CPU.")
            return "cpu"
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


def _voice_description(payload: TTSRequest) -> str:
    if payload.voice_description and payload.voice_description.strip():
        return payload.voice_description.strip()
    return os.getenv("PARLER_TTS_VOICE_DESCRIPTION", DEFAULT_VOICE_DESCRIPTION).strip() or DEFAULT_VOICE_DESCRIPTION


def _login_huggingface_if_needed() -> None:
    token = _hf_token()
    if not token:
        return
    login(token=token)


def _load_model_bundle():
    global _model
    global _prompt_tokenizer
    global _description_tokenizer
    global _model_load_error

    if _model is not None and _prompt_tokenizer is not None and _description_tokenizer is not None:
        return _model, _prompt_tokenizer, _description_tokenizer

    with _model_lock:
        if _model is not None and _prompt_tokenizer is not None and _description_tokenizer is not None:
            return _model, _prompt_tokenizer, _description_tokenizer
        if _model_load_error is not None:
            raise RuntimeError(_model_load_error)

        try:
            _login_huggingface_if_needed()
            device = _device()
            torch_dtype = torch.float16 if device == "cuda" else torch.float32

            model = ParlerTTSForConditionalGeneration.from_pretrained(
                _model_id(),
                torch_dtype=torch_dtype,
            ).to(device)
            model.eval()

            prompt_tokenizer = AutoTokenizer.from_pretrained(_model_id())
            description_tokenizer = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
        except Exception as exc:  # noqa: BLE001 - sidecar must report load failures cleanly.
            _model_load_error = f"Failed to initialize Parler TTS sidecar: {exc}"
            raise RuntimeError(_model_load_error) from exc

        _model = model
        _prompt_tokenizer = prompt_tokenizer
        _description_tokenizer = description_tokenizer
        return _model, _prompt_tokenizer, _description_tokenizer


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok" if _model_load_error is None else "degraded",
        "model_id": _model_id(),
        "device": _device(),
        "loaded": _model is not None,
        "load_error": _model_load_error,
    }


@app.post("/tts")
def generate_tts(payload: TTSRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        model, prompt_tokenizer, description_tokenizer = _load_model_bundle()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    device = _device()
    description = _voice_description(payload)

    description_inputs = description_tokenizer(description, return_tensors="pt")
    prompt_inputs = prompt_tokenizer(payload.text, return_tensors="pt")

    description_ids = description_inputs.input_ids.to(device)
    prompt_ids = prompt_inputs.input_ids.to(device)
    description_mask = description_inputs.get("attention_mask")
    prompt_mask = prompt_inputs.get("attention_mask")
    if description_mask is not None:
        description_mask = description_mask.to(device)
    if prompt_mask is not None:
        prompt_mask = prompt_mask.to(device)

    with torch.no_grad():
        generation = model.generate(
            input_ids=description_ids,
            attention_mask=description_mask,
            prompt_input_ids=prompt_ids,
            prompt_attention_mask=prompt_mask,
        )

    audio = generation.detach().cpu().float()
    if audio.ndim > 1:
        audio = audio.squeeze(0)
    if audio.ndim > 1:
        audio = audio[0]

    buffer = io.BytesIO()
    sf.write(buffer, audio.numpy(), model.config.sampling_rate, format="WAV")
    return Response(
        content=buffer.getvalue(),
        media_type="audio/wav",
        headers={
            "X-TTS-Provider": "indic_parler_sidecar",
            "X-TTS-Model-Id": _model_id(),
            "X-TTS-Target-Language": payload.target_language or "",
        },
    )
