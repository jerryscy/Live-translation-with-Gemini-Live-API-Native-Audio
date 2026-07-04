"""WebSocket client for the DeepFilterNet2 denoiser sidecar.

DeepFilterNet needs a native lib (only built for CPython 3.8-3.11) and numpy<2,
which can't coexist with the latest google-genai (Python >=3.10, numpy 2). So
the denoiser runs in a separate Python 3.9 process (see denoiser_service.py) and
this client streams 16 kHz PCM chunks to it, receiving denoised 16 kHz PCM back.

Robustness:
  * If the sidecar is down, audio passes through unchanged (never dropped).
  * Reconnect attempts are throttled (no per-chunk spam) and the "unavailable"
    message is logged only once per outage.
  * When the sidecar comes back up, denoising resumes automatically.

Interface expected by the worker:
    .enabled           bool flag (toggled live from the UI)
    .available         whether the sidecar is currently reachable
    async process(pcm) -> denoised pcm  (passthrough when disabled/unavailable)
    set_enabled(bool)
"""

import asyncio
import json
import time

import websockets

RETRY_INTERVAL = 5.0  # seconds between reconnect attempts while the sidecar is down


class DenoiserClient:
    def __init__(self, url: str = "ws://127.0.0.1:8600", enabled: bool = True):
        self.url = url
        self.enabled = enabled
        self.available = False
        self._ws = None
        self._lock = asyncio.Lock()
        self._needs_reset = False
        self._last_attempt = 0.0
        self._reported_down = False

    async def _try_connect(self) -> bool:
        """Attempt a connection. Logs success once; failure once per outage."""
        try:
            self._ws = await websockets.connect(
                self.url, max_size=None, ping_interval=None
            )
            self.available = True
            self._needs_reset = True
            self._reported_down = False
            print(f"[denoiser-client] connected to sidecar {self.url}")
            return True
        except Exception as exc:
            self._ws = None
            self.available = False
            if not self._reported_down:
                print(
                    f"[denoiser-client] sidecar unavailable ({self.url}): {exc} "
                    f"— passing audio through; will retry every {RETRY_INTERVAL:.0f}s"
                )
                self._reported_down = True
            return False

    async def probe(self) -> bool:
        """Startup connectivity check (for /config reporting)."""
        self._last_attempt = time.monotonic()
        return await self._try_connect()

    def set_enabled(self, enabled: bool) -> None:
        if enabled and not self.enabled:
            self._needs_reset = True  # flush stale streaming state on re-enable
        self.enabled = enabled
        print(f"[denoiser-client] enabled = {enabled}")

    async def process(self, pcm: bytes) -> bytes:
        """Denoise one 16 kHz int16 PCM chunk via the sidecar.

        Returns the input unchanged when disabled or when the sidecar is
        unreachable (with throttled reconnection so there is no log spam).
        """
        if not self.enabled or not pcm:
            return pcm
        async with self._lock:
            if self._ws is None:
                now = time.monotonic()
                if now - self._last_attempt < RETRY_INTERVAL:
                    return pcm  # within backoff window — silent passthrough
                self._last_attempt = now
                if not await self._try_connect():
                    return pcm
            try:
                if self._needs_reset:
                    await self._ws.send(json.dumps({"cmd": "reset"}))
                    self._needs_reset = False
                await self._ws.send(pcm)          # binary chunk
                resp = await self._ws.recv()       # denoised chunk
                return bytes(resp) if isinstance(resp, (bytes, bytearray)) else pcm
            except Exception as exc:
                # Lost the sidecar mid-stream — drop to passthrough and let the
                # throttled reconnect logic pick it back up.
                self._ws = None
                self.available = False
                self._last_attempt = time.monotonic()
                if not self._reported_down:
                    print(f"[denoiser-client] sidecar connection lost: {exc} — passthrough")
                    self._reported_down = True
                return pcm

    async def aclose(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
