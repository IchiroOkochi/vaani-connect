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

## API endpoints

- `GET /health`
- `POST /translate/text`
- `POST /translate/speech` (multipart with `audio`, `source_language`, `target_language`)
- `GET /audio/{filename}`

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
