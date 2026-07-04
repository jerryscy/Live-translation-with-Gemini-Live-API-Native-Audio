#!/usr/bin/env bash
# Launch the DeepFilterNet2 denoiser sidecar (Python 3.9) and the main
# translation app (Python 3.14) together.
set -euo pipefail
cd "$(dirname "$0")"

DENOISER_PY="./.venv/bin/python"        # Python 3.9 env with deepfilternet
APP_PY="./.venv-app/bin/python"         # Python 3.14 env with latest google-genai

if [ ! -x "$DENOISER_PY" ]; then echo "Missing .venv (denoiser). See RUN.md"; exit 1; fi
if [ ! -x "$APP_PY" ]; then echo "Missing .venv-app (main app). See RUN.md"; exit 1; fi

# Start the denoiser sidecar in the background.
echo "Starting denoiser sidecar..."
"$DENOISER_PY" denoiser_service.py &
DENOISER_PID=$!

# Make sure we tear the sidecar down when the app exits.
cleanup() { echo "Stopping denoiser sidecar ($DENOISER_PID)"; kill "$DENOISER_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

# Give the sidecar a moment to load the model before the app probes it.
sleep 6

echo "Starting main app on http://127.0.0.1:8000"
"$APP_PY" -m uvicorn main:app --host 127.0.0.1 --port 8000
