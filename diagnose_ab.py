"""A/B: does activity_handling affect whether output_transcription appears?

Single clean utterance per session. Logs input transcript, output transcript,
audio byte count, interrupted, turn_complete. Arg: 'noint' | 'default'.
"""
import asyncio, os, sys, wave
os.environ.setdefault("DEBUG_LIVE_API", "false")
from liveapiworker import LiveAPIWorker
from google.genai.types import Blob, ActivityHandling

CHUNK_MS = 20
CLIP = sys.argv[2] if len(sys.argv) > 2 else "/tmp/c1.wav"

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

async def run_once():
    w = LiveAPIWorker("Mandarin Chinese (China)","English (United States)",
        source_language_code="cmn-CN", target_language_code="en-US", denoiser=None)
    cfg = w.config
    mode = sys.argv[1] if len(sys.argv) > 1 else "noint"
    cfg.realtime_input_config.activity_handling = (
        ActivityHandling.NO_INTERRUPTION if mode == "noint"
        else ActivityHandling.START_OF_ACTIVITY_INTERRUPTS)
    stats = {"in": "", "out": "", "audio": 0, "interrupted": False, "turn": False}
    async def receiver(session):
        async for msg in session.receive():
            sc = msg.server_content
            if not sc: continue
            if getattr(sc, "interrupted", False): stats["interrupted"] = True
            it = getattr(sc, "input_transcription", None)
            if it and it.text: stats["in"] += it.text
            ot = getattr(sc, "output_transcription", None)
            if ot and ot.text: stats["out"] += ot.text
            mt = getattr(sc, "model_turn", None)
            if mt and mt.parts:
                for p in mt.parts:
                    if getattr(p, "inline_data", None) and p.inline_data.data:
                        stats["audio"] += len(p.inline_data.data)
            if getattr(sc, "turn_complete", False):
                stats["turn"] = True; return
    async with w.client.aio.live.connect(model=w.MODEL_ID, config=cfg) as session:
        rt = asyncio.create_task(receiver(session))
        await send_clip(session, CLIP, tail_ms=1500)
        try: await asyncio.wait_for(rt, timeout=12)
        except asyncio.TimeoutError: rt.cancel()
    print(f"[{mode}] IN={stats['in'][:30]!r} | OUT={stats['out'][:50]!r} "
          f"| audio={stats['audio']}B | interrupted={stats['interrupted']} | turn={stats['turn']}")

asyncio.run(run_once())
