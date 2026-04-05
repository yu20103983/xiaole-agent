"""
语音助手全局配置
"""

# ============ 音频设备 ============
# 设为 None 时自动检测蓝牙/本地设备
A2DP_ID = None            # 输出设备 [设None自动检测]
A2DP_SR = None            # 输出采样率
HFP_IN = None             # 输入设备 [设None自动检测]
HFP_IN_SR = None          # 输入采样率
SPLIT_IO = False          # 分离模式
DUPLEX_MODE = True        # 本地设备支持全双工
PREFER_LOCAL = True       # 跳过蓝牙，优先本地设备

# ============ TTS ============
TTS_VOICE = "xiaoxiao"    # TTS 语音：xiaoxiao/yunxi/xiaoyi/yunjian
TTS_RATE = "+10%"         # TTS 语速

# ============ 播放管线 ============
MAX_MERGE_CLAUSES = 2     # 最多合并逗号短句数（TTS文本层面合并，提升语气连贯性）
INPUT_SILENCE_TIMEOUT = 3.0  # 普通模式：N秒无新输入后发送指令

# ============ 会话 ============
AUTO_SLEEP_TIMEOUT = 0    # 无活动自动休眠秒数 (0=禁用)

# ============ Agent ============
PI_WORKING_DIR = "D:/workdir/voice_agent"
PI_PROVIDER = "claude-proxy"
PI_MODEL = "claude-opus-4-6"
