"""Multi-turn diagnostic: feed several utterances into ONE Live API session and
report, per turn (seq), whether input (type 1) and output (type 2) transcripts
appeared. Used to reproduce "no output transcription after a few turns".

    ./.venv-app/bin/python diagnose_multi.py
"""
import asyncio, os, sys, time, wave

os.environ.setdefault("DEBUG_LIVE_API", "false")
from liveapiworker import LiveAPIWorker

CLIPS = [f"/tmp/c{i}.wav" for i in range(1, 6)] # 5 turns
CHUNK_MS = 20
T0 = time.time()
seen = {}  # seq -> set of types


def ts():
    return f"+{time.time()-T0:6.2f}s"


async def consume(worker, stop):
    while not stop.is_set():
        try:
            ev = await asyncio.wait_for(worker.event_queue.get(), timeout=0.3)
        except asyncio.TimeoutError:
            continue
        if ev["type"] == "data":
            p = ev["payload"]
            seen.setdefault(p["seq"], set()).add(p["type"])
        worker.event_queue.task_done()


async def feed_clip(worker, path):
    w = wave.open(path)
    fpc = int(16000 * CHUNK_MS / 1000)
    while True:
        data = w.readframes(fpc)
        if not data:
            break
        await worker.send_audio_data(data)
        await asyncio.sleep(CHUNK_MS / 1000)
    silence = b"\x00\x00" * fpc
    for _ in range(90):  # ~1.8s trailing silence to end the turn
        await worker.send_audio_data(silence)
        await asyncio.sleep(CHUNK_MS / 1000)


async def main():
    worker = LiveAPIWorker(
        "Mandarin Chinese (China)", "English (United States)",
        source_language_code="cmn-CN", target_language_code="en-US", denoiser=None,
    )
    run_task = asyncio.create_task(worker.run())
    stop = asyncio.Event()
    ct = asyncio.create_task(consume(worker, stop))
    worker.begin_client_session()
    await worker.start_session()
    await asyncio.sleep(1.0)

    for i, clip in enumerate(CLIPS, 1):
        print(f"{ts()} --- feeding turn {i}: {clip} ---")
        await feed_clip(worker, clip)
        await asyncio.sleep(3.0)  # let translation + turn_complete finish

    stop.set()
    await worker.stop_session()
    run_task.cancel()
    await asyncio.gather(run_task, ct, return_exceptions=True)

    print("\n===== PER-TURN SUMMARY =====")
    for seq in sorted(seen):
        types = seen[seq]
        print(f"seq {seq}: input(type1)={'YES' if 1 in types else 'no '}  "
              f"output(type2)={'YES' if 2 in types else 'NO '}")


if __name__ == "__main__":
    asyncio.run(main())
