# Backend (Python)

Converted from Google Colab notebook cells into regular Python modules:

- `app/config.py` → Hugging Face token loading/login via env vars
- `app/translation.py` → IndicTrans2 translation service
- `app/asr.py` → Whisper + IndicWav2Vec transcription service
- `app/tts.py` → gTTS audio generation
- `app/setup.py` → NLTK punkt download helper
- `app/main.py` → simple startup/demo entrypoint

## Quick start
```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip==24.0
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
python -m app.setup
export HF_TOKEN="your_huggingface_read_token"
python -m app.main
```


## Run API server
```bash
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Endpoints:
- `GET /health`
- `POST /translate/text`
- `POST /translate/speech` (multipart form with `audio`, `source_language`, `target_language`)
- `GET /audio/{filename}`
