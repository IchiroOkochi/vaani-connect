# Changelog

## 2026-03-14

- Moved `POST /translate/speech` onto FastAPI's synchronous worker path so ASR, translation, and TTS no longer run inside the async event loop.
- Made TTS best-effort for both translation endpoints. Requests now succeed even when `gTTS` fails, and TTS errors are logged in backend metrics instead of crashing the request.
- Loaded translation and lazy Indic ASR models in eval mode and added a lock around the lazy Indic ASR cache to avoid duplicate first-request model initialization.
