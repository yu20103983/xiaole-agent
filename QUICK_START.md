# 🚀 快速上手

从零开始，5 分钟让小乐跑起来。

---

## 第一步：检查环境

确认以下工具已安装：

```bash
python --version   # 需要 3.10+
node --version     # 需要 18+
```

> **没有 Python？** → [下载 Python](https://www.python.org/downloads/)（安装时勾选 "Add to PATH"）
>
> **没有 Node.js？** → [下载 Node.js](https://nodejs.org/)（选 LTS 版本）

## 第二步：下载项目

```bash
git clone https://github.com/yu20103983/xiaole-agent.git
cd xiaole-agent
```

## 第三步：一键安装

```bash
setup.bat
```

这会自动完成：
1. ✅ 安装 Python 依赖（sherpa-onnx、sounddevice 等）
2. ✅ 安装 Node.js 依赖（Pi Agent）
3. ✅ 下载 ASR 和 TTS 模型（约 300MB）

> **下载模型失败？** 设置代理后重试：
> ```bash
> set HTTPS_PROXY=http://127.0.0.1:7890
> download_models.bat
> ```

## 第四步：配置 AI Provider

用文本编辑器打开 `src/config.py`，找到最后两行，改成你的 AI 配置：

```python
# ============ Agent ============
PI_PROVIDER = "anthropic"              # ← 改成你的 provider
PI_MODEL = "claude-sonnet-4-20250514"  # ← 改成你的模型
```

### 常用 Provider 配置

<details>
<summary><b>Anthropic（官方直连）</b></summary>

1. 获取 API Key：https://console.anthropic.com/
2. 设置环境变量：
   ```bash
   set ANTHROPIC_API_KEY=sk-ant-xxxxx
   ```
3. 配置：
   ```python
   PI_PROVIDER = "anthropic"
   PI_MODEL = "claude-sonnet-4-20250514"
   ```
</details>

<details>
<summary><b>OpenAI</b></summary>

1. 获取 API Key：https://platform.openai.com/
2. 设置环境变量：
   ```bash
   set OPENAI_API_KEY=sk-xxxxx
   ```
3. 配置：
   ```python
   PI_PROVIDER = "openai"
   PI_MODEL = "gpt-4o"
   ```
</details>

<details>
<summary><b>自定义代理 / 中转</b></summary>

在 `~/.pi/agent/models.json` 中添加自定义 provider：

```json
{
  "providers": [
    {
      "id": "my-proxy",
      "name": "My Proxy",
      "type": "anthropic",
      "baseUrl": "http://localhost:8787",
      "models": [
        { "id": "claude-sonnet-4-20250514", "name": "Claude Sonnet" }
      ]
    }
  ]
}
```

然后配置：
```python
PI_PROVIDER = "my-proxy"
PI_MODEL = "claude-sonnet-4-20250514"
```
</details>

## 第五步：启动

```bash
start.bat
```

或命令行启动：

```bash
python -X utf8 src/main.py
```

看到以下输出说明启动成功：

```
[Init] ✅ 就绪

等待语音输入...
```

## 第六步：开始对话！

| 你说 | 小乐回应 |
|------|----------|
| "小乐小乐" | "我在，请说" |
| "帮我查一下今天天气" | "好的，我来查一下..." |
| "终止" | "好的，已终止"（打断播报） |
| "小乐退下" | "好的，再见"（休眠） |

### 💡 使用技巧

- **一步到位**：直接说"小乐帮我查天气"，不用先唤醒再说指令
- **快速发送**：说完指令后说"好了"，不用等 4 秒静音超时
- **连续对话**：说"我们聊聊天"，之后不用每次说"小乐"
- **语音打断**：播报过程中说"终止"立即停止

---

## ❓ 常见问题

### 没有声音输出

编辑 `src/config.py`，设置 `PREFER_LOCAL = True` 强制使用本地扬声器。

### 识别不到"小乐"唤醒词

- 确保麦克风正常工作（系统录音测试）
- 说清楚"小——乐——小——乐"，语速不要太快
- 支持近音变体：享乐、向乐、想乐、响乐等

### 蓝牙耳机输入输出冲突

Windows 下蓝牙 HFP（输入）+ A2DP（输出）不能同时工作，系统会自动切换为半双工模式（说话时暂停播放）。

### Agent 响应超时

- 检查 AI Provider 的 API Key 是否正确
- 检查网络是否能访问 AI 服务
- 查看终端输出的错误信息

### 模型下载失败

国内网络可能无法直接访问 GitHub，设置代理后重试：

```bash
set HTTP_PROXY=http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890
download_models.bat
```
