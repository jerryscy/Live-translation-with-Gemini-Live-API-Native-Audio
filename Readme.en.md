# Real-Time Audio Translation with Gemini Live API

This project demonstrates a real-time audio translation application that captures audio from a user's microphone, sends it to the Gemini Live API for translation, and plays back the translated audio in the browser.

## Features

*   **🎤 Real-time Audio Streaming:** Captures live audio from the browser using the MediaStream API and an AudioWorklet.
*   **🚀 Gemini Live API:** Leverages the power of the Gemini Live API for low-latency, simultaneous transcription and translation.
*   **🗣️ Audio Playback:** Plays the translated audio directly in the browser.
*   **🌐 FastAPI Backend:** A robust and efficient backend built with FastAPI to handle WebSocket communication.
*   **🔌 WebSocket Communication:** Real-time, bidirectional communication between the client and server.
*   **✍️ Live Transcription & Translation:** Displays the live transcription of the source audio and the translation in the user interface.
*   **🎨 Simple Frontend:** A clean and straightforward HTML/JavaScript frontend for easy interaction.

## How It Works

1.  **Audio Capture:** The browser captures audio from the user's microphone at a sample rate of 16kHz.
2.  **Client-Side Processing:** An `AudioWorklet` (`static/audio-processor.js`) running in a separate thread receives the raw audio. It converts the 32-bit floating-point samples into 16-bit PCM data, which is the format expected by the Gemini API. This processed audio is then sent to the backend via a WebSocket connection.
3.  **Backend Forwarding:** The FastAPI backend (`main.py`) acts as a relay. It receives the audio chunks from the client and forwards them directly to the Gemini Live API through the `LiveAPIWorker`.
4.  **Gemini Processing:** The `LiveAPIWorker` (`liveapiworker.py`) manages the connection to the Gemini Live API. It uses a specific `system_instruction` to configure the AI model as a real-time translator. The Gemini API processes the audio stream, providing simultaneous transcription of the input, translation to the target language, and the translated audio.
5.  **Results Streaming:** The backend streams the transcription, translation, and translated audio data back to the client over the WebSocket as soon as they are received from the Gemini API.
6.  **Display and Playback:** The frontend JavaScript (`static/index.html`) receives the data. It displays the incoming transcription and translation text in the chat interface. The translated audio (received as 24kHz 16-bit PCM) is converted into a WAV file and played back using the Web Audio API.

## Architecture

*   **Frontend:** HTML, vanilla JavaScript, Web Audio API (`AudioWorklet`)
    *   `static/index.html`: The main page with the UI and client-side logic.
    *   `static/audio-processor.js`: An `AudioWorklet` for efficient, low-latency audio processing.
*   **Backend:** Python, FastAPI, WebSockets
    *   `main.py`: The FastAPI application that handles WebSocket connections and serves the frontend.
    *   `liveapiworker.py`: A dedicated worker that manages the interaction with the Gemini Live API, including sending audio and handling the response stream.
*   **AI Model:** Gemini Live API (`gemini-live-2.5-flash-preview-native-audio-09-2025`)

## Prerequisites

*   Python 3.10+
*   Google Cloud SDK

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv myenv
    source myenv/bin/activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration and Authentication

1.  **Create a `.env` file** in the root of the project and add your Google Cloud project ID and location:
    ```env
    GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
    GOOGLE_CLOUD_LOCATION="your-gcp-location"
    ```

2.  **Authenticate with Google Cloud:**
    ```bash
    gcloud auth application-default login
    ```
3. **Set SSL Certificate (if needed):**
    ```bash
    export SSL_CERT_FILE=$(python3 -m certifi)
    ```

## Usage

1.  **Run the application:**
    ```bash
    python3 main.py
    ```

2.  **Open your browser** and navigate to `http://127.0.0.1:8000`.

3.  **Click the "Start Recording" button** and begin speaking.

4.  You will see the live transcription and translation appear in the text boxes, and you will hear the translated audio played back.

5.  **Click the "Stop Recording" button** to end the session.

## Troubleshooting

*   **Authentication Errors:** Ensure you have authenticated with `gcloud` and have the necessary permissions for the Vertex AI API in your Google Cloud project.
*   **Microphone Issues:** Check your browser and system settings to ensure the microphone is accessible and that you have granted the necessary permissions to the website.
*   **WebSocket Errors:** Make sure the FastAPI server is running and accessible at the correct address and port.
