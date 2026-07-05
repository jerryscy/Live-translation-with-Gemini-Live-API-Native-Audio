#!/usr/bin/env bash
# Launch the real-time translation app (single process, Python >= 3.10).
set -euo pipefail
cd "$(dirname "$0")"

APP_PY="./.venv-app/bin/python"

if [ ! -x "$APP_PY" ]; then
  echo "Missing .venv-app. Create it and install deps:"
  echo "  python3 -m venv .venv-app"
  echo "  ./.venv-app/bin/pip install -r requirements.txt"
  exit 1
fi

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
echo "Starting app on http://${HOST}:${PORT}"
exec "$APP_PY" -m uvicorn main:app --host "${HOST}" --port "${PORT}"
