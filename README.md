# Vaani Connect

This repository has two main folders:

- `Expo/` → React Native frontend (Expo).
- `bakcend/` → Python backend services for ASR, translation, and TTS.

## 1) Backend setup (`bakcend/`)

### Prerequisites
- Python 3.10+
- (Optional but recommended) NVIDIA GPU with CUDA 11.8 for faster model inference

### Create and activate virtual environment
```bash
cd bakcend
python -m venv .venv
source .venv/bin/activate
```

### Install dependencies
Upgrade pip first (same version used in your Colab snippet):
```bash
python -m pip install --upgrade pip==24.0
```

Install PyTorch for CUDA 11.8 (GPU build):
```bash
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu118
```

Install remaining backend dependencies:
```bash
pip install -r requirements.txt
```

Download NLTK data required by IndicTransToolkit:
```bash
python -m app.setup
```

### Hugging Face token (for gated/private model access)
1. Create a **read token** at: https://huggingface.co/settings/tokens
2. Export it in your shell:
```bash
export HF_TOKEN="your_token_here"
```

You can also use:
```bash
export HUGGINGFACE_HUB_TOKEN="your_token_here"
```

### Run backend demo
```bash
python -m app.main
```

This initializes:
- IndicTrans2 models (`en↔indic`)
- Whisper ASR
- IndicWav2Vec ASR (lazy-loaded by language)
- gTTS for speech output

## 2) Frontend setup (`Expo/`)

```bash
cd Expo
npm install
npm run start
```

Then launch on Android/iOS/Web from the Expo CLI output.

## Notes
- The backend code was converted from Colab-style cells to standard Python modules.
- Colab-only imports like `google.colab.userdata` are replaced by environment-variable based token loading.
- The folder name is currently `bakcend/` (as in the existing repo).
