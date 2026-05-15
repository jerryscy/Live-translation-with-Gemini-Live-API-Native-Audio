import asyncio
import json
import subprocess
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from liveapiworker import LiveAPIWorker

# --- Configuration ---
# Display names match the frontend dropdown (option text), and codes are
# BCP-47 codes that match the option `value` attribute.
DEFAULT_SOURCE_LANG = "English (United States)"
DEFAULT_SOURCE_LANG_CODE = "en-US"
DEFAULT_TARGET_LANG = "Chinese (Simplified, China)"
DEFAULT_TARGET_LANG_CODE = "cmn-Hans-CN"


liveapiworker: Optional[LiveAPIWorker] = None
_worker_task: Optional[asyncio.Task] = None


def check_gcloud_auth() -> None:
    """Ensure gcloud application-default credentials are available."""
    try:
        subprocess.check_output(
            ["gcloud", "auth", "application-default", "print-access-token"],
            stderr=subprocess.STDOUT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Attempting to authenticate with gcloud...")
        subprocess.run(["gcloud", "auth", "application-default", "login"])
        print("Authentication successful, you can now start the application.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    global liveapiworker, _worker_task
    check_gcloud_auth()
    liveapiworker = LiveAPIWorker(
        DEFAULT_SOURCE_LANG,
        DEFAULT_TARGET_LANG,
        source_language_code=DEFAULT_SOURCE_LANG_CODE,
        target_language_code=DEFAULT_TARGET_LANG_CODE,
    )

    _worker_task = asyncio.create_task(liveapiworker.run(), name="live-api-worker")
    yield
    # Graceful shutdown: cancel the background worker task.
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        await asyncio.gather(_worker_task, return_exceptions=True)


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


async def _stream_events_to_client(websocket: WebSocket) -> None:
    """Forward events from the worker's event queue to the WebSocket client.

    Blocks on the queue — no polling sleep required. Each event is dispatched
    as soon as the Live API produces it, giving minimal end-to-end latency.
    """
    while True:
        event = await liveapiworker.event_queue.get()
        try:
            event_type = event["type"]

            if event_type == "audio":
                await websocket.send_bytes(event["data"])

            elif event_type == "input_transcription":
                await websocket.send_text(
                    json.dumps({"input_transcription": event["text"]})
                )

            elif event_type == "output_transcription":
                await websocket.send_text(
                    json.dumps({"output_transcription": event["text"]})
                )

            elif event_type == "turn_complete":
                await websocket.send_text(json.dumps({"turn_complete": True}))

            elif event_type == "live_api_status":
                await websocket.send_text(
                    json.dumps({
                        "live_api_status": {
                            "connected": event.get("connected", False),
                            "state": event.get("state", "disconnected"),
                        }
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

    # Send the current Live API connection state immediately so the client
    # can render the status indicator without waiting for the next change.
    try:
        connected = bool(getattr(liveapiworker, "live_api_connected", False))
        await websocket.send_text(
            json.dumps({
                "live_api_status": {
                    "connected": connected,
                    "state": "connected" if connected else "disconnected",
                }
            })
        )
    except Exception as exc:
        print(f"[websocket] Failed to send initial status: {exc}")

    # Start the event-streaming task for this connection.
    stream_task = asyncio.create_task(
        _stream_events_to_client(websocket), name="ws-event-stream"
    )

    try:
        while True:
            data = await websocket.receive()

            # The raw receive() dict carries a "type" field.
            # "websocket.disconnect" means the client closed — stop the loop.
            if data.get("type") == "websocket.disconnect":
                print("Client disconnected")
                break

            if "bytes" in data:
                await liveapiworker.send_audio_data(data["bytes"])

            elif "text" in data:
                message = json.loads(data["text"])
                if message.get("action") == "start_session":
                    # Start Recording pressed — open a new Live API session.
                    await liveapiworker.start_session()
                elif message.get("action") == "stop_session":
                    # Stop Recording pressed — tear down the current session.
                    # run() waits for the next start_session signal before reconnecting.
                    await liveapiworker.stop_session()
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
