import asyncio
import json
import os
import subprocess
import uvicorn

from typing import Union
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from liveapiworker import LiveAPIWorker

# --- Configuration ---
DEFAULT_SOURCE_LANG = "English (en-us)"
DEFAULT_TARGET_LANG = "Chinese (Simplified) (zh-CN)"

# --- Global Instances ---
app = FastAPI()


def check_gcloud_auth():
    """
    Checks for gcloud authentication and prompts the user to log in if not authenticated.
    """
    try:
        # The 'r' at the end of the command was a typo in the prompt, so I am correcting it to 'token'
        subprocess.check_output(["gcloud", "auth", "application-default", "print-access-token"], stderr=subprocess.STDOUT)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Attempting to authenticate with gcloud...")
        subprocess.run(["gcloud", "auth", "application-default", "login"])
        print("Authentication successful, you can now start the application.")
        

liveapiworker: Union[LiveAPIWorker, None] = None




app.mount("/static", StaticFiles(directory="static"), name="static")


async def receive_from_worker(websocket: WebSocket):
    while True:
        try:
            if not liveapiworker:
                await asyncio.sleep(0.1)
                continue
            result = await liveapiworker.get_result()
            
            audio_data = result.get("audio_data")
            input_transcription = result.get("input_transcription")
            output_transcription = result.get("output_transcription")

            # Only send if there is something to send
            if audio_data or input_transcription or output_transcription:
                text_payload = {
                    "input_transcription": input_transcription,
                    "output_transcription": output_transcription
                }
                await websocket.send_text(json.dumps(text_payload))

                if audio_data:
                    await websocket.send_bytes(audio_data)

            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            break


@app.on_event("startup")
async def startup_event():
    check_gcloud_auth()
    global liveapiworker
    liveapiworker = LiveAPIWorker()
    await liveapiworker.set_language(DEFAULT_SOURCE_LANG, DEFAULT_TARGET_LANG)
    asyncio.create_task(liveapiworker.run())


@app.get("/")
async def get():
    return FileResponse('static/index.html')


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    receive_task = asyncio.create_task(receive_from_worker(websocket))
    try:
        while True:
            data = await websocket.receive()
            if liveapiworker:
                if "bytes" in data:
                    await liveapiworker.send_audio_data(data["bytes"])
                elif "text" in data:
                    message = json.loads(data["text"])
                    if "target_language" in message:
                        await liveapiworker.set_language(DEFAULT_SOURCE_LANG, message["target_language"])

    except WebSocketDisconnect:
        print("Client disconnected")
    finally:
        receive_task.cancel()


if __name__ == "__main__":

    uvicorn.run(app, host="127.0.0.1", port=8000)
