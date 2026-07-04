"""Exercise the REAL worker receiver/sender/emit code and print every record
that lands on its event_queue (what the browser would receive)."""
import asyncio, os, time, wave
os.environ.setdefault("DEBUG_LIVE_API", "false")
from liveapiworker import LiveAPIWorker
T0=time.time()
def ts(): return f"+{time.time()-T0:6.2f}s"

async def main():
    w = LiveAPIWorker("Mandarin Chinese (China)","English (United States)",
        source_language_code="cmn-CN", target_language_code="en-US", denoiser=None)
    w.begin_client_session()
    w._paused = False
    async def drain():
        while True:
            ev = await w.event_queue.get()
            if ev.get("type")=="data":
                p=ev["payload"]
                print(f"{ts()} EMIT type={p['type']} seq={p['seq']} finished={p['finished']} delta={p['delta']!r}")
            w.event_queue.task_done()
    async with w.client.aio.live.connect(model=w.MODEL_ID, config=w.config) as session:
        d=asyncio.create_task(drain())
        s=asyncio.create_task(w._sender_task(session))
        r=asyncio.create_task(w._receiver_supervisor(session))
        # feed audio through the real queue path
        wav=wave.open("/tmp/c1.wav"); fpc=int(16000*20/1000)
        while True:
            b=wav.readframes(fpc)
            if not b: break
            await w.send_audio_data(b); await asyncio.sleep(0.02)
        sil=b"\x00\x00"*fpc
        for _ in range(int(1600/20)):
            await w.send_audio_data(sil); await asyncio.sleep(0.02)
        await asyncio.sleep(7)
        for t in (r,s,d): t.cancel()
        await asyncio.gather(r,s,d, return_exceptions=True)

asyncio.run(main())
