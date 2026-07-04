"""Print the exact per-message ordering of input/output/turn_complete so we can
see whether input_transcription arrives and where relative to turn_complete."""
import asyncio, os, time, wave
os.environ.setdefault("DEBUG_LIVE_API", "false")
from liveapiworker import LiveAPIWorker
from google.genai.types import Blob

T0 = time.time()
def ts(): return f"+{time.time()-T0:6.2f}s"

async def feed(session, path, tail_ms=1600):
    w = wave.open(path); fpc = int(16000*20/1000)
    while True:
        d = w.readframes(fpc)
        if not d: break
        await session.send_realtime_input(audio=Blob(data=d, mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(0.02)
    sil=b"\x00\x00"*fpc
    for _ in range(int(tail_ms/20)):
        await session.send_realtime_input(audio=Blob(data=sil, mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(0.02)

async def main():
    w = LiveAPIWorker("Mandarin Chinese (China)","English (United States)",
        source_language_code="cmn-CN", target_language_code="en-US", denoiser=None)
    async with w.client.aio.live.connect(model=w.MODEL_ID, config=w.config) as session:
        async def recv():
            n=0
            async for m in session.receive():
                sc=m.server_content
                if not sc: continue
                n+=1
                it=getattr(sc,"input_transcription",None)
                ot=getattr(sc,"output_transcription",None)
                tc=getattr(sc,"turn_complete",False)
                itxt=(it.text if it else None)
                otxt=(ot.text if ot else None)
                parts=[]
                if itxt: parts.append(f"IN={itxt!r}")
                if otxt: parts.append(f"OUT={otxt!r}")
                if tc: parts.append("TURN_COMPLETE")
                if parts: print(f"{ts()} msg#{n}: {'  '.join(parts)}")
        rt=asyncio.create_task(recv())
        await feed(session, "/tmp/c1.wav")
        await asyncio.sleep(7)
        rt.cancel()
        await asyncio.gather(rt, return_exceptions=True)

asyncio.run(main())
