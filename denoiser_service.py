"""DeepFilterNet2 denoiser sidecar (run with the Python 3.9 .venv).

Exposes a local WebSocket that accepts 16 kHz int16 PCM chunks (binary frames)
and returns the denoised 16 kHz int16 PCM. Text frames are control messages,
e.g. {"cmd": "reset"} to clear streaming state at the start of a new utterance.

The main app (running the latest google-genai on Python 3.14) talks to this
sidecar via denoiser_client.DenoiserClient, so DeepFilterNet's native lib and
numpy<2 requirement stay isolated in this interpreter.

Run:
    ./.venv/bin/python denoiser_service.py
"""

import asyncio
import json
import os

import websockets
from dotenv import load_dotenv

from denoiser import DeepFilterDenoiser

load_dotenv(override=True)

HOST = os.getenv("DENOISER_HOST", "127.0.0.1")
PORT = int(os.getenv("DENOISER_PORT", "8600"))
MODEL = os.getenv("DENOISER_MODEL", "DeepFilterNet2")

# One model instance for the process. This is a single-user local tool, so a
# shared streaming state is fine; it is reset on each new connection / utterance.
denoiser = DeepFilterDenoiser(model_name=MODEL, enabled=True)


async def handler(websocket):
    print("[denoiser-service] client connected")
    denoiser.reset()
    loop = asyncio.get_event_loop()
    try:
        async for msg in websocket:
            if isinstance(msg, (bytes, bytearray)):
                # Offload CPU-heavy denoise to a thread so the WS loop stays free.
                out = await loop.run_in_executor(None, denoiser.process, bytes(msg))
                await websocket.send(out)
            else:
                try:
                    ctrl = json.loads(msg)
                except Exception:
                    continue
                if ctrl.get("cmd") == "reset":
                    denoiser.reset()
    except websockets.ConnectionClosed:
        pass
    finally:
        print("[denoiser-service] client disconnected")


async def main():
    print(f"[denoiser-service] loading {MODEL} ...")
    denoiser.load()
    print(f"[denoiser-service] listening on ws://{HOST}:{PORT}")
    async with websockets.serve(handler, HOST, PORT, max_size=None, ping_interval=None):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
