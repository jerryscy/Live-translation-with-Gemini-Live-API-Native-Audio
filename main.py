import os
import asyncio
import json
import socket
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from liveapiworker import LiveAPIWorker
from denoiser_client import DenoiserClient
from languages import languages_json, name_for_code

load_dotenv(override=True)  # .env wins over inherited env (e.g. GOOGLE_CLOUD_LOCATION=global)

# --- Configuration (all overridable via .env) ---
DEFAULT_SOURCE_LANG_CODE = os.getenv("DEFAULT_SOURCE_LANG_CODE", "cmn-CN")
DEFAULT_TARGET_LANG_CODE = os.getenv("DEFAULT_TARGET_LANG_CODE", "en-US")
DEFAULT_SOURCE_LANG = os.getenv("DEFAULT_SOURCE_LANG") or name_for_code(DEFAULT_SOURCE_LANG_CODE)
DEFAULT_TARGET_LANG = os.getenv("DEFAULT_TARGET_LANG") or name_for_code(DEFAULT_TARGET_LANG_CODE)

DENOISER_MODEL = os.getenv("DENOISER_MODEL", "DeepFilterNet2")
DENOISER_DEFAULT_ON = os.getenv("DENOISER_DEFAULT_ON", "true").lower() in ("1", "true", "yes", "on")
DENOISER_URL = os.getenv("DENOISER_URL", "ws://127.0.0.1:8600")
# Auto-start the denoiser sidecar (Python 3.9) as a subprocess so a plain
# `uvicorn main:app` works without needing run.sh. Set to false to manage it
# yourself (e.g. via run.sh).
AUTO_START_DENOISER = os.getenv("AUTO_START_DENOISER", "true").lower() in ("1", "true", "yes", "on")
APP_DIR = Path(__file__).resolve().parent
# Interpreter for the sidecar (the Python 3.9 venv with deepfilternet).
DENOISER_PYTHON = os.getenv("DENOISER_PYTHON", str(APP_DIR / ".venv" / "bin" / "python"))


liveapiworker: Optional[LiveAPIWorker] = None
denoiser: Optional[DenoiserClient] = None
_worker_task: Optional[asyncio.Task] = None
_denoiser_proc: Optional[subprocess.Popen] = None


def _port_is_open(url: str) -> bool:
    """Return True if something is already listening at the sidecar URL."""
    parsed = urlparse(url)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 8600
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def _denoiser_expected_available() -> bool:
    """True if the denoiser is connected or expected to be (sidecar spawned)."""
    if bool(getattr(denoiser, "available", False)):
        return True
    # We spawned it (still loading) — it will connect lazily when toggled on.
    return _denoiser_proc is not None and _denoiser_proc.poll() is None


def _maybe_spawn_denoiser() -> Optional[subprocess.Popen]:
    """Start the denoiser sidecar subprocess if it isn't already running."""
    if not AUTO_START_DENOISER:
        return None
    if _port_is_open(DENOISER_URL):
        print("[startup] Denoiser sidecar already running.")
        return None
    if not Path(DENOISER_PYTHON).exists():
        print(f"[startup] Denoiser interpreter not found at {DENOISER_PYTHON}; "
              "skipping auto-start (audio will pass through undenoised).")
        return None
    print(f"[startup] Launching denoiser sidecar: {DENOISER_PYTHON} denoiser_service.py")
    return subprocess.Popen(
        [DENOISER_PYTHON, "denoiser_service.py"],
        cwd=str(APP_DIR),
    )


