"""
语音助手全局配置
"""

# ============ 音频设备 ============
# 设为 None 时自动检测蓝牙/本地设备
A2DP_ID = None            # A2DP 输出设备 ID (None=自动)
A2DP_SR = None            # A2DP 采样率 (None=自动)
HFP_IN = None             # HFP 输入设备 ID (None=自动)
HFP_IN_SR = None          # HFP 输入采样率 (None=自动)

# ============ TTS ============
TTS_VOICE = "xiaoxiao"    # TTS 语音：xiaoxiao/yunxi/xiaoyi/yunjian
TTS_RATE = "+10%"         # TTS 语速

# ============ 播放管线 ============
MAX_MERGE_CLAUSES = 2     # 最多合并逗号短句数（TTS文本层面合并，提升语气连贯性）
INPUT_SILENCE_TIMEOUT = 3.0  # 普通模式：N秒无新输入后发送指令

# ============ 会话 ============
AUTO_SLEEP_TIMEOUT = 120  # 无活动自动休眠秒数

# ============ Agent ============
PI_WORKING_DIR = "D:/workdir/voice_agent"
PI_PROVIDER = "claude-proxy"
PI_MODEL = "claude-opus-4-6"
