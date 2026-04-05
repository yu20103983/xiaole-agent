"""
SenseVoice + VAD 实时麦克风测试
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
print("初始化 SenseVoice ASR...")
asr = ASREngine()
asr.init()

results = []
def on_final(text):
    print(f"\n  [识别] {text}")
    results.append(text)

asr.set_callbacks(on_final=on_final)

# TTS 提示
tts = TTSEngine(voice="xiaoxiao", rate="+10%")
audio = tts.synthesize("请说一句话，我会识别并复述。")
if audio is not None:
    audio_out = scipy_resample(audio, int(len(audio) * a2dp_sr / 24000)).astype(np.float32)
    sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
    sd.wait()

time.sleep(0.5)

# 录音
recorder = AudioRecorder(device_id=hfp_in, sample_rate=hfp_in_sr, target_sr=16000,
                         block_size=hfp_in_sr // 10)
recorder.start(callback=lambda data: asr.feed_audio(data))

print("\n录音中... 请说话 (15秒后自动结束)")
t0 = time.time()
while time.time() - t0 < 15:
    time.sleep(0.1)
    if results and time.time() - t0 > 3:
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
    print("✅ 测试通过!")
else:
    print("\n❌ 未识别到语音")

print("测试完成")
