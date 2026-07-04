"""Check whether new incoming voice interrupts the model's ongoing output.

Feeds clip1, waits for the model to START translating it, then feeds clip2
(new voice) mid-output to see if the first translation gets interrupted.
Pass 'noint' as arg to test with activity_handling=NO_INTERRUPTION.
"""
import asyncio, os, sys, time, wave
os.environ.setdefault("DEBUG_LIVE_API", "false")
from liveapiworker import LiveAPIWorker
from google.genai.types import Blob, ActivityHandling

CHUNK_MS = 20
T0 = time.time()
def ts(): return f"+{time.time()-T0:6.2f}s"
output_started = asyncio.Event()

async def send_clip(session, path, tail_ms):
    w = wave.open(path); fpc = int(16000*CHUNK_MS/1000)
    while True:
        d = w.readframes(fpc)
        if not d: break
        await session.send_realtime_input(audio=Blob(data=d, mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(CHUNK_MS/1000)
    sil = b"\x00\x00"*fpc
    for _ in range(int(tail_ms/CHUNK_MS)):
        await session.send_realtime_input(audio=Blob(data=sil, mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(CHUNK_MS/1000)

async def receiver(session):
    async for msg in session.receive():
        sc = msg.server_content
        if not sc: continue
        if getattr(sc, "interrupted", False): print(f"{ts()} *** INTERRUPTED ***")
        ot = getattr(sc, "output_transcription", None)
        if ot and ot.text:
            print(f"{ts()} OUT: {ot.text!r}")
            output_started.set()
        if getattr(sc, "turn_complete", False): print(f"{ts()} turn_complete")

async def main():
    w = LiveAPIWorker("Mandarin Chinese (China)","English (United States)",
        source_language_code="cmn-CN", target_language_code="en-US", denoiser=None)
    cfg = w.config
    if len(sys.argv) > 1 and sys.argv[1] == "default":
        cfg.realtime_input_config.activity_handling = ActivityHandling.START_OF_ACTIVITY_INTERRUPTS
    print(f"[config] effective activity_handling = {cfg.realtime_input_config.activity_handling}")
    async with w.client.aio.live.connect(model=w.MODEL_ID, config=cfg) as session:
        rt = asyncio.create_task(receiver(session))
        print(f"{ts()} feeding clip1 ...")
        await send_clip(session, "/tmp/c4.wav", tail_ms=1200)
        print(f"{ts()} clip1 sent; waiting for model to START translating ...")
        try:
            await asyncio.wait_for(output_started.wait(), timeout=10)
        except asyncio.TimeoutError:
            print(f"{ts()} (no output started?)")
        print(f"{ts()} >>> model is translating — talking over it with clip2 (NEW VOICE) now <<<")
        await send_clip(session, "/tmp/c5.wav", tail_ms=1500)
        await asyncio.sleep(8)
        rt.cancel(); await asyncio.gather(rt, return_exceptions=True)

asyncio.run(main())
