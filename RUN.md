# Running the Live Translation app

The app is a **single process** (Python >= 3.10) — a FastAPI/uvicorn server that
relays browser mic audio to the Gemini Live API and streams the source
transcript, translation, and translated audio back.

Noise handling is done in the browser via the mic constraints
(`echoCancellation`, `noiseSuppression`, `autoGainControl`) — there is no
server-side denoiser.

## 1. Authenticate to Google Cloud (required)
```bash
gcloud auth application-default login
```
Project/region come from `.env` (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`).

## 2. One-time environment setup
```bash
python3 -m venv .venv-app
./.venv-app/bin/pip install --index-url https://pypi.org/simple -r requirements.txt
```
> The `--index-url https://pypi.org/simple` override matters if a global
> `pip.conf` points pip at a private registry.

## 3. Start it
```bash
./run.sh
# or directly:
./.venv-app/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```
`HOST` and `PORT` are read from the environment (defaults `127.0.0.1:8000`).

> Free a stuck port: `kill -9 $(lsof -tiTCP:8000) 2>/dev/null`

## 4. Use it
Open http://127.0.0.1:8000 in Chrome/Edge:
- **Input / Output** dropdowns (Chirp 3 HD list; defaults cmn-CN → en-US).
- **▶ Start** → allow mic. Left = input transcription (type 1), right = translation (type 2).
- **Raw messages** panel shows the exact `data:{...}` records.
- **Play audio** toggle controls translated-speech playback.

## Data contract (WebSocket text frame `{"kind":"data","data":{...}}`)
```
uid      client session id (new when a browser tab connects)
seq      turn sequence; increments on each turnComplete; accumulates across
         pauses and Start/Stop for the life of the connection
type     1 = input transcription, 2 = translation
delta    the NEW text for this record (frontend accumulates into the full message)
finished false while turnComplete is false, true when it is true
```

## Stop / Start behaviour
Pressing **Stop** pauses the audio but keeps the Live API session open, so
pressing **Start** again resumes **instantly** (no reconnect). If you stay
stopped longer than `IDLE_CLOSE_SECONDS` (default 30s, in `.env`) the session
closes to avoid holding a billable session open; the next Start reconnects.

## Session resumption (survives the ~10 min native-audio limit)
Native-audio Live API sessions have a hard time limit. The app enables session
resumption: it stores the server's resumption handle and, when the session hits
its limit (or the server sends `GoAway`), it reconnects with that handle
automatically — translation continues with context preserved and **without**
requiring another Start press.

## Optional: Google OAuth login (local)
The app can require a Google sign-in (restricted to `@google.com`). It's **off**
unless `OAUTH_CLIENT_ID` + `OAUTH_CLIENT_SECRET` are set in `.env`. To test the
login flow locally, fill in the OAuth block in `.env` (see `.env.example`),
ensure `http://127.0.0.1:8000/auth` is a registered redirect URI on your OAuth
client, and set `OAUTH_REDIRECT_URI="http://127.0.0.1:8000/auth"`. Then visiting
`http://127.0.0.1:8000/` bounces you to Google before the app loads. Leave the
OAuth vars blank to run open (no login). See `DEPLOY.md` for the Cloud Run setup.

## Diagnostics
Set `DEBUG_LIVE_API=true` in `.env` to log raw Live API transcription timing
(and `[resume] ...` handle/reconnect events). `diagnose.py` streams a Mandarin
WAV through the real worker and prints event timing (needs ADC):
```bash
./.venv-app/bin/python diagnose.py /tmp/test_cmn.wav
```
