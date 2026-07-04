"""Reproduce Start -> Stop -> Start behaviour."""
import asyncio, os, time, wave
os.environ.setdefault("DEBUG_LIVE_API", "false")
from liveapiworker import LiveAPIWorker

CHUNK_MS = 20
T0 = time.time()
def ts(): return f"+{time.time()-T0:6.2f}s"

async def consume(worker, stop):
    while not stop.is_set():
        try:
            ev = await asyncio.wait_for(worker.event_queue.get(), timeout=0.3)
        except asyncio.TimeoutError:
            continue
        if ev["type"] == "data":
            p = ev["payload"]
            tag = "IN " if p["type"]==1 else "OUT"
            print(f"{ts()} [{tag} seq{p['seq']} fin={p['finished']:d}] delta={p['delta']!r}")
        elif ev["type"] == "live_api_status":
            print(f"{ts()} [status] {ev.get('state')}")
        worker.event_queue.task_done()

async def feed(worker, path):
    w = wave.open(path); fpc = int(16000*CHUNK_MS/1000)
    while True:
        d = w.readframes(fpc)
        if not d: break
        await worker.send_audio_data(d); await asyncio.sleep(CHUNK_MS/1000)
    sil = b"\x00\x00"*fpc
    for _ in range(90):
        await worker.send_audio_data(sil); await asyncio.sleep(CHUNK_MS/1000)

async def main():
    worker = LiveAPIWorker("Mandarin Chinese (China)","English (United States)",
        source_language_code="cmn-CN", target_language_code="en-US", denoiser=None)
    run_task = asyncio.create_task(worker.run())
    stop = asyncio.Event(); ct = asyncio.create_task(consume(worker, stop))
    worker.begin_client_session()

    print(f"{ts()} ===== START #1 =====")
    await worker.start_session(); await asyncio.sleep(1.0)
    await feed(worker, "/tmp/c1.wav"); await asyncio.sleep(3.0)

    print(f"{ts()} ===== STOP =====")
    await worker.stop_session(); await asyncio.sleep(2.0)

    print(f"{ts()} ===== START #2 =====")
    await worker.start_session(); await asyncio.sleep(1.5)
    await feed(worker, "/tmp/c2.wav"); await asyncio.sleep(4.0)

    stop.set(); await worker.stop_session(); run_task.cancel()
    await asyncio.gather(run_task, ct, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
