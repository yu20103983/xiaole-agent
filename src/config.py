"""
语音助手全局配置
"""

# ============ 音频设备 ============
A2DP_ID = 11              # A2DP 输出设备 ID
A2DP_SR = 44100           # A2DP 采样率
HFP_IN = 9               # HFP 输入设备 ID
HFP_IN_SR = 44100        # HFP 输入采样率

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
