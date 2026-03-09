# Backend Setup Guide (Beginner Friendly)

This backend provides:

- Speech recognition (ASR)
- Translation
- Text-to-speech (TTS)
- API endpoints used by the Expo frontend

If you are on Windows, use **WSL** for best compatibility.

---

## Backend files (quick map)

- `app/config.py` → loads Hugging Face token from environment
- `app/translation.py` → IndicTrans2 translation
- `app/asr.py` → Whisper + IndicWav2Vec transcription
- `app/tts.py` → gTTS audio generation
- `app/setup.py` → downloads required NLTK data
- `app/server.py` → FastAPI server
- `app/main.py` → startup/demo script

---

## Option A (Recommended): Windows + WSL

### 1) Install WSL (one-time)

In PowerShell (Admin):

```powershell
wsl --install
```

Restart if prompted.

### 2) Install Python 3.11 in WSL Ubuntu

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

### 3) Create virtual environment with Python 3.11

```bash
cd /workspace/vaani-connect/bakcend
python3.11 -m venv .venv
source .venv/bin/activate
python --version
```

Expected: `Python 3.11.x`

### 4) Install dependencies

```bash
python -m pip install --upgrade pip==24.0
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install git+https://github.com/VarunGumma/IndicTransToolkit.git
pip install -r requirements.txt
python -m app.setup
```

### 5) Add Hugging Face token

Create a read token: <https://huggingface.co/settings/tokens>

```bash
export HF_TOKEN="your_huggingface_read_token"
```

(You can also use `HUGGINGFACE_HUB_TOKEN`.)

### 6) Run backend API server

```bash
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

---

## Option B: No WSL

### Linux/macOS

Use the exact same commands as Option A in your normal terminal.

### Windows PowerShell (no WSL)

1. Install Python 3.11 from: <https://www.python.org/downloads/release/python-3110/>
2. Open PowerShell in `bakcend` folder.
3. Run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install --upgrade pip==24.0
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install git+https://github.com/VarunGumma/IndicTransToolkit.git
pip install -r requirements.txt
python -m app.setup
$env:HF_TOKEN="your_huggingface_read_token"
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

---

## Runtime hardening env vars

- `VAANI_API_KEY`  
  If set, `POST /translate/text` and `POST /translate/speech` require header `X-API-Key: <value>`.
- `VAANI_ALLOWED_ORIGINS`  
  Comma-separated CORS origins (default is local dev origins only).
- `VAANI_RATE_LIMIT_REQUESTS`  
  Max requests per client IP in the time window (default `30`).
- `VAANI_RATE_LIMIT_WINDOW_SECONDS`  
  Rate-limit window in seconds (default `60`).
- `VAANI_MAX_UPLOAD_BYTES`  
  Max upload size for speech translation (default `10485760`, i.e. 10 MB).
- `VAANI_AUDIO_TTL_SECONDS`  
  Auto-cleanup TTL for generated audio files (default `3600`).
- `VAANI_RECENT_METRICS_LIMIT`  
  Max number of in-memory metric events kept for `/metrics/recent` (default `100`).

---

## API endpoints

- `GET /health`
- `GET /languages`
- `GET /metrics/recent` (debug endpoint for recent backend metrics)
- `POST /translate/text`
- `POST /translate/speech` (multipart with `audio`, `source_language`, `target_language`)
- `GET /audio/{filename}`

---

## Observability and metrics

The backend emits structured metrics for translation requests.

### 1) Terminal metrics logs

When requests hit translation endpoints, backend logs include lines that start with:

```text
VAANI_METRICS {...}
```

To ensure these appear, run uvicorn with info-level logs:

```bash
uvicorn app.server:app --host 0.0.0.0 --port 8000 --log-level info
```

### 2) Read metrics via API

Use the debug endpoint to inspect recent metric events:

```bash
curl "http://localhost:8000/metrics/recent?limit=20"
```

If `VAANI_API_KEY` is enabled, include header:

```bash
curl -H "X-API-Key: your_key_here" "http://localhost:8000/metrics/recent?limit=20"
```

### What metrics include

- Request latency (`total_latency_ms`)
- Translation route/model IDs and per-stage timings
- ASR model path/latency for speech translation
- TTS latency and audio persistence timing
- Input/output size stats (chars/bytes)
- `request_id` is included in translation responses and in metrics events for correlation.

---

## Benchmark harness (CSV + report)

Use the built-in benchmark harness for presentation-ready metrics.

Files:

- `benchmark/run_api_benchmark.py`
- `benchmark/datasets/presentation_text_cases.csv`
- `benchmark/README.md`

Run from `bakcend/`:

```bash
python benchmark/run_api_benchmark.py \
  --base-url http://localhost:8000 \
  --dataset benchmark/datasets/presentation_text_cases.csv \
  --runs-per-case 5 \
  --concurrency 2 \
  --tag professional-demo
```

If API key auth is enabled:

```bash
python benchmark/run_api_benchmark.py --api-key your_key_here
```

Benchmark output is written to:

`benchmark/results/<timestamp>-<tag>/`

Key artifacts:

- `raw_requests.csv`
- `pair_summary.csv`
- `route_summary.csv`
- `error_summary.csv`
- `summary.json`
- `summary.md`

For larger runs, increase `VAANI_RECENT_METRICS_LIMIT` so all request IDs can join with backend metrics.

---

## Quick checks

When server is running, test health:

```bash
curl http://localhost:8000/health
```

Optional demo run:

```bash
python -m app.main
```

Run backend tests:

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```
