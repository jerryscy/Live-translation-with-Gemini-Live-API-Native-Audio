"""Measure Start/Stop/Start reliability: N stop->start cycles, output per cycle."""
import asyncio, os, time, wave
os.environ.setdefault("DEBUG_LIVE_API", "false")
from liveapiworker import LiveAPIWorker

CLIPS = [f"/tmp/c{i}.wav" for i in range(1, 6)]
CHUNK_MS = 20
got_output = {}  # seq -> bool

async def consume(worker, stop):
    while not stop.is_set():
        try:
            ev = await asyncio.wait_for(worker.event_queue.get(), timeout=0.3)
        except asyncio.TimeoutError:
            continue
        if ev["type"] == "data" and ev["payload"]["type"] == 2:
            got_output[ev["payload"]["seq"]] = True
        worker.event_queue.task_done()

async def feed(worker, path):
    w = wave.open(path); fpc = int(16000*CHUNK_MS/1000)
    while True:
        d = w.readframes(fpc)
        if not d: break
        await worker.send_audio_data(d); await asyncio.sleep(CHUNK_MS/1000)
    sil = b"\x00\x00"*fpc
    for _ in range(80):
        await worker.send_audio_data(sil); await asyncio.sleep(CHUNK_MS/1000)

async def main():
    worker = LiveAPIWorker("Mandarin Chinese (China)","English (United States)",
        source_language_code="cmn-CN", target_language_code="en-US", denoiser=None)
    run_task = asyncio.create_task(worker.run())
    stop = asyncio.Event(); ct = asyncio.create_task(consume(worker, stop))
    worker.begin_client_session()
    results = []
    for i in range(5):
        seq_before = worker.seq
        await worker.start_session(); await asyncio.sleep(1.6)
        await feed(worker, CLIPS[i]); await asyncio.sleep(3.5)
        # the turn that just happened used seq_before (input) ... capture max seq with output
        await worker.stop_session(); await asyncio.sleep(2.0)
        results.append((i+1, seq_before))
    stop.set(); run_task.cancel()
    await asyncio.gather(run_task, ct, return_exceptions=True)
    print("\n===== CYCLE RESULTS =====")
    for cyc, seq in results:
        ok = any(got_output.get(s) for s in (seq, seq+1))
        print(f"cycle {cyc} (seq~{seq}): output={'YES' if ok else 'NO'}")

if __name__ == "__main__":
    asyncio.run(main())
