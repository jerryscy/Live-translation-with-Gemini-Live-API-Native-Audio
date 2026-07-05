# 🎙️ 实时音频翻译 · Gemini Live API

[![zh](https://img.shields.io/badge/lang-中文-red.svg)](./Readme.md)
[![en](https://img.shields.io/badge/lang-English-blue.svg)](./Readme.en.md)

> 一个基于 **Gemini Live API**（原生音频模型）的**单向**实时语音翻译应用：浏览器采集麦克风音频 → 后端中继到 Gemini → 同步返回**原文转录**、**译文转录**与**译文音频**，并在浏览器中即时播放。支持 **70+ 种语言**、**会话内切换语言**、**跨原生音频时长限制的会话续接**，以及**实时连接状态指示**。

---

## 📑 目录

- [✨ 功能亮点](#-功能亮点)
- [🧭 工作流程](#-工作流程)
- [🏗️ 架构概览](#️-架构概览)
- [✅ 先决条件](#-先决条件)
- [⚡ 快速开始](#-快速开始)
- [🔐 配置与身份验证](#-配置与身份验证)
- [🚀 运行与使用](#-运行与使用)
- [📦 数据契约](#-数据契约)
- [🧠 Live API 关键配置](#-live-api-关键配置)
- [🛠️ 故障排除](#️-故障排除)

---

## ✨ 功能亮点

| | 功能 | 说明 |
|---|---|---|
| 🎤 | **实时音频流** | 通过 MediaStream API + AudioWorklet 以 16 kHz 单声道 PCM 采集麦克风音频 |
| ➡️ | **单向翻译** | 仅从源语言 → 目标语言（例如 `cmn-CN` → `en-US`） |
| 🌍 | **70+ 种语言** | GA + Preview 的 Chirp 3 HD 语言池，可在界面中选择 |
| 🚀 | **原生音频模型** | 使用 `gemini-live-2.5-flash-native-audio`，低延迟同传 |
| 🗣️ | **译文语音回放** | 24 kHz 16-bit PCM 流式返回浏览器（`puck` 音色），可开关 |
| 🎧 | **浏览器回声/降噪/增益控制** | 麦克风启用 `echoCancellation`、`noiseSuppression`、`autoGainControl`，抑制回声与背景噪声（无需服务端降噪器） |
| 🎭 | **情感化语音** | `enable_affective_dialog` 让译文语气贴近说话人 |
| ⏱️ | **服务端 VAD** | 自动语音活动检测，起止灵敏度经过调优 |
| 🚦 | **不中断进行中的翻译** | `activity_handling = NO_INTERRUPTION`——新语音不会截断正在进行的翻译 |
| 🔁 | **会话续接** | 原生音频会话到达约 10 分钟上限时自动重连并续接上下文 |
| 🧠 | **上下文压缩** | 滑动窗口（8192 tokens），支持长时间会话 |
| 🔌 | **实时连接指示** | 显示 后端 ↔ Live API 的会话状态 |
| 🔐 | **Google OAuth 登录（可选）** | 将整个应用（页面、`/config`、`/ws`）置于 Google 登录之后，并限制为单一 Workspace 域名（`ALLOWED_HD`）；登录用户显示在页头 |
| ⏸️ | **停止/开始即时恢复** | 停止只暂停音频、保持会话存活，再次开始可瞬时恢复（空闲会话超时后自动关闭） |
| ⚙️ | **会话内切换语言** | 修改语言后后端透明重连 Live API |
| 🎨 | **零构建前端** | 原生 HTML/JS，无需打包工具 |

---

## 🧭 工作流程

```
🎙️ 麦克风
   │  16 kHz 单声道 PCM
   ▼
🌐 浏览器 (AudioWorklet)          ── 32-bit float → 16-bit PCM
   │                                 麦克风约束：echoCancellation / noiseSuppression / autoGainControl
   │  WebSocket (二进制音频块 + JSON 控制消息)
   ▼
⚙️  FastAPI 后端 (main.py)         ── 双向消息路由
   │     ├─ 音频块 → LiveAPIWorker.send_audio_data()
   │     └─ start/stop/开关/语言切换 → 控制 worker 状态
   ▼
🤖 LiveAPIWorker (liveapiworker.py) ── 管理 Live API 会话生命周期
   ▼
🧠 Gemini Live API                ── 源语言转录 + 单向翻译 + 译文语音合成
   │  WebSocket 回流
   ▼
🌐 浏览器 (index.html)             ── 显示原文/译文文本 + 播放 24 kHz 音频
```

**详细步骤：**

1. **音频采集** — 浏览器以 16 kHz 单声道采集麦克风音频，并启用 `echoCancellation`、`noiseSuppression`、`autoGainControl`。
2. **客户端处理** — `static/audio-processor.js` 中的 `AudioWorklet` 将 32-bit float 样本量化为 16-bit PCM（小端）。
3. **会话信号** — 点击「开始」后前端通过 WebSocket 发送 `{action: "start_session"}`；worker 打开（或恢复）Gemini Live API 会话。
4. **后端中继** — `main.py` 接收二进制音频与 JSON 控制消息并转交 `LiveAPIWorker`。
5. **AI 翻译** — 严格的**单向** `system_instruction` 把模型配置成翻译管道：仅把源语言译成目标语言，对目标语言/回授音频保持静默。
6. **结果回流** — 服务端把事件推回浏览器：
   - 译文 `audio`（24 kHz PCM 二进制）
   - `data` 记录（增量原文/译文，见 [数据契约](#-数据契约)）
   - `live_api_status`（连接状态变化）
7. **展示与播放** — 前端将文本增量累加为聊天气泡，并播放译文音频。

---

## 🏗️ 架构概览

单一轻量进程。降噪在浏览器端完成，因此没有 torch 依赖，也没有 sidecar。

| 层级 | 技术栈 | 关键文件 |
|---|---|---|
| **前端** | HTML · 原生 JS · Web Audio API (`AudioWorklet`) | `static/index.html`、`static/audio-processor.js` |
| **后端** | Python (≥3.10) · FastAPI · WebSockets · `google-genai` | `main.py`、`liveapiworker.py`、`languages.py` |
| **AI 模型** | Gemini Live API（Vertex AI） | `gemini-live-2.5-flash-native-audio` |

---

## ✅ 先决条件

- **Python 3.10+**
- **Google Cloud SDK**（`gcloud`）已安装、在 `PATH` 中并已登录
- **已启用 Vertex AI API 的 GCP 项目**
- **支持麦克风的现代浏览器**（推荐 Chrome / Edge）

---

## ⚡ 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/jerryscy/Live-translation-with-Gemini-Live-API-Native-Audio.git
cd Live-translation-with-Gemini-Live-API-Native-Audio

# 2. 创建虚拟环境并安装依赖
python3 -m venv .venv-app
./.venv-app/bin/pip install --index-url https://pypi.org/simple -r requirements.txt
```

> 💡 如果全局 `pip.conf` 指向了私有源，`--index-url https://pypi.org/simple` 覆盖很重要。

---

## 🔐 配置与身份验证

### 1. 创建 `.env` 文件

```env
GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
GOOGLE_CLOUD_LOCATION="us-central1"

# 模型 + 默认语言
LIVE_API_MODEL="gemini-live-2.5-flash-native-audio"
DEFAULT_SOURCE_LANG="Mandarin Chinese (China)"
DEFAULT_SOURCE_LANG_CODE="cmn-CN"
DEFAULT_TARGET_LANG="English (United States)"
DEFAULT_TARGET_LANG_CODE="en-US"

# 行为
IDLE_CLOSE_SECONDS="30"      # 暂停会话在空闲这么多秒后关闭
DEBUG_LIVE_API="false"       # 设为 true 可记录 Live API 转录时序
```

> 💡 `.env` 已加入 `.gitignore`，不会被提交。参见 `.env.example`。

### 2. 使用 Google Cloud 进行身份验证

```bash
gcloud auth application-default login
```

请确保 **`gcloud` CLI 已安装并在 `PATH` 中**——应用使用 Application Default Credentials。（在 Cloud Run 上会自动使用服务账号。）

### 3.（可选）Google OAuth 登录

应用可要求 Google 登录，并将访问限制在单一 Workspace 域名内。仅当同时设置了
`OAUTH_CLIENT_ID` 与 `OAUTH_CLIENT_SECRET` 时才会启用（否则应用开放访问）。

- 在 Google Cloud Console（APIs & Services → Credentials）创建 **Web application**
  类型的 OAuth 客户端，并注册重定向 URI：`http://127.0.0.1:8000/auth`（本地）与
  `https://<你的服务地址>/auth`（Cloud Run）。
- 在 `.env` 中填写 OAuth 配置块（参见 `.env.example`）：`OAUTH_CLIENT_ID`、
  `OAUTH_CLIENT_SECRET`、`OAUTH_REDIRECT_URI`、`ALLOWED_HD`（如 `google.com`）
  以及一个稳定的 `SESSION_SECRET`。
- 启用后，页面、`/config` 接口与 `/ws` WebSocket 都需要邮箱域名匹配 `ALLOWED_HD`
  的已登录用户；其他人将收到 403。页头会显示登录邮箱及 **Sign out**（`/logout`）链接。

> **生产环境密钥：** 在 Cloud Run 上，应将 `OAUTH_CLIENT_SECRET` 与
> `SESSION_SECRET` 存入 **Secret Manager**，并通过 `--set-secrets` 注入——
> 参见 **[DEPLOY.md](./DEPLOY.md)**。

---

## 🚀 运行与使用

```bash
./run.sh
# 或直接运行：
./.venv-app/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

然后在 Chrome/Edge 打开 👉 **<http://127.0.0.1:8000>**

| 步骤 | 操作 |
|---|---|
| ① | （可选）选择 **输入 / 输出** 语言（默认 `cmn-CN` → `en-US`） |
| ② | 点击 **▶ 开始** 并允许麦克风权限 |
| ③ | **左侧**显示原文转录（type 1）；**右侧**显示译文（type 2） |
| ④ | **原始消息** 面板显示精确的 `data:{...}` 记录 |
| ⑤ | **播放音频** 开关控制译文语音播放 |
| ⑥ | 点击 **停止** 暂停；会话保持存活，下次 **开始** 可瞬时恢复 |

> 释放被占用的端口：`kill -9 $(lsof -tiTCP:8000) 2>/dev/null`

Cloud Run 部署请参见 **[DEPLOY.md](./DEPLOY.md)**。

---

## 📦 数据契约

结果通过 WebSocket 文本帧返回：

```json
{ "kind": "data", "data": { "uid": "...", "seq": 1, "type": 1, "delta": "…", "finished": false } }
```

| 字段 | 含义 |
|---|---|
| `uid` | 客户端会话 id（浏览器标签页连接时新建） |
| `seq` | 轮次序号；每次 `turnComplete` 递增，跨停止/开始累加 |
| `type` | `1` = 输入转录（原文），`2` = 翻译（译文） |
| `delta` | 本条记录的**新增**文本片段 |
| `finished` | 轮次进行中为 `false`；Live API 报告 `turnComplete` 时为 `true` |

**线上格式 vs 显示：** 为避免每个 token 都重发整串文本，后端只发送**增量 `delta`**。前端按 `(seq, type)` **累加**成聊天与原始面板中显示的完整 `message`。同一轮的原文（type 1）与译文（type 2）共享相同 `seq`；`delta` 为空且 `finished:true` 的记录是收尾标记。

---

## 🧠 Live API 关键配置

`liveapiworker.py` 中的 `LiveConnectConfig` 已为**实时口译**场景调优：

| 配置 | 取值 | 作用 |
|---|---|---|
| `response_modalities` | `["AUDIO"]` | 模型输出语音；文本通过转录字段获取 |
| `input_audio_transcription` | 源语言 BCP-47 | 服务端 STT 转录原文 |
| `output_audio_transcription` | 目标语言 BCP-47 | 服务端 STT 转录模型译文 |
| `proactivity.proactive_audio` | `True` | 模型积累足够上下文即开口，不等整段说完 |
| `realtime_input_config.automatic_activity_detection` | 服务端 VAD | `start = LOW`（抗噪/抗回声）、`end = HIGH`（低延迟） |
| `realtime_input_config.activity_handling` | `NO_INTERRUPTION` | 新语音**不会**截断正在进行的翻译 |
| `session_resumption` | 已启用 | 会话到达约 10 分钟上限时重连并续接上下文 |
| `enable_affective_dialog` | `True` | 译文语气贴近说话人情绪 |
| `speech_config.voice_name` | `puck` | 预置 Live API 语音 |
| `context_window_compression` | 滑动窗口 8192 tokens | 避免长会话被音频 token 撑爆上下文 |
| `system_instruction` | 严格的**单向**「翻译管道」提示 | 仅源 → 目标；对目标语言/回授音频保持静默；抗注入 |

> 修改语言时 `set_language()` 会重建配置并优雅重连 Live API，无需重启服务。

### 停止 / 开始与会话续接

点击 **停止** 只暂停音频，但**保持 Live API 会话存活**，因此再次 **开始** 可瞬时恢复（无需重连）。若停止时长超过 `IDLE_CLOSE_SECONDS`（默认 30 秒），会话将关闭；下次开始会重连。此外，当原生音频会话到达 **约 10 分钟上限**（或服务端发送 `GoAway`）时，应用会用保存的续接句柄自动重连——翻译继续、上下文保留，且无需再次点击开始。

---

## 🛠️ 故障排除

<details>
<summary><strong>🔑 身份验证错误</strong></summary>

- 确认已运行 `gcloud auth application-default login`
- 确认 `.env` 中的 `GOOGLE_CLOUD_PROJECT` 与 `GOOGLE_CLOUD_LOCATION` 正确
- 确认 GCP 项目已启用 **Vertex AI API**，且账号拥有相应 IAM 权限

</details>

<details>
<summary><strong>🎤 麦克风无法工作</strong></summary>

- 授予浏览器麦克风权限并检查操作系统的麦克风隐私设置
- 在 `chrome://settings/content/microphone` 中确认默认输入设备
- `AudioWorklet` 需要 **HTTPS 或 localhost** 环境

</details>

<details>
<summary><strong>🤖 没有输出 / Live API 一直 Error 或 Connecting</strong></summary>

- 设置 `DEBUG_LIVE_API="true"`，查看 `input_transcription` / `output_transcription` / `[run] Connection error` 日志
- 确认所选 BCP-47 语言受 Live API 支持（Preview 语言配额可能有限）
- 区域配额问题可能触发错误，可尝试更换 `GOOGLE_CLOUD_LOCATION`
- 连接错误后 worker 会退避约 3 秒再等待下一次开始

</details>

<details>
<summary><strong>🔇 听不到译文 / 自我打断</strong></summary>

- 确认 **播放音频** 已开启
- 佩戴耳机，或依赖已启用的浏览器 `echoCancellation`，避免模型把自己的输出当作输入

</details>

<details>
<summary><strong>🔒 SSL 证书错误（多见于 macOS 系统 Python）</strong></summary>

如出现 `SSL: CERTIFICATE_VERIFY_FAILED`：

```bash
pip install certifi
export SSL_CERT_FILE=$(python3 -m certifi)
```

在 macOS 上建议优先运行 python.org 安装包附带的 *Install Certificates.command*。

</details>

---

<p align="center">
  Made with ❤️ using <a href="https://ai.google.dev/">Gemini Live API</a> · <a href="https://fastapi.tiangolo.com/">FastAPI</a>
</p>
