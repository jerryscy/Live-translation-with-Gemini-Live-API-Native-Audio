"""Exercise the REAL browser->server path over the /ws WebSocket.

Sends start_session + streams a WAV as 16k PCM chunks, then collects the
'data' records (type1 input / type2 translation) and audio the server sends.
"""
import asyncio, json, sys, wave
import websockets

URL = "ws://127.0.0.1:8000/ws"
CLIP = sys.argv[1] if len(sys.argv) > 1 else "/tmp/c1.wav"
CHUNK_MS = 20

async def main():
    data_recs, audio_bytes, statuses = [], 0, []
    async with websockets.connect(URL, max_size=None) as ws:
        async def reader():
            nonlocal audio_bytes
            try:
                async for msg in ws:
                    if isinstance(msg, bytes):
                        audio_bytes += len(msg); continue
                    o = json.loads(msg)
                    k = o.get("kind")
                    if k == "data":
                        data_recs.append(o["data"])
                        d = o["data"]
                        print(f"  DATA type={d.get('type')} seq={d.get('seq')} "
                              f"finished={d.get('finished')} delta={str(d.get('delta'))[:45]!r}")
                    else:
                        statuses.append(o)
                        print(f"  STATUS {o}")
            except Exception as e:
                print("  reader end:", e)
        rt = asyncio.create_task(reader())
        denoiser_on = not (len(sys.argv) > 2 and sys.argv[2] == "nodn")
        audio_on = not (len(sys.argv) > 3 and sys.argv[3] == "noaudio")
        await ws.send(json.dumps({"action": "set_denoiser", "enabled": denoiser_on}))
        print(f"[ws] denoiser_enabled={denoiser_on} audio_output={audio_on}")
        await ws.send(json.dumps({"action": "set_audio_output", "enabled": audio_on}))
        await ws.send(json.dumps({"action": "start_session"}))
        await asyncio.sleep(1.0)
        print(f"[ws] streaming {CLIP} ...")
        w = wave.open(CLIP); fpc = int(16000*CHUNK_MS/1000)
        while True:
            d = w.readframes(fpc)
            if not d: break
            await ws.send(d)
            await asyncio.sleep(CHUNK_MS/1000)
        sil = b"\x00\x00"*fpc
        for _ in range(int(1800/CHUNK_MS)):   # trailing silence to end the turn
            await ws.send(sil); await asyncio.sleep(CHUNK_MS/1000)
        print("[ws] waiting for output ...")
        await asyncio.sleep(10)   # give the reader ample time to drain
        await ws.send(json.dumps({"action": "stop_session"}))
        await asyncio.sleep(1.5)
        rt.cancel()
        try: await rt
        except: pass
    print(f"\n[RESULT] data_records={len(data_recs)}  audio_bytes={audio_bytes}")
    t1 = [d for d in data_recs if d.get("type")==1]
    t2 = [d for d in data_recs if d.get("type")==2]
    print(f"  type1 (input) records : {len(t1)}")
    print(f"  type2 (translation)   : {len(t2)}")
    if t2: print("  last translation:", t2[-1].get("message"))

asyncio.run(main())
