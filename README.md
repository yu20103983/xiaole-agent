# 小乐 (XiaoLe) — 中文语音 AI 助手

<p align="center">
  <strong>🎧 说"小乐小乐"，你的 AI 助手就在身边</strong>
</p>

<p align="center">
  基于唤醒词的中文语音 AI 助手，通过麦克风和扬声器（或蓝牙耳机）与
  <a href="https://github.com/mariozechner/pi-coding-agent">Pi Coding Agent</a>
  进行自然语音交互。
</p>

---

## ✨ 特性

| 功能 | 说明 |
|------|------|
| 🗣️ 语音唤醒 | "小乐小乐"唤醒，模糊语音匹配（享乐 / 向乐 / 想乐等 ASR 常见变体） |
| 🤖 AI 对话 | 语音下达指令，AI 助手执行并语音播报结果 |
| ⚡ 流式播报 | Agent 回复实时切句合成播放，首句 < 0.5 秒 |
| ✋ 语音打断 | 播报中说"终止"立即中断 |
| 🔄 连续对话 | 免唤醒多轮交互（英语口语练习、闲聊等场景） |
| 📋 指令排队 | 处理中识别到新指令自动排队，完成后依次执行 |
| 🎵 全离线 TTS | Matcha-TTS 本地推理，RTF ≈ 0.08，无需联网 |
| 🎧 蓝牙 / 本地双模式 | 自动检测蓝牙耳机或本地麦克风 + 扬声器 |
| 🔊 全双工 / 半双工 | 设备能力自动检测，边说边听 |

## 🚀 快速开始

> 详见 [QUICK_START.md](QUICK_START.md) 获取完整的分步指南。

### 前置条件

- **操作系统**：Windows 10 / 11
- **Python**：3.10+
- **Node.js**：18+（Pi Agent 依赖）
- **硬件**：麦克风 + 扬声器（或蓝牙耳机）

### 安装

```bash
git clone https://github.com/yu20103983/xiaole-agent.git
cd xiaole-agent

# 方式一：一键安装
setup.bat

# 方式二：手动安装
pip install -r requirements.txt
npm install
download_models.bat
```

### 配置 AI Provider

编辑 `src/config.py`，设置你的 AI provider 和模型：

```python
PI_PROVIDER = "anthropic"         # 你的 provider 名称
PI_MODEL = "claude-sonnet-4-20250514"  # 你的模型名称
```

