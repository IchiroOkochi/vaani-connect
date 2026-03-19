# Vaani Connect

This project has 2 parts:

- `bakcend/` → Python backend (speech + translation API)
- `Expo/` → Mobile/web frontend (Expo React Native app)

If you are brand new, follow this guide from top to bottom.

---

## Quick overview (what you will run)

You will usually run **2 terminals**:

1. **Backend terminal** (inside WSL if possible) on port `8000`
2. **Frontend terminal** (Expo) on port `8081` (default)

If you enable the optional Indic Parler-TTS sidecar, run a **third terminal** for `backend/tts_sidecar` on port `8010`.

The frontend calls backend routes like:

- `/health`
- `/translate/text`
- `/translate/speech`
- `/audio/{filename}`
- `/metrics/recent` (debug view of recent backend translation metrics)

---

## Recommended setup: backend in WSL (Windows users)

> If you are on Windows, this is the recommended path.

### 1) Install WSL (one-time)

In **PowerShell as Administrator**:

```powershell
wsl --install
```

Then reboot if prompted.

### 2) Open Ubuntu (WSL) and install Python 3.11

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

### 3) Go to the backend folder and create a Python 3.11 virtual environment

```bash
cd /workspace/vaani-connect/bakcend
python3.11 -m venv .venv
source .venv/bin/activate
python --version
```

You should see Python `3.11.x`.

### 4) Install backend dependencies

```bash
python -m pip install --upgrade pip==24.0
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install git+https://github.com/VarunGumma/IndicTransToolkit.git
pip install -r requirements.txt
python -m app.setup
```

### 5) Add your Hugging Face token

Create a **Read** token here: <https://huggingface.co/settings/tokens>

Then set it in your terminal:

```bash
export HF_TOKEN="your_token_here"
```

(Alternative name also supported: `HUGGINGFACE_HUB_TOKEN`.)

### 6) Start backend API

```bash
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Leave this running.

---

## If you do NOT have WSL

You can still run the backend on Linux/macOS/Windows (PowerShell).

### Linux/macOS

Use the same backend steps as above, but run them in your normal terminal (no WSL).

### Windows (without WSL)

1. Install **Python 3.11** from: <https://www.python.org/downloads/release/python-3110/>
2. Open PowerShell in `bakcend` folder.
3. Create and activate venv:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

4. Install dependencies:

```powershell
python -m pip install --upgrade pip==24.0
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install git+https://github.com/VarunGumma/IndicTransToolkit.git
pip install -r requirements.txt
python -m app.setup
```

5. Set token and run server:

```powershell
$env:HF_TOKEN="your_token_here"
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

---

## Frontend setup (`Expo/`)

Open a **second terminal**:

```bash
cd /workspace/vaani-connect/Expo
npm install
npm run start
```

Then choose Android/iOS/Web from Expo output.

---

## Basic run checklist

- Backend terminal shows: `Uvicorn running on http://0.0.0.0:8000`
- Frontend terminal shows Expo QR/dev server
- Backend health test works:

```bash
curl http://localhost:8000/health
```

---

## Helpful notes

- Folder name is intentionally `backend/` in this repository.
- Backend observability details (VAANI_METRICS logs + `/metrics/recent`) are documented in `bakcend/README.md`.
- Professional benchmark harness docs are in `bakcend/benchmark/README.md`.
- Optional Indic Parler-TTS sidecar docs are in `backend/tts_sidecar/README.md`.
- You can launch the recommended dev stack with one command instead of starting each service manually:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start-dev-stack.ps1
```

- That launcher starts the main backend in WSL, starts the Indic Parler-TTS sidecar in WSL when its virtual environment exists, and starts the Expo frontend in Windows with the default `web` target.
- To stop the whole stack:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\stop-dev-stack.ps1
```

- Use `-FrontendTarget start`, `-FrontendTarget android`, or `-FrontendTarget ios` if you want a different Expo mode than the default web launch.
- Project update history lives in `CHANGELOG.md`.
- You can keep `CHANGELOG.md` up to date automatically while you work:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start-changelog-agent.ps1
```

Stop it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\stop-changelog-agent.ps1
```

- In VS Code, run `Tasks: Run Task` and choose `Changelog Agent: Start`, `Changelog Agent: Start (Dry Run)`, or `Changelog Agent: Stop`.
- In VS Code, you can also use `Dev Stack: Start`, `Dev Stack: Start (Expo Menu)`, and `Dev Stack: Stop`.
- To start it automatically when you log in on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\install-changelog-agent-scheduled-task.ps1
```

Remove that auto-start task with:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\uninstall-changelog-agent-scheduled-task.ps1
```

- In VS Code, you can also use `Changelog Agent: Install Auto-Start`, `Changelog Agent: Install Auto-Start (Dry Run)`, and `Changelog Agent: Remove Auto-Start`.
- The watcher debounces file saves, ignores build/venv folders, and uses local `codex exec` to refresh only the root changelog based on current uncommitted changes.
- You can also run backend demo directly:

```bash
python -m app.main
```
