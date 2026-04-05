"""
实时流式 ASR 测试 — 使用录音回调实时送 ASR
先 TTS 提示，停止后再开始录音
"""
import sys, os, io, time
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import sounddevice as sd
from scipy.signal import resample as scipy_resample
from tts_engine import TTSEngine
from asr_engine import ASREngine
from audio_io import AudioRecorder

# 设备
a2dp_id = 11; a2dp_sr = 44100
hfp_in = 9; hfp_in_sr = 44100

# ASR
print("初始化 ASR...")
asr = ASREngine()
asr.init()

results = []
def on_partial(text):
    print(f"\r  [识别中] {text}        ", end="", flush=True)

def on_final(text):
    print(f"\n  [最终] {text}")
    results.append(text)

asr.set_callbacks(on_partial=on_partial, on_final=on_final)

# TTS 提示
tts = TTSEngine(voice="xiaoxiao", rate="+10%")
audio = tts.synthesize("请说一句话，我会识别并复述。")
if audio is not None:
    audio_out = scipy_resample(audio, int(len(audio) * a2dp_sr / 24000)).astype(np.float32)
    sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
    sd.wait()

time.sleep(0.5)

# 使用 AudioRecorder 流式录音
recorder = AudioRecorder(device_id=hfp_in, sample_rate=hfp_in_sr, target_sr=16000,
                         block_size=hfp_in_sr // 10)
recorder.start(callback=lambda data: asr.feed_audio(data))

print("\n录音中... 请说话 (10秒后自动结束)")
t0 = time.time()
while time.time() - t0 < 10:
    time.sleep(0.1)
    if results:
        # 识别到结果后再等2秒
        time.sleep(2)
        break

recorder.stop()

if results:
    reply = f"你说的是：{results[0]}"
    print(f"\n播报: {reply}")
    audio = tts.synthesize(reply)
    if audio is not None:
        audio_out = scipy_resample(audio, int(len(audio) * a2dp_sr / 24000)).astype(np.float32)
        sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
        sd.wait()
else:
    print("\n未识别到语音")
    print(f"部分文本: '{asr.get_current_text()}'")

print("测试完成")
