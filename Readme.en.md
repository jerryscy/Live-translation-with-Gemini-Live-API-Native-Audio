# 🎙️ Real-Time Audio Translation · Gemini Live API

[![zh](https://img.shields.io/badge/lang-中文-red.svg)](./Readme.md)
[![en](https://img.shields.io/badge/lang-English-blue.svg)](./Readme.en.md)

> A **one-way** real-time speech translation app built on the **Gemini Live API** (native-audio model). The browser captures microphone audio → the backend (optionally denoises it and) relays it to Gemini → and the **source transcript**, **translated transcript**, and **translated audio** stream back to the browser in real time. Supports **70+ languages**, **mid-session language switching**, an optional **DeepFilterNet2 denoiser**, and **live connection status indicators**.

---

## 📑 Table of Contents

- [✨ Features](#-features)
- [🧭 How It Works](#-how-it-works)
- [🏗️ Architecture](#️-architecture)
- [✅ Prerequisites](#-prerequisites)
- [⚡ Quick Start](#-quick-start)
- [🔐 Configuration & Authentication](#-configuration--authentication)
- [🚀 Running & Usage](#-running--usage)
- [📦 Data Contract](#-data-contract)
- [🧠 Key Live API Configuration](#-key-live-api-configuration)
- [🛠️ Troubleshooting](#️-troubleshooting)

---

## ✨ Features

| | Feature | Description |
|---|---|---|
| 🎤 | **Real-time audio streaming** | MediaStream API + AudioWorklet capture mic audio at 16 kHz mono PCM |
| ➡️ | **One-way translation** | Source language → target language only (e.g. `cmn-CN` → `en-US`) |
| 🌍 | **70+ languages** | GA + Preview Chirp 3 HD language pools, selectable in the UI |
| 🚀 | **Native-audio model** | Powered by `gemini-live-2.5-flash-native-audio` for low-latency simultaneous interpretation |
| 🗣️ | **Translated speech playback** | 24 kHz 16-bit PCM streamed to the browser (`puck` voice), toggleable |
| 🧹 | **Optional DeepFilterNet2 denoiser** | Real-time noise suppression sidecar you can toggle on/off for A/B comparison (off by default) |
| 🎧 | **Browser echo/noise/gain control** | `echoCancellation`, `noiseSuppression`, `autoGainControl` on the mic reduce feedback and background noise |
| 🎭 | **Affective dialog** | `enable_affective_dialog` makes the translated voice mirror the speaker's emotion |
| ⏱️ | **Server-side VAD** | Automatic voice-activity detection with tuned start/end sensitivity |
| 🚦 | **No mid-turn interruption** | `activity_handling = NO_INTERRUPTION` — new speech won't truncate an in-progress translation |
| 🧠 | **Context-window compression** | Sliding window (8192 tokens) sustains long sessions |
| 🔌 | **Live connection indicator** | Shows the Backend ↔ Live API session state |
| ⏸️ | **Instant resume on Stop/Start** | Stop pauses audio but keeps the session alive, so Start resumes instantly (idle sessions auto-close after a timeout) |
| ⚙️ | **Change languages mid-session** | Update languages and the server transparently reconnects the Live API |
| 🎨 | **Zero-build frontend** | Plain HTML / vanilla JS, no bundler required |

---

## 🧭 How It Works

```
🎙️ Microphone
   │  16 kHz mono PCM
   ▼
🌐 Browser (AudioWorklet)          ── 32-bit float → 16-bit PCM
   │                                   mic constraints: echoCancellation / noiseSuppression / autoGainControl
   │  WebSocket (binary audio chunks + JSON control messages)
   ▼
⚙️  FastAPI backend (main.py)       ── Two-way message router
   │     ├─ audio chunks → LiveAPIWorker.send_audio_data()
   │     └─ start/stop/toggles/language-switch → controls worker state
   ▼
🧹 DeepFilterNet2 sidecar (optional) ── denoises audio when the toggle is ON (port 8600)
   ▼
🤖 LiveAPIWorker (liveapiworker.py) ── Owns the Live API session lifecycle
   ▼
🧠 Gemini Live API                  ── Source STT + one-way translation + speech synthesis
   │  WebSocket return stream
   ▼
🌐 Browser (index.html)             ── Renders source/target text + plays 24 kHz audio
```

**Step-by-step:**

1. **Audio capture** — The browser captures mic audio at 16 kHz mono, with `echoCancellation`, `noiseSuppression`, and `autoGainControl` enabled.
2. **Client-side processing** — `static/audio-processor.js` runs an `AudioWorklet` that converts 32-bit float samples to 16-bit PCM (little-endian).
3. **Session signaling** — Pressing **Start** sends `{action: "start_session"}` over the WebSocket; the worker opens (or resumes) the Gemini Live API session.
4. **Backend relay** — `main.py` receives binary audio and JSON control messages and forwards them to `LiveAPIWorker`. If the **DeepFilterNet2** toggle is on, audio is denoised by the sidecar first.
5. **AI translation** — A strict, **one-way** `system_instruction` turns the model into a translation conduit: translate source → target, stay silent on target-language / echoed audio.
6. **Streamed results** — The server pushes events back to the browser:
   - translated `audio` (24 kHz PCM binary)
   - `data` records (incremental source transcript / translation — see [Data Contract](#-data-contract))
   - `live_api_status` (connection state changes)
7. **Display & playback** — The frontend accumulates the text deltas into chat bubbles and plays the translated audio.

---

## 🏗️ Architecture

This app runs as **two processes** because of a native dependency conflict:

| Process | Interpreter | Why | Port |
|---|---|---|---|
| **Main app** (`main.py`) | Python 3.10+ (`.venv-app`) | Latest `google-genai` needs Python ≥ 3.10 | `8000` |
| **Denoiser sidecar** (`denoiser_service.py`) | Python 3.8–3.11 (`.venv`) | DeepFilterNet's native lib builds only for CPython 3.8–3.11 and needs numpy < 2 | `8600` |

| Layer | Stack | Key files |
|---|---|---|
| **Frontend** | HTML · vanilla JS · Web Audio API (`AudioWorklet`) | `static/index.html`, `static/audio-processor.js` |
| **Backend** | Python · FastAPI · WebSockets · `google-genai` | `main.py`, `liveapiworker.py` |
| **Denoiser** | Python · DeepFilterNet2 | `denoiser_service.py`, `denoiser_client.py`, `denoiser.py` |
| **AI model** | Gemini Live API (Vertex AI) | `gemini-live-2.5-flash-native-audio` |

The main app **auto-starts the denoiser sidecar** and streams audio to it **only when the toggle is ON** (zero overhead when off).

---

## ✅ Prerequisites

- **Python 3.10+** for the main app; **Python 3.8–3.11** for the denoiser sidecar
- **Google Cloud SDK** (`gcloud`) installed, on `PATH`, and logged in
- **A GCP project with the Vertex AI API enabled**
- **A modern browser with microphone support** (Chrome / Edge recommended)

---

## ⚡ Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/jerryscy/Live-translation-with-Gemini-Live-API-Native-Audio.git
cd Live-translation-with-Gemini-Live-API-Native-Audio

# 2. Create the two virtual environments
#    Main app (Python 3.10+)
python3 -m venv .venv-app
./.venv-app/bin/pip install --index-url https://pypi.org/simple -r requirements.txt

#    Denoiser sidecar (Python 3.8–3.11)
python3 -m venv .venv
./.venv/bin/pip install --index-url https://pypi.org/simple -r requirements-denoiser.txt
```

> 💡 The `--index-url https://pypi.org/simple` override matters if a global `pip.conf` points pip at a private registry.

---

## 🔐 Configuration & Authentication

### 1. Create a `.env` file

```env
GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
GOOGLE_CLOUD_LOCATION="us-central1"

# Model + default languages
LIVE_API_MODEL="gemini-live-2.5-flash-native-audio"
DEFAULT_SOURCE_LANG="Mandarin Chinese (China)"
DEFAULT_SOURCE_LANG_CODE="cmn-CN"
DEFAULT_TARGET_LANG="English (United States)"
DEFAULT_TARGET_LANG_CODE="en-US"

# Behavior
IDLE_CLOSE_SECONDS="30"      # close a paused session after this many idle seconds
DENOISER_MODEL="DeepFilterNet2"
DENOISER_DEFAULT_ON="false"  # denoiser starts OFF
DEBUG_LIVE_API="false"       # set true to log raw Live API transcription timing
```

> 💡 `.env` is git-ignored, so it won't be committed.

### 2. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

Make sure the **`gcloud` CLI is installed and on your `PATH`** — the app uses Application Default Credentials.

---

## 🚀 Running & Usage

Start everything with the launcher (it starts the denoiser sidecar, then the app):

```bash
./run.sh
```

Or run the app directly — it **auto-starts the denoiser sidecar** for you:

```bash
./.venv-app/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Then open 👉 **<http://127.0.0.1:8000>** in Chrome/Edge.

| Step | Action |
|---|---|
| ① | (Optional) Pick **Input / Output** languages (defaults `cmn-CN` → `en-US`) |
| ② | Click **▶ Start** and allow microphone access |
| ③ | **Left** shows the source transcript (type 1); **right** shows the translation (type 2) |
| ④ | The **Raw messages** panel shows the exact `data:{...}` records |
| ⑤ | Toggle **Play audio** to control translated-speech playback |
| ⑥ | Toggle **DeepFilterNet2** to denoise the mic in real time (A/B) |
| ⑦ | Click **Stop** to pause. The session stays alive so the next **Start** resumes instantly |

> Free a stuck port: `for p in 8000 8600; do kill -9 $(lsof -tiTCP:$p) 2>/dev/null; done`

---

## 📦 Data Contract

Results come back on the WebSocket as a text frame:

```json
{ "kind": "data", "data": { "uid": "...", "seq": 1, "type": 1, "delta": "…", "finished": false } }
```

| Field | Meaning |
|---|---|
| `uid` | Client session id (new when a browser tab connects) |
| `seq` | Turn number; increments on each `turnComplete`, accumulates across Stop/Start |
| `type` | `1` = input transcription (source), `2` = translation (output) |
| `delta` | The **new** text chunk for this record |
| `finished` | `false` while the turn streams; `true` when the Live API reports `turnComplete` |

**Wire vs. display:** to avoid re-sending the whole string on every token, the backend sends only the **`delta`** (new text). The frontend **accumulates** deltas per `(seq, type)` into the full `message` shown in the chat and the raw panel:

```
{ "uid": ..., "seq": N, "type": T, "message": <accumulated text>, "finished": bool }
```

Same `seq` is shared by a turn's input (type 1) and translation (type 2). A `finished:true` record with empty `delta` is the finalize marker.

---

## 🧠 Key Live API Configuration

The `LiveConnectConfig` in `liveapiworker.py` is tuned for **real-time interpretation**:

| Setting | Value | Purpose |
|---|---|---|
| `response_modalities` | `["AUDIO"]` | Model speaks; text arrives via the transcription fields |
| `input_audio_transcription` | Source BCP-47 | Server-side STT for the source audio |
| `output_audio_transcription` | Target BCP-47 | Server-side STT for the model's spoken translation |
| `proactivity.proactive_audio` | `True` | Model starts speaking as soon as it has enough context |
| `realtime_input_config.automatic_activity_detection` | Server-side VAD | `start = LOW` (robust to noise/feedback), `end = HIGH` (low latency), `prefix = 30 ms`, `silence = 0 ms` |
| `realtime_input_config.activity_handling` | `NO_INTERRUPTION` | New speech does **not** truncate an in-progress translation |
| `enable_affective_dialog` | `True` | Mirrors the speaker's emotion in the translated voice |
| `speech_config.voice_name` | `puck` | Built-in Live API voice |
| `context_window_compression` | Sliding window of 8192 tokens | Prevents long sessions from being cut off by audio-token bloat |
| `system_instruction` | Strict **one-way** "translation conduit" prompt | Translate source → target only; stay silent on target/echoed audio; anti-injection |

> Changing languages calls `set_language()`, which rebuilds the config and reconnects the Live API gracefully — no restart required.

### Stop / Start behavior

Pressing **Stop** pauses the audio but **keeps the Live API session open**, so **Start** resumes instantly and reliably (no reconnect). If you stay stopped longer than `IDLE_CLOSE_SECONDS` (default 30 s), the session closes to avoid holding a billable session open; the next Start reconnects.

---

## 🛠️ Troubleshooting

<details>
<summary><strong>🔑 Authentication errors</strong></summary>

- Run `gcloud auth application-default login`
- Verify `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` in `.env`
- Confirm the GCP project has **Vertex AI API** enabled and the account holds the required IAM roles

</details>

<details>
<summary><strong>🎤 Microphone not working</strong></summary>

- Grant the browser microphone permission and check OS-level mic privacy settings
- Confirm the default input device at `chrome://settings/content/microphone`
- `AudioWorklet` requires **HTTPS or localhost**

</details>

<details>
<summary><strong>🧹 Denoiser shows as unavailable</strong></summary>

- The `.venv` (Python 3.8–3.11) with `requirements-denoiser.txt` must be installed
- If the sidecar can't start on port `8600`, the app still runs and audio passes through undenoised
- Check the backend logs for denoiser sidecar startup errors

</details>

<details>
<summary><strong>🤖 No output / Live API stays in Error / Connecting</strong></summary>

- Set `DEBUG_LIVE_API="true"` and look for `input_transcription` / `output_transcription` / `[run] Connection error` lines
- Confirm the selected BCP-47 language is supported by the Live API (Preview languages may have limited quota)
- Regional quota issues can trigger errors — try a different `GOOGLE_CLOUD_LOCATION`
- After a connection error the worker backs off ~3 s before the next Start

</details>

<details>
<summary><strong>🔇 No translated audio / self-interruption</strong></summary>

- Make sure **Play audio** is ON
- Use headphones, or rely on the browser `echoCancellation` (already enabled) so the model doesn't pick up its own output as input

</details>

<details>
<summary><strong>🔒 SSL certificate errors (often macOS system Python)</strong></summary>

If you see `SSL: CERTIFICATE_VERIFY_FAILED`:

```bash
pip install certifi
export SSL_CERT_FILE=$(python3 -m certifi)
```

On macOS, prefer the *Install Certificates.command* shipped with the official python.org installer.

</details>

---

<p align="center">
  Made with ❤️ using <a href="https://ai.google.dev/">Gemini Live API</a> · <a href="https://fastapi.tiangolo.com/">FastAPI</a>
</p>
