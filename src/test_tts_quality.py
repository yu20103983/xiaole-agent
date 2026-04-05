"""
TTS 声音质量测试 — 测试不同内容
"""
import sys, os, time, io
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
import sounddevice as sd
from scipy.signal import resample as scipy_resample
from tts_engine import TTSEngine

# A2DP Stereo 设备
a2dp_id = 11
a2dp_sr = 44100

tts = TTSEngine(voice="xiaoxiao", rate="+10%")

text = "语音输出测试成功。现在请你对着耳机麦克风说话，我将测试语音输入功能。请说任意一句话。"
print(f"合成: {text}")

audio = tts.synthesize(text)
if audio is not None:
    print(f"合成完成: {len(audio)/24000:.1f}s")
    audio_out = scipy_resample(audio, int(len(audio) * a2dp_sr / 24000)).astype(np.float32)
    print("播放中...")
    sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
    sd.wait()
    print("播放完成!")
else:
    print("合成失败!")
