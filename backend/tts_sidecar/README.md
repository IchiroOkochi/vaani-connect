# Vaani Connect TTS Sidecar

This sidecar isolates Indic Parler-TTS from the main backend so the core
translation/ASR stack can keep its own dependency set.

## What it does

- Runs `ai4bharat/indic-parler-tts` in a separate FastAPI service
- Exposes `POST /tts` that returns `audio/wav`
- Can be called by the main backend when `VAANI_TTS_PROVIDER=parler_sidecar`

## Recommended setup

Use a separate virtual environment or container for this sidecar.

### Linux/macOS/WSL

```bash
cd /workspace/vaani-connect/backend/tts_sidecar
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip==24.0
pip install -r requirements.txt
export HF_TOKEN="your_huggingface_read_token"
uvicorn app:app --host 0.0.0.0 --port 8010
```

### Main backend env vars

Set these in the main backend environment:

```bash
export VAANI_TTS_PROVIDER=parler_sidecar
export VAANI_TTS_SIDECAR_URL=http://127.0.0.1:8010
```

Optional:

```bash
export VAANI_TTS_SIDECAR_TIMEOUT_SECONDS=120
```

### Sidecar env vars

- `HF_TOKEN` or `HUGGINGFACE_HUB_TOKEN`
- `PARLER_TTS_MODEL_ID` (default: `ai4bharat/indic-parler-tts`)
- `PARLER_TTS_DEVICE` (`auto`, `cpu`, or `cuda`)
- `PARLER_TTS_VOICE_DESCRIPTION` for a default speaking style prompt

## Health check

```bash
curl http://localhost:8010/health
```

## TTS request example

```bash
curl -X POST http://localhost:8010/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"नमस्ते, आप कैसे हैं?","target_language":"Hindi"}' \
  --output sample.wav
```
