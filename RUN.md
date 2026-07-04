# Running the Live Translation app

This app runs as **two processes** because of a hard dependency conflict on this
machine:

| Process | Interpreter | Why |
|---|---|---|
| **Main app** (`main.py`) | Python 3.14 (`.venv-app`) | latest `google-genai` (2.10.0) needs Python ≥3.10; gives proper word-by-word streaming + language hints |
| **Denoiser sidecar** (`denoiser_service.py`) | Python 3.9 (`.venv`) | DeepFilterNet's native lib only builds for CPython 3.8–3.11 and needs numpy<2 |

The main app streams mic audio to the sidecar over a local WebSocket **only when
the DeepFilterNet2 toggle is ON** (zero overhead when off).

## 1. Authenticate to Google Cloud (required)
```bash
gcloud auth application-default login
```
Project/region come from `.env` (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`).

## 2. One-time environment setup
Both venvs already exist. To rebuild them (note the PyPI index override — a global
pip.conf otherwise points pip at a private registry):

```bash
# Main app (Python 3.14)
/opt/homebrew/bin/python3.14 -m venv .venv-app
./.venv-app/bin/pip install --index-url https://pypi.org/simple -r requirements.txt

# Denoiser sidecar (Python 3.9)
/usr/bin/python3 -m venv .venv
./.venv/bin/pip install --index-url https://pypi.org/simple -r requirements-denoiser.txt
```

## 3. Start everything
Just start the app — it **auto-starts the denoiser sidecar** for you:
```bash
./.venv-app/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```
The app spawns `denoiser_service.py` on the Python 3.9 venv, waits for the model
to load, and stops it on exit. If the sidecar can't start, the app still runs and
audio simply passes through undenoised (the UI shows the denoiser as unavailable).

Prefer to manage them yourself? Set `AUTO_START_DENOISER=false` in `.env` and run:
```bash
./run.sh
# or, in two terminals:
./.venv/bin/python denoiser_service.py
./.venv-app/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

> Tip: if a previous run left something on port 8000/8600, free it with:
> `for p in 8000 8600; do kill -9 $(lsof -tiTCP:$p) 2>/dev/null; done`

## 4. Use it
Open http://127.0.0.1:8000 in Chrome/Edge:
- **Input / Output** dropdowns (Chirp 3 HD list; defaults cmn-CN → en-US).
- **▶ Start** → allow mic. Left = input transcription (type 1), right = translation (type 2).
- **Raw messages** panel shows the exact `data:{...}` records.
- **Play audio** toggle controls translated-speech playback.
- **DeepFilterNet2** toggle turns denoising on/off in real time for A/B comparison.

## Data contract (WebSocket text frame `{"kind":"data","data":{...}}`)
```
uid      client session id (new when a browser tab connects)
seq      turn sequence; increments on each turnComplete; accumulates across
         pauses and Start/Stop for the life of the connection
type     1 = input transcription, 2 = translation
message  accumulated text for the current turn
finished false while turnComplete is false, true when it is true
```

## Stop / Start behaviour
Pressing **Stop** pauses the audio but keeps the Live API session open, so
pressing **Start** again resumes **instantly and reliably** (no reconnect). If
you stay stopped longer than `IDLE_CLOSE_SECONDS` (default 30s, in `.env`) the
session closes to avoid holding a billable session open; the next Start
reconnects. This avoids the intermittent "no translation after restart" that a
fresh reconnect on every Stop→Start could cause.

## Diagnostics
Set `DEBUG_LIVE_API=true` in `.env` to log raw Live API transcription timing.
`diagnose.py` streams a Mandarin WAV through the real worker and prints event
timing (needs ADC):
```bash
./.venv-app/bin/python diagnose.py /tmp/test_cmn.wav
```
