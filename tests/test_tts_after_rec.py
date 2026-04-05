"""
测试：模拟唤醒后播放 TTS 的场景
先启动录音，然后停止录音，再播 TTS
"""
import sys, os, time
import numpy as np
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, os.path.dirname(__file__))

import sounddevice as sd
from scipy.signal import resample as scipy_resample
from audio_io import AudioRecorder
from tts_engine import TTSEngine

a2dp_id = 11; a2dp_sr = 44100
hfp_in = 9; hfp_in_sr = 44100

tts = TTSEngine(voice="xiaoxiao", rate="+10%")
recorder = AudioRecorder(device_id=hfp_in, sample_rate=hfp_in_sr, target_sr=16000,
                         block_size=hfp_in_sr // 10)

def play_tts(text):
    print(f"[TTS] {text}")
    audio = tts.synthesize(text)
    if audio is None:
        print("  合成失败!")
        return
    print(f"  合成完成: {len(audio)} samples")
    audio_out = scipy_resample(audio, int(len(audio) * a2dp_sr / 24000)).astype(np.float32)
    # 加前导静音
    pad = np.zeros(int(a2dp_sr * 0.5), dtype=np.float32)
    audio_out = np.concatenate([pad, audio_out])
    print(f"  播放: device={a2dp_id}, sr={a2dp_sr}, len={len(audio_out)}, max={np.max(np.abs(audio_out)):.4f}")
    sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
    sd.wait()
    print("  播放完成")

# 测试1：直接播放（之前验证过OK）
print("\n=== 测试1: 直接播放 ===")
play_tts("测试一，直接播放。")
time.sleep(1)

# 测试2：启动录音 → 停止录音 → 播放（模拟唤醒场景）
print("\n=== 测试2: 录音后播放 ===")
print("启动录音...")
recorder.start(callback=lambda data: None)
time.sleep(2)
print("停止录音...")
recorder.stop()
time.sleep(0.3)
play_tts("测试二，录音停止后播放。")
time.sleep(1)

# 测试3：录音 → 停止 → 更长等待 → 播放
print("\n=== 测试3: 录音后等1秒再播放 ===")
recorder.start(callback=lambda data: None)
time.sleep(2)
recorder.stop()
time.sleep(1.0)
play_tts("测试三，等一秒后播放。")

print("\n所有测试完成")
