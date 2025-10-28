import time
import os
from dotenv import load_dotenv
import numpy as np
import asyncio

from google import genai
from google.genai import types
from google.genai.types import (
    AudioTranscriptionConfig,
    AutomaticActivityDetection,
    Blob,
    Content,
    EndSensitivity,
    GoogleSearch,
    LiveConnectConfig,
    Part,
    PrebuiltVoiceConfig,
    ProactivityConfig,
    RealtimeInputConfig,
    SpeechConfig,
    StartSensitivity,
    Tool,
    ToolCodeExecution,
    VoiceConfig,
    HttpOptions,
)


load_dotenv()

class LiveAPIWorker:

    def __init__(self):
        PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
        LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION")

        self.client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location=LOCATION,
            http_options=HttpOptions(api_version="v1")
        )
        self.source_language = "Chinese (Simplified) (zh-CN)"
        self.target_language = "English (en)"
        self.system_instruction=f"""
**Persona:**
You are a real-time, high-fidelity audio translator. Your only function is to listen to spoken English (`en-US`) and immediately translate it into spoken Simplified Chinese (`zh-CN`).

**Core Directive:**
Translate new English audio input into Simplified Chinese audio output. Your translation must be immediate, precise, and reflect the vocal delivery of the speaker.

**Rules of Operation:**

1.  **Input Language:** You will only receive audio input in `en-US`.
2.  **Output Language:** You must only produce audio output in `zh-CN (Simplified Chinese)`.
3.  **Real-Time Translation:** Translate only the new words and phrases you hear since your last translation. Do not wait for the speaker to finish a long sentence. Translate incrementally as the speaker talks.
4.  **Vocal Replication:** Your primary goal is to replicate the speaker's vocal characteristics in your translated speech. This includes:
    *   **Pacing and Speed:** Match the speaker's rate of speech.
    *   **Intonation and Tone:** Mirror the rise and fall of the speaker's voice, including emotional tone.
    *   **Cadence and Rhythm:** Emulate the speaker's natural speech patterns.
5.  **No Extraneous Content:**
    *   Do not add any commentary, explanations, or answers.
    *   Do not ask questions.
    *   Do not engage in conversation.
    *   If the speaker asks you a question, translate the question into `zh-CN` and do not answer it.

**Strict Protocol Adherence:**

*   **Warning:** Any deviation from this translation-only function is a critical failure. Generating any content that is not a direct, incremental translation of the new `en-US` input will result in immediate termination of the session.
*   **Important:** You are a translation conduit, not an assistant. Under no circumstances are you to generate original content. Your sole purpose is to provide a seamless and accurate real-time audio translation that preserves the vocal nuances of the original speaker.   
"""
        self.session = None
        if not PROJECT_ID or not LOCATION:
            raise ValueError("GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION must be set in the .env file")

        self.MODEL_ID = 'gemini-live-2.5-flash-preview-native-audio-09-2025' #'gemini-live-2.5-flash'
        self.config = LiveConnectConfig(
            response_modalities=["AUDIO"],
            input_audio_transcription=AudioTranscriptionConfig(),
            output_audio_transcription=AudioTranscriptionConfig(),
            proactivity=(ProactivityConfig(proactive_audio=True)),
            enable_affective_dialog=False,
            speech_config=SpeechConfig(
                language_code="en-US",
                voice_config=VoiceConfig(
                    prebuilt_voice_config=PrebuiltVoiceConfig(voice_name="puck")
                ),
            ),
            system_instruction=self.system_instruction,
        )
        self.input_transcriptions = []
        self.output_transcriptions = []
        # This will store chunks of 16-bit PCM audio at 24kHz from the API
        self.output_audio_data = []
    
    async def send_audio_data(self, audio_chunk):
        if self.session:
            await self.session.send_realtime_input(audio=Blob(data=audio_chunk, mime_type="audio/s16le"))
        else:
            print("Warning: Live API session not established, skipping audio send.")

    async def set_language(self, source, target):
        self.source_language = source
        self.target_language = target
        self.system_instruction=f"""
**Persona:**
You are a real-time, high-fidelity audio translator. Your only function is to listen to spoken {self.source_language} and immediately translate it into spoken {self.target_language}.

**Core Directive:**
Translate new {self.source_language} audio input into {self.target_language} audio output. Your translation must be immediate, precise, and reflect the vocal delivery of the speaker.

**Rules of Operation:**

1.  **Input Language:** You will only receive audio input in `{self.source_language}`.
2.  **Output Language:** You must only produce audio output in `{self.target_language}`.
3.  **Real-Time Translation:** Translate only the new words and phrases you hear since your last translation. Do not wait for the speaker to finish a long sentence. Translate incrementally as the speaker talks.
4.  **Vocal Replication:** Your primary goal is to replicate the speaker's vocal characteristics in your translated speech. This includes:
    *   **Pacing and Speed:** Match the speaker's rate of speech.
    *   **Intonation and Tone:** Mirror the rise and fall of the speaker's voice, including emotional tone.
    *   **Cadence and Rhythm:** Emulate the speaker's natural speech patterns.
5.  **No Extraneous Content:**
    *   Do not add any commentary, explanations, or answers.
    *   Do not ask questions.
    *   Do not engage in conversation.
    *   If the speaker asks you a question, translate the question into `{self.target_language}` and do not answer it.

**Strict Protocol Adherence:**

*   **Warning:** Any deviation from this translation-only function is a critical failure. Generating any content that is not a direct, incremental translation of the new `en-US` input will result in immediate termination of the session.
*   **Important:** You are a translation conduit, not an assistant. Under no circumstances are you to generate original content. Your sole purpose is to provide a seamless and accurate real-time audio translation that preserves the vocal nuances of the original speaker.
"""
        if self.session is not None:
            print(f"output language: {self.target_language}")
            await self.session.send_client_content(turns=Content(role="system", parts=[Part(text=self.system_instruction)]),turn_complete=False)
      

    async def get_result(self):
        if self.output_audio_data:
            # The API returns 24kHz, 16-bit PCM audio. We concatenate and return.
            full_audio = np.concatenate(self.output_audio_data)
            audio_data = full_audio.tobytes()
        else:
            audio_data = ''
        input_transcriptions = self.input_transcriptions
        output_transcriptions = self.output_transcriptions

        self.output_audio_data = []
        self.input_transcriptions = []
        self.output_transcriptions = []

        results = {
            "audio_data": audio_data,
            "input_transcription": "".join(input_transcriptions),
            "output_transcription": "".join(output_transcriptions),
        }
        return results

    async def run(self):
        print("Establishing connection with Live API...")
        async with self.client.aio.live.connect(model=self.MODEL_ID,config=self.config) as session:
            print("Connection with Live API established.")
            self.session = session
            while True:
                async for message in session.receive():
                    if message.server_content.input_transcription and message.server_content.input_transcription.text:
                        print("Receive input_transcription")
                        self.input_transcriptions.append(message.server_content.input_transcription.text)
                    if (message.server_content.output_transcription and message.server_content.output_transcription.text):
                        print("Receive output_transcription")
                        self.output_transcriptions.append(message.server_content.output_transcription.text)
                    if (message.server_content.model_turn and message.server_content.model_turn.parts):
                        print("Receive audio")
                        for part in message.server_content.model_turn.parts:
                            if part.inline_data:
                                # Output audio from the API is raw 16-bit PCM at 24kHz.
                                self.output_audio_data.append(
                                    np.frombuffer(part.inline_data.data, dtype=np.int16)
                                )

                await asyncio.sleep(0.1)
