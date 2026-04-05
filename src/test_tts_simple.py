"""
简单 TTS 输出测试 — 通过 A2DP Stereo 播放
"""
import sys, os, time, io
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
import sounddevice as sd
from scipy.signal import resample as scipy_resample
from tts_engine import TTSEngine

# 找到 A2DP Stereo 输出设备
devices = sd.query_devices()
a2dp_id = None
a2dp_sr = 44100
for i, d in enumerate(devices):
    if '漫步者' in d['name'] and 'Stereo' in d['name'] and d['max_output_channels'] > 0:
        hostapi = sd.query_hostapis(d['hostapi'])['name']
        if 'DirectSound' in hostapi:
            a2dp_id = i
            a2dp_sr = int(d['default_samplerate'])
            print(f"A2DP Stereo: #{i} [{hostapi}] {d['name']} @ {a2dp_sr}Hz")
            break

if a2dp_id is None:
    print("未找到 A2DP Stereo 设备，使用默认输出")
    a2dp_id = sd.default.device[1]

# 初始化 TTS
tts = TTSEngine(voice="xiaoxiao", rate="+10%")

text = "你好，这是语音输出测试。如果你能听到这段话，说明语音输出正常。"
print(f"合成中: {text}")

audio = tts.synthesize(text)
if audio is not None:
    print(f"合成完成: {len(audio)} samples, {len(audio)/24000:.1f}s")
    # 重采样到设备采样率
    audio_out = scipy_resample(audio, int(len(audio) * a2dp_sr / 24000)).astype(np.float32)
    print(f"重采样: {len(audio_out)} samples @ {a2dp_sr}Hz")
    print(f"播放中 (设备 #{a2dp_id})...")
    sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
    sd.wait()
    print("播放完成!")
else:
    print("TTS 合成失败!")