> 支持 Anthropic / OpenAI / 自定义 provider，详见 [Pi Agent 文档](https://github.com/mariozechner/pi-coding-agent)。

### 启动

```bash
# 命令行启动
python -X utf8 src/main.py

# 或使用自动重启脚本
start.bat
```

## 🎙️ 使用方法

```
你：  "小乐小乐"              → 唤醒
小乐：  "我在，请说"

你：  "帮我查一下今天天气"      → 等 4 秒静音或说"好了"发送
小乐：  "好的，我来查一下..."

你：  "终止"                   → 打断播报

你：  "小乐小乐退下"           → 休眠
小乐：  "好的，再见"
```

### 操作速查

| 操作 | 说法 | 说明 |
|------|------|------|
| 唤醒 | "小乐小乐" | 从休眠进入活跃状态 |
| 唤醒 + 指令 | "小乐，帮我查天气" | 一步到位 |
| 分步指令 | "小乐"（停顿）"帮我查天气" | 5 秒内自动关联 |
| 结束输入 | 说"好了" / 等 4 秒静音 | 触发指令发送 |
| 打断播报 | "终止" | 立即中断当前回复 |
| 休眠 | "小乐退下" / "小乐再见" | 进入休眠状态 |
| 连续对话 | "我们聊聊天" | Agent 自动开启免唤醒模式 |

## 🏗️ 架构

```
┌─────────┐     ┌───────────────┐     ┌────────────────┐     ┌────────────┐
│  麦克风  │────→│   ASR 引擎     │────→│  会话状态机     │────→│  Pi Agent  │
│  (录音)  │     │ SenseVoice+VAD│     │ 唤醒/指令/休眠  │     │  (RPC)     │
└─────────┘     └───────────────┘     └────────────────┘     └──────┬─────┘
                                                                    │
┌─────────┐     ┌───────────────┐     ┌────────────────┐           │
│  扬声器  │←────│   TTS 引擎     │←────│  流式播放管线   │←──────────┘
│  (播放)  │     │  Matcha-TTS   │     │ 并发合成 + FIFO │
└─────────┘     └───────────────┘     └────────────────┘
```

### 模块说明

| 模块 | 职责 |
|------|------|
| `main.py` | 主程序：启动初始化、音频播放管线、指令分发 |
| `config.py` | 全局配置：音频设备、TTS、会话、Agent 参数 |
| `asr_engine.py` | ASR 引擎：SenseVoice + Silero VAD，异步流式识别 |
| `tts_engine.py` | TTS 引擎：sherpa-onnx Matcha-TTS 本地推理 + 磁盘缓存 |
| `audio_io.py` | 音频 I/O：录音、设备自动检测、双工检测、高性能重采样 |
| `session_controller.py` | 会话状态机：唤醒词检测、指令提取、上下文关联、连续对话 |
| `pi_client.py` | Pi Agent RPC 客户端：子进程管理、流式事件、自动重启 |

## ⚙️ 配置

所有配置集中在 `src/config.py`：

```python
# ===== 音频设备 =====
A2DP_ID = None          # 输出设备 ID (None = 自动检测)
HFP_IN = None           # 输入设备 ID (None = 自动检测)
PREFER_LOCAL = False    # 优先本地设备（跳过蓝牙检测）
DUPLEX_MODE = None      # 全双工模式 (True / False / None = 自动检测)

# ===== TTS =====
TTS_VOICE = "matcha-zh-baker"  # 本地模型：matcha-zh-baker / melo-zh
TTS_SPEED = 1.0                # 语速 (1.0 = 正常)

# ===== 会话 =====
INPUT_SILENCE_TIMEOUT = 4.0          # 静音超时发送指令 (秒)
AUTO_SLEEP_TIMEOUT = 0               # 自动休眠 (0 = 禁用)
CONTINUOUS_SILENCE_TIMEOUT = 30      # 连续对话沉默超时 (秒)

# ===== Agent =====
PI_WORKING_DIR = "."                 # Agent 工作目录
PI_PROVIDER = "claude-proxy"         # AI provider
PI_MODEL = "claude-opus-4-6"         # AI 模型
```

## 📁 项目结构

```
xiaole-agent/
├── src/
│   ├── main.py                # 主程序
│   ├── config.py              # 全局配置
│   ├── asr_engine.py          # ASR 引擎 (SenseVoice + VAD)
│   ├── tts_engine.py          # TTS 引擎 (Matcha-TTS 本地推理)
│   ├── audio_io.py            # 音频 I/O 与设备管理
│   ├── session_controller.py  # 会话状态机
│   └── pi_client.py           # Pi Agent RPC 客户端
├── models/                    # ASR / TTS 模型 (需下载，不含在仓库中)
├── cache/tts/                 # TTS 音频磁盘缓存 (自动生成)
├── tests/                     # 测试脚本
├── setup.bat                  # 一键安装脚本
├── start.bat                  # 启动脚本 (自动重启)
├── download_models.bat        # 模型下载脚本
├── requirements.txt           # Python 依赖
├── package.json               # Node.js 依赖
└── README.md
```

## 🔧 技术细节

### TTS 播放管线

1. Agent 流式返回文本 → 按标点切句（逗号切短句，句号切长句）
2. 每个短句独立合成 + 相邻短句合并合成（提升语气连贯性）
3. FIFO 顺序播放，优先选最长已就绪的合并音频
4. 首 2 句不等合并直接播放，减少首次响应延迟

### 唤醒词匹配

- 模糊匹配"小乐"及其语音变体（肖乐 / 笑乐 / 享乐等）
- "X乐X乐" 模式匹配
- "乐"前缀截断识别（ASR 截掉了"小"字）
- 上下文关联：先说"小乐"停顿 → 5 秒内的下一句自动拼接为指令

### 音频设备检测

按优先级自动检测：

1. 蓝牙一体：HFP 输入 + A2DP 输出（半双工）
2. 蓝牙 + 本地混合：本地麦克风 + 蓝牙输出（全双工）
3. 纯本地：本地麦克风 + 本地扬声器（全双工）

## 🤝 致谢

- [Pi Coding Agent](https://github.com/mariozechner/pi-coding-agent) — AI Agent 后端
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) — ASR (SenseVoice) + TTS (Matcha-TTS) 推理引擎
- [Silero VAD](https://github.com/snakers4/silero-vad) — 语音活动检测

## 📄 许可证

[MIT License](LICENSE)