def check_gcloud_auth() -> bool:
    """Check for gcloud application-default credentials (non-blocking).

    Returns True if ADC is present. If not, prints a clear instruction and
    returns False rather than launching an interactive login (which would
    hang the server startup). The UI still boots; the Live API session will
    error until the user authenticates.
    """
    try:
        subprocess.check_output(
            ["gcloud", "auth", "application-default", "print-access-token"],
            stderr=subprocess.STDOUT,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("=" * 70)
        print("  Google Cloud ADC not found. Translation will fail until you run:")
        print("      gcloud auth application-default login")
        print("=" * 70)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    global liveapiworker, denoiser, _worker_task, _denoiser_proc
    check_gcloud_auth()

    # Auto-start the DeepFilterNet denoiser sidecar (separate Python 3.9
    # process), then connect to it. If it can't be started/reached the app
    # still works — audio just isn't denoised and the UI shows it unavailable.
    _denoiser_proc = _maybe_spawn_denoiser()
    denoiser = DenoiserClient(url=DENOISER_URL, enabled=DENOISER_DEFAULT_ON)

    # Probe in the BACKGROUND so app startup is instant (the sidecar takes a few
    # seconds to load its model, and it's off by default anyway). The client
    # also connects lazily the moment the denoiser is toggled on.
    async def _probe_denoiser_bg():
        for _ in range(30):
            try:
                if await denoiser.probe():
                    return
            except Exception:
                pass
            await asyncio.sleep(1.0)
    asyncio.create_task(_probe_denoiser_bg())

    liveapiworker = LiveAPIWorker(
        DEFAULT_SOURCE_LANG,
        DEFAULT_TARGET_LANG,
        source_language_code=DEFAULT_SOURCE_LANG_CODE,
        target_language_code=DEFAULT_TARGET_LANG_CODE,
        denoiser=denoiser,
    )

    _worker_task = asyncio.create_task(liveapiworker.run(), name="live-api-worker")
    yield
    # Graceful shutdown: cancel the background worker task.
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        await asyncio.gather(_worker_task, return_exceptions=True)
    # Stop the denoiser sidecar if we started it.
    if _denoiser_proc is not None:
        print("[shutdown] Stopping denoiser sidecar...")
        _denoiser_proc.terminate()
        try:
            _denoiser_proc.wait(timeout=5)
        except Exception:
            _denoiser_proc.kill()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/config")
async def get_config():
    """Expose language list + defaults + denoiser state to the frontend."""
    return JSONResponse(
        {
            "languages": languages_json(),
            "default_source_code": DEFAULT_SOURCE_LANG_CODE,
            "default_target_code": DEFAULT_TARGET_LANG_CODE,
            "denoiser_available": _denoiser_expected_available(),
            "denoiser_enabled": bool(getattr(denoiser, "enabled", False)) and _denoiser_expected_available(),
            "denoiser_model": DENOISER_MODEL,
            "model": LiveAPIWorker.MODEL_ID,
        }
    )


async def _stream_events_to_client(websocket: WebSocket) -> None:
    """Forward events from the worker's event queue to the WebSocket client."""
    while True:
        event = await liveapiworker.event_queue.get()
        try:
            event_type = event["type"]

            if event_type == "audio":
                await websocket.send_bytes(event["data"])

            elif event_type == "data":
                # The uid/seq/type/message/finished data contract.
                await websocket.send_text(
                    json.dumps({"kind": "data", "data": event["payload"]})
                )

            elif event_type == "live_api_status":
                await websocket.send_text(
                    json.dumps({
                        "kind": "status",
                        "live_api_status": {
                            "connected": event.get("connected", False),
                            "state": event.get("state", "disconnected"),
                        },
                    })
                )

        except Exception as exc:
            print(f"[stream_events] Error sending to client: {exc}")
        finally:
            liveapiworker.event_queue.task_done()


@app.get("/")
async def get():
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # New browser connection = new client session (fresh uid, seq resets to 1).
    # seq then accumulates across turns and Start/Stop until the next connect.
    liveapiworker.begin_client_session()

    # Send the current Live API connection state immediately so the client
    # can render the status indicator without waiting for the next change.
    try:
        connected = bool(getattr(liveapiworker, "live_api_connected", False))
        await websocket.send_text(
            json.dumps({
                "kind": "status",
                "live_api_status": {
                    "connected": connected,
                    "state": "connected" if connected else "disconnected",
                },
            })
        )
    except Exception as exc:
        print(f"[websocket] Failed to send initial status: {exc}")

    stream_task = asyncio.create_task(
        _stream_events_to_client(websocket), name="ws-event-stream"
    )

    try:
        while True:
            data = await websocket.receive()

            if data.get("type") == "websocket.disconnect":
                print("Client disconnected")
                break

            if "bytes" in data:
                await liveapiworker.send_audio_data(data["bytes"])

            elif "text" in data:
                message = json.loads(data["text"])
                action = message.get("action")

                if action == "start_session":
                    await liveapiworker.start_session()
                elif action == "stop_session":
                    await liveapiworker.stop_session()
                elif action == "set_denoiser":
                    liveapiworker.set_denoiser_enabled(bool(message.get("enabled", True)))
                elif action == "set_audio_output":
                    liveapiworker.set_audio_output(bool(message.get("enabled", True)))
                elif "source_language" in message or "target_language" in message:
                    source = message.get("source_language", liveapiworker.source_language)
                    target = message.get("target_language", liveapiworker.target_language)
                    source_code = message.get(
                        "source_language_code", liveapiworker.source_language_code
                    )
                    target_code = message.get(
                        "target_language_code", liveapiworker.target_language_code
                    )
                    await liveapiworker.set_language(
                        source, target,
                        source_code=source_code,
                        target_code=target_code,
                    )

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as exc:
        print(f"[websocket] Unexpected error: {exc}")
    finally:
        stream_task.cancel()
        await asyncio.gather(stream_task, return_exceptions=True)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
