# Change Log

Use this file to record what changed in the project over time.

## Entry Template

Copy this block for each update:

```md
## YYYY-MM-DD - Short Title

- Area: Backend | Expo | Full Stack | Docs | DevOps
- Summary: What changed and why
- Files: `path/to/file1`, `path/to/file2`
- Commands Run: `npm test`, `uvicorn ...` (if any)
- Validation: What you tested and the result
- Notes/Risks: Anything incomplete, risky, or important
- Next Step: What should happen next
```

---

## 2026-03-10 - Added Change Log

- Area: Docs
- Summary: Created a dedicated update log so project progress can be tracked consistently.
- Files: `CHANGELOG.md`
- Commands Run: None
- Validation: File added to repository root and ready for future updates.
- Notes/Risks: None
- Next Step: Add a new entry each time you make a meaningful project update.


## 2026-03-14

- Moved `POST /translate/speech` onto FastAPI's synchronous worker path so ASR, translation, and TTS no longer run inside the async event loop.
- Made TTS best-effort for both translation endpoints. Requests now succeed even when `gTTS` fails, and TTS errors are logged in backend metrics instead of crashing the request.
- Loaded translation and lazy Indic ASR models in eval mode and added a lock around the lazy Indic ASR cache to avoid duplicate first-request model initialization.

## 2026-03-18 - Added Indic Parler TTS Sidecar Architecture

- Area: Backend
- Summary: Added an isolated `tts_sidecar` service for Indic Parler-TTS so the main backend can keep its existing translation/ASR dependency stack while optionally calling Parler over HTTP.
- Files: `backend/app/tts.py`, `backend/app/server.py`, `backend/app/main.py`, `backend/tests/test_server_hardening.py`, `backend/tests/test_tts_sidecar_client.py`, `backend/tts_sidecar/app.py`, `backend/tts_sidecar/requirements.txt`, `backend/tts_sidecar/README.md`, `backend/README.md`, `README.md`, `CHANGELOG.md`
- Commands Run: None
- Validation: Added backend tests for the sidecar client path and for serving `.wav` generated audio alongside existing TTS behavior.
- Notes/Risks: Automated backend test execution was not completed in this shell, so the new sidecar path still needs a real environment smoke test after dependencies are installed.
- Next Step: Install the sidecar dependencies in a separate environment, start it on port `8010`, and verify end-to-end translation plus audio playback with `VAANI_TTS_PROVIDER=parler_sidecar`.

## 2026-03-18 - Added One-Command Dev Stack Launcher

- Area: DevOps
- Summary: Added PowerShell launcher scripts to start and stop the recommended dev stack in one command, with the Python services running in WSL and Expo running in Windows.
- Files: `tools/start-dev-stack.ps1`, `tools/stop-dev-stack.ps1`, `.vscode/tasks.json`, `README.md`, `CHANGELOG.md`
- Commands Run: None
- Validation: Added PID and log tracking for each service, plus matching VS Code tasks for start/stop workflows.
- Notes/Risks: The launcher expects the backend WSL virtual environment at `backend/.venv` and uses the sidecar automatically only when `backend/tts_sidecar/.venv` exists.
- Next Step: Run the new launcher, confirm the stack comes up end-to-end, and inspect `.git/dev-stack/` logs if any service fails during boot.
