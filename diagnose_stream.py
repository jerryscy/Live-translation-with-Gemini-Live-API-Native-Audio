"""Simulate continuous/back-to-back speech (like a real mic) and count how
many utterances actually get an output_transcription.

Arg1: 'noint' | 'default'   Arg2: gap_ms between utterances (default 300)
"""
import asyncio, os, sys, wave
os.environ.setdefault("DEBUG_LIVE_API", "false")
from liveapiworker import LiveAPIWorker
from google.genai.types import Blob, ActivityHandling

CHUNK_MS = 20
MODE = sys.argv[1] if len(sys.argv) > 1 else "noint"
GAP_MS = int(sys.argv[2]) if len(sys.argv) > 2 else 300
CLIPS = ["/tmp/c1.wav", "/tmp/c2.wav", "/tmp/c3.wav", "/tmp/c4.wav"]

async def feed(session, path):
    w = wave.open(path); fpc = int(16000*CHUNK_MS/1000)
    while True:
        d = w.readframes(fpc)
        if not d: break
        await session.send_realtime_input(audio=Blob(data=d, mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(CHUNK_MS/1000)

async def feed_silence(session, ms):
    fpc = int(16000*CHUNK_MS/1000); sil = b"\x00\x00"*fpc
    for _ in range(int(ms/CHUNK_MS)):
        await session.send_realtime_input(audio=Blob(data=sil, mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(CHUNK_MS/1000)

async def main():
    w = LiveAPIWorker("Mandarin Chinese (China)","English (United States)",
        source_language_code="cmn-CN", target_language_code="en-US", denoiser=None)
    cfg = w.config
    cfg.realtime_input_config.activity_handling = (
        ActivityHandling.NO_INTERRUPTION if MODE == "noint"
        else ActivityHandling.START_OF_ACTIVITY_INTERRUPTS)
    ins, outs, turns = [], [], [0]
    async def receiver(session):
        cur_out = [""]
        async for msg in session.receive():
            sc = msg.server_content
            if not sc: continue
            it = getattr(sc, "input_transcription", None)
            if it and it.text: ins.append(it.text)
            ot = getattr(sc, "output_transcription", None)
            if ot and ot.text: cur_out[0] += ot.text
            if getattr(sc, "turn_complete", False):
                turns[0]+=1
                if cur_out[0]: outs.append(cur_out[0]); cur_out[0]=""
    async with w.client.aio.live.connect(model=w.MODEL_ID, config=cfg) as session:
        rt = asyncio.create_task(receiver(session))
        for c in CLIPS:
            await feed(session, c)
            await feed_silence(session, GAP_MS)   # short gap, like a real speaker
        await feed_silence(session, 2000)         # final trailing silence
        await asyncio.sleep(8)
        rt.cancel(); await asyncio.gather(rt, return_exceptions=True)
    print(f"\n[{MODE} gap={GAP_MS}ms] fed {len(CLIPS)} utterances")
    print(f"  turns_completed = {turns[0]}")
    print(f"  input_transcripts  = {len(ins)} segment(s)")
    print(f"  OUTPUT translations = {len(outs)}:")
    for o in outs: print(f"     - {o!r}")

asyncio.run(main())
