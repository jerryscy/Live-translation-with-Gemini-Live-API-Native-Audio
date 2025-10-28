# 使用 Gemini Live API 进行实时音频翻译
[![zh](https://img.shields.io/badge/lang-zh-red.svg)](./Readme.md)
[![en](https://img.shields.io/badge/lang-en-red.svg)](./Readme.en.md)

该项目展示了一个实时音频翻译应用程序，它从用户的麦克风捕获音频，将其发送到 Gemini Live API 进行翻译，并在浏览器中播放翻译后的音频。

## 功能

*   **🎤 实时音频流：** 使用 MediaStream API 和 AudioWorklet 从浏览器捕获实时音频。
*   **🚀 Gemini Live API：** 利用 Gemini Live API 的强大功能，实现低延迟、同步的转录和翻译。
*   **🗣️ 音频播放：** 直接在浏览器中播放翻译后的音频。
*   **🌐 FastAPI 后端：** 使用 FastAPI 构建的健壮高效的后端，用于处理 WebSocket 通信。
*   **🔌 WebSocket 通信：** 客户端和服务器之间的实时双向通信。
*   **✍️ 实时转录和翻译：** 在用户界面中显示源音频的实时转录和翻译。
*   **🎨 简单的前端：** 简洁明了的 HTML/JavaScript 前端，易于交互。

## 工作原理

1.  **音频捕获：** 浏览器以 16kHz 的采样率从用户的麦克风捕获音频。
2.  **客户端处理：** 一个在单独线程中运行的 `AudioWorklet` (`static/audio-processor.js`) 接收原始音频。它将 32 位浮点采样转换为 16 位 PCM 数据，这是 Gemini API 所需的格式。然后，处理后的音频通过 WebSocket 连接发送到后端。
3.  **后端转发：** FastAPI 后端 (`main.py`) 充当中继。它从客户端接收音频块，并通过 `LiveAPIWorker` 将它们直接转发到 Gemini Live API。
4.  **Gemini 处理：** `LiveAPIWorker` (`liveapiworker.py`) 管理与 Gemini Live API 的连接。它使用特定的 `system_instruction` 将 AI 模型配置为实时翻译器。Gemini API 处理音频流，提供输入的同步转录、目标语言的翻译以及翻译后的音频。
5.  **结果流式传输：** 后端在从 Gemini API 收到转录、翻译和翻译后的音频数据后，立即通过 WebSocket 将它们流式传输回客户端。
6.  **显示和播放：** 前端 JavaScript (`static/index.html`) 接收数据。它在聊天界面中显示传入的转录和翻译文本。翻译后的音频（以 24kHz 16 位 PCM 格式接收）被转换为 WAV 文件，并使用 Web Audio API 播放。

## 架构

*   **前端：** HTML、原生 JavaScript、Web Audio API (`AudioWorklet`)
    *   `static/index.html`: 包含用户界面和客户端逻辑的主页面。
    *   `static/audio-processor.js`: 用于高效、低延迟音频处理的 `AudioWorklet`。
*   **后端：** Python、FastAPI、WebSockets
    *   `main.py`: 处理 WebSocket 连接并提供前端服务的 FastAPI 应用程序。
    *   `liveapiworker.py`: 一个专用的工作程序，负责管理与 Gemini Live API 的交互，包括发送音频和处理响应流。
*   **AI 模型：** Gemini Live API (`gemini-live-2.5-flash-preview-native-audio-09-2025`)

## 先决条件

*   Python 3.10+
*   Google Cloud SDK

## 安装

1.  **克隆存储库：**
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **创建并激活虚拟环境：**
    ```bash
    python3 -m venv myenv
    source myenv/bin/activate
    ```

3.  **安装所需的依赖项：**
    ```bash
    pip install -r requirements.txt
    ```

## 配置和身份验证

1.  **在项目根目录中创建一个 `.env` 文件**，并添加您的 Google Cloud 项目 ID 和位置：
    ```env
    GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
    GOOGLE_CLOUD_LOCATION="your-gcp-location"
    ```

2.  **使用 Google Cloud 进行身份验证：**
    ```bash
    gcloud auth application-default login
    ```
3. **设置 SSL 证书（如果需要）：**
    ```bash
    export SSL_CERT_FILE=$(python3 -m certifi)
    ```

## 使用方法

1.  **运行应用程序：**
    ```bash
    python3 main.py
    ```

2.  **打开浏览器**并导航到 `http://127.0.0.1:8000`。

3.  **单击“开始录制”按钮**并开始讲话。

4.  您将看到实时转录和翻译出现在文本框中，并且您将听到播放的翻译音频。

5.  **单击“停止录制”按钮**以结束会话。

## 故障排除

*   **身份验证错误：** 确保您已使用 `gcloud` 进行身份验证，并在您的 Google Cloud 项目中具有 Vertex AI API 的必要权限。
*   **麦克风问题：** 检查您的浏览器和系统设置，确保麦克风可访问，并且您已授予网站必要的权限。
*   **WebSocket 错误：** 确保 FastAPI 服务器正在运行，并且可以在正确的地址和端口访问。
