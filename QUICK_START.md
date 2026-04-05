# 快速上手

## 1. 环境要求

- Windows 10/11
- Python 3.10+
- Node.js 18+
- 麦克风 + 扬声器（或蓝牙耳机）

## 2. 一键安装

```bash
git clone https://github.com/<your-username>/xiaole-agent.git
cd xiaole-agent
setup.bat
```

`setup.bat` 会自动完成：安装 Python 依赖 → 安装 Node.js 依赖 → 下载 ASR 模型

## 3. 配置 AI Provider

编辑 `src/config.py`，设置你的 AI provider：

```python
PI_PROVIDER = "claude-proxy"      # 改成你的 provider
PI_MODEL = "claude-opus-4-6"      # 改成你的模型
```

> 详见 [Pi Agent 文档](https://github.com/mariozechner/pi-coding-agent) 了解可用的 provider 配置

## 4. 启动

双击 `start.bat`，或命令行运行：

```bash
set PYTHONIOENCODING=utf-8 && python -X utf8 src/main.py
```

## 5. 开始对话

```
你：  "小乐小乐"              → 唤醒
小乐：  "我在，请说"

你：  "小乐，今天天气怎么样"   → 下达指令（等 5 秒静音自动发送）
小乐：  "好的，我来查一下……"

你：  "停止"                   → 打断播报

你：  "小乐小乐退下"           → 休眠
小乐：  "好的，再见"
```

**提示：**
- 说"好了"可以立即发送指令，不用等 5 秒
- 可以直接说"小乐帮我查天气"，唤醒和指令一步到位
- Agent 处理中说新指令会自动排队，处理完后依次执行

## 常见问题

### 没有声音输出
编辑 `src/config.py`，设置 `PREFER_LOCAL = True` 强制使用本地扬声器

### 模型下载失败
设置代理后重新运行 `download_models.bat`：
```bash
set HTTPS_PROXY=http://127.0.0.1:7890
download_models.bat
```

### 蓝牙耳机输入输出冲突
Windows 下蓝牙 HFP + A2DP 不能同时工作，系统会自动切换为半双工模式
