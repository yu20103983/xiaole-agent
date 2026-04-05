# 小乐 - 语音 AI 助手

基于唤醒词的中文语音 AI 助手，通过麦克风和扬声器（或蓝牙耳机）与 [Pi Coding Agent](https://github.com/mariozechner/pi-coding-agent) 进行自然语音交互。支持语音唤醒、语音指令、流式 TTS 播报、语音打断等。

## ✨ 特性

- **语音唤醒**：说"小乐小乐"唤醒，支持模糊语音匹配（享乐/向乐/想乐等变体）
- **自然对话**：语音下达指令，AI 助手执行并语音播报结果
- **流式播报**：Agent 回复实时切句合成播放，减少等待
- **语音打断**：播报过程中说"停止"立即中断
- **指令排队**：Agent 处理中识别到新指令自动排队，完成后依次执行
- **蓝牙 / 本地双模式**：自动检测蓝牙耳机（HFP+A2DP）或本地麦克风+扬声器
- **全双工 / 半双工自适应**：本地设备全双工，蓝牙一体设备自动切半双工
- **并发合成 + 语句合并**：多线程 TTS 合成，相邻逗号短句合并提升语气连贯性
- **TTS 预缓存**：常用回复（"好的"、"我在"等）预合成并持久化到磁盘

## 🏗️ 架构

```
┌─────────┐    ┌──────────┐    ┌──────────────┐    ┌───────────┐
│ 麦克风   │───→│ ASR 引擎  │───→│ 会话状态机    │───→│ Pi Agent  │
│ (HFP)   │    │ SenseVoice│    │ 唤醒/指令/休眠 │    │ (RPC)     │
└─────────┘    │ + VAD     │    └──────────────┘    └─────┬─────┘
               └──────────┘                               │
┌─────────┐    ┌──────────┐    ┌──────────────┐           │
│ 扬声器   │←───│ TTS 引擎  │←───│ 流式播放管线  │←──────────┘
│ (A2DP)  │    │ edge-tts  │    │ 并发合成+FIFO │
└─────────┘    └──────────┘    └──────────────┘
```

## 📦 安装

> ✨ 想快速上手？看 [QUICK_START.md](QUICK_START.md)

### 前置条件

- Python 3.10+
- Node.js 18+（Pi Agent 依赖）
- Windows 10/11（音频设备管理依赖 Windows API）
- 麦克风 + 扬声器（或蓝牙耳机）

### 1. 克隆项目

```bash
git clone https://github.com/<your-username>/voice-agent.git
cd voice-agent
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 安装 Node.js 依赖（Pi Agent）

```bash
npm install
```

### 4. 下载模型

ASR 模型（SenseVoice + VAD）会在首次运行时自动提示下载路径，也可手动下载：

```bash
# 创建模型目录
mkdir models

# SenseVoice 中文 ASR 模型
# 下载: https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models
# 解压到: models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/

# Silero VAD 模型
# 下载: https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
# 放到: models/silero_vad.onnx
```

### 5. 配置 AI Provider

在项目根目录创建 Pi Agent 配置（详见 [Pi 文档](https://github.com/mariozechner/pi-coding-agent)）：

```bash
# 编辑 src/config.py 中的 PI_PROVIDER 和 PI_MODEL
```

## 🚀 启动

```bash
# 方式一：命令行启动
set PYTHONIOENCODING=utf-8 && python -X utf8 src/main.py

# 方式二：使用启动脚本（自动重启）
start.bat
```

## 🎙️ 使用方法

| 操作 | 说法 | 说明 |
|------|------|------|
| 唤醒 | "小乐小乐" | 从休眠进入活跃状态 |
| 下达指令 | "小乐，帮我查天气" | 唤醒 + 指令一步到位 |
| 上下文关联 | "小乐"（停顿）"帮我查天气" | 先唤醒，再说指令 |
| 结束输入 | 说"好了"或等待 5 秒静音 | 触发指令发送 |
| 打断播报 | "停止" | 立即中断 Agent 回复 |
| 休眠 | "小乐小乐退下" | 进入休眠状态 |

## ⚙️ 配置

编辑 `src/config.py`：

```python
# 音频设备（None = 自动检测）
A2DP_ID = None          # 输出设备 ID
HFP_IN = None           # 输入设备 ID
PREFER_LOCAL = True     # 优先使用本地设备（跳过蓝牙）
DUPLEX_MODE = None      # 全双工模式（None = 自动检测）

# TTS
TTS_VOICE = "xiaoxiao"  # 语音：xiaoxiao / yunxi / xiaoyi / yunjian
TTS_RATE = "+10%"       # 语速

# 会话
INPUT_SILENCE_TIMEOUT = 5.0  # 静音超时（秒）
AUTO_SLEEP_TIMEOUT = 0       # 自动休眠（0 = 禁用）
MAX_MERGE_CLAUSES = 2        # 最大合并短句数

# Agent
PI_WORKING_DIR = "."
PI_PROVIDER = "claude-proxy"
PI_MODEL = "claude-opus-4-6"
```

## 📁 项目结构

```
voice-agent/
├── src/
│   ├── main.py               # 主程序：启动、音频播放、指令处理
│   ├── config.py              # 全局配置
│   ├── asr_engine.py          # ASR 引擎：SenseVoice + VAD，异步识别
│   ├── tts_engine.py          # TTS 引擎：edge-tts，预缓存 + 磁盘持久化
│   ├── audio_io.py            # 音频 I/O：录音、设备检测、双工检测、重采样
│   ├── session_controller.py  # 会话状态机：唤醒 / 活跃 / 处理中 / 休眠
│   └── pi_client.py           # Pi Agent RPC 客户端
├── models/                    # ASR/VAD 模型（需手动下载）
├── cache/tts/                 # TTS 音频缓存（自动生成）
├── tests/                     # 测试脚本
├── start.bat                  # Windows 启动脚本（自动重启）
├── requirements.txt           # Python 依赖
├── package.json               # Node.js 依赖（Pi Agent）
└── README.md
```

## 🔧 技术细节

### 音频设备检测策略

自动检测按优先级尝试：
1. **蓝牙一体**：同一蓝牙设备的 HFP 输入 + A2DP Stereo 输出（半双工）
2. **蓝牙分体**：不同蓝牙设备的 HFP + Stereo
3. **蓝牙 + 本地混合**：本地麦克风 + 蓝牙 A2DP 输出（全双工）
4. **纯本地**：本地麦克风 + 本地扬声器（全双工）

API 优先级：DirectSound > MME > WASAPI（跳过 WDM-KS）

### TTS 播放管线

1. Agent 流式返回文本 → 按标点切句（逗号切短句，句号切长句）
2. 每个短句独立合成 + 相邻短句合并合成（最多 MAX_MERGE_CLAUSES 个）
3. FIFO 顺序播放，优先选最长已就绪的合并音频
4. 首 2 句不等合并直接播放，减少首次响应延迟

### 唤醒词匹配

- "小乐小乐" 及其语音变体（享乐/向乐/想乐/响乐等 ASR 常见误识别）
- 任意 "X乐X乐" 模式匹配
- 支持 "乐" 前缀截断识别（ASR 截掉了"小"字）
- 上下文关联：先说"小乐"停顿，5 秒内说的下一句自动关联为指令

## 📄 许可证

MIT License
