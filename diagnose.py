"""Headless diagnostic: stream a Mandarin WAV to the Live API and print the
timing/granularity of input vs. output transcription events.

Requires: gcloud application-default credentials.
Usage:
    ./.venv/bin/python diagnose.py [path/to/16k_mono.wav]

It reuses the real LiveAPIWorker so the behaviour matches the app exactly.
Set DEBUG_LIVE_API=true to also see raw server_content lines.
"""

import asyncio
import os
import sys
import time
import wave

os.environ.setdefault("DEBUG_LIVE_API", "true")

from liveapiworker import LiveAPIWorker

WAV = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test_cmn.wav"
CHUNK_MS = 20
T0 = time.time()
_acc = {}  # (seq,type) -> accumulated text


def ts() -> str:
    return f"+{time.time() - T0:6.2f}s"


async def consume(worker: LiveAPIWorker, stop: asyncio.Event):
    """Print every data-contract event as it is produced."""
    while not stop.is_set():
        try:
            ev = await asyncio.wait_for(worker.event_queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        if ev["type"] == "data":
            p = ev["payload"]
            key = (p["seq"], p["type"])
            _acc[key] = _acc.get(key, "") + p.get("delta", "")
            kind = "IN " if p["type"] == 1 else "OUT"
            print(f"{ts()} [{kind} seq{p['seq']} fin={p['finished']:d}] {_acc[key]!r}")
        worker.event_queue.task_done()


async def feed(worker: LiveAPIWorker):
    w = wave.open(WAV)
    rate = w.getframerate()
    assert rate == 16000, f"expected 16k, got {rate}"
    frames_per_chunk = int(rate * CHUNK_MS / 1000)
    print(f"{ts()} feeding {WAV} ({w.getnframes()/rate:.1f}s)")
    while True:
        data = w.readframes(frames_per_chunk)
        if not data:
            break
        await worker.send_audio_data(data)
        await asyncio.sleep(CHUNK_MS / 1000)
    # trailing silence to trigger end-of-speech VAD
    silence = b"\x00\x00" * frames_per_chunk
    for _ in range(100):  # ~2.0 s
        await worker.send_audio_data(silence)
        await asyncio.sleep(CHUNK_MS / 1000)
    print(f"{ts()} finished feeding audio")


async def main():
    worker = LiveAPIWorker(
        "Mandarin Chinese (China)", "English (United States)",
        source_language_code="cmn-CN", target_language_code="en-US",
    )
    run_task = asyncio.create_task(worker.run())
    stop = asyncio.Event()
    consume_task = asyncio.create_task(consume(worker, stop))

    worker.begin_client_session()
    await worker.start_session()
    await asyncio.sleep(1.0)  # let the session connect
    await feed(worker)
    await asyncio.sleep(15.0)  # wait for translation + turn_complete

    stop.set()
    await worker.stop_session()
    run_task.cancel()
    await asyncio.gather(run_task, consume_task, return_exceptions=True)
    print(f"{ts()} done")


if __name__ == "__main__":
    asyncio.run(main())
