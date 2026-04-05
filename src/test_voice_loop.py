"""
集成测试：麦克风 → ASR → TTS → 扬声器 回路测试
（不含 Pi Agent，仅测试语音识别和播报）
"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))

from audio_io import AudioRecorder, AudioPlayer, find_bluetooth_devices
from asr_engine import ASREngine
from tts_engine import TTSEngine
from scipy.signal import resample as scipy_resample

print("=" * 50)
print("  语音回路测试")
print("  说话后会识别并用 TTS 复读")
print("  按 Ctrl+C 退出")
print("=" * 50)

# 初始化
input_id, output_id, info = find_bluetooth_devices()
input_sr = info.get('input_sr', 16000)
output_sr = info.get('output_sr', 44100)
print(f"输入: #{input_id} @ {input_sr}Hz")
print(f"输出: #{output_id} @ {output_sr}Hz")

asr = ASREngine()
asr.init()

tts = TTSEngine(voice="xiaoxiao", rate="+10%")
player = AudioPlayer(device_id=output_id, sample_rate=output_sr)
recorder = AudioRecorder(device_id=input_id, sample_rate=input_sr)

def on_partial(text):
    print(f"\r  [识别中] {text}    ", end="", flush=True)

def on_final(text):
    print(f"\n  [最终] {text}")
    if len(text) < 2:
        return
    # TTS 复读
    reply = f"你说的是：{text}"
    print(f"  [TTS] {reply}")
    audio = tts.synthesize(reply)
    if audio is not None:
        if output_sr != 24000:
            audio = scipy_resample(audio, int(len(audio) * output_sr / 24000)).astype(np.float32)
        player.play(audio, sample_rate=output_sr, blocking=True)

asr.set_callbacks(on_partial=on_partial, on_final=on_final)

# 启动录音
if input_sr != 16000:
    def resample_feed(data):
        resampled = scipy_resample(data, int(len(data) * 16000 / input_sr)).astype(np.float32)
        asr.feed_audio(resampled)
    recorder.start(callback=resample_feed)
else:
    recorder.start(callback=lambda data: asr.feed_audio(data))

print("\n开始说话...\n")
try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    recorder.stop()
    print("\n测试结束")
