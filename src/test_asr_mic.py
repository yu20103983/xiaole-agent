"""
ASR + 麦克风录音测试 — 录8秒后手动解码
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

# 设备
a2dp_id = 11; a2dp_sr = 44100
hfp_in = 9; hfp_in_sr = 44100

# TTS 提示
tts = TTSEngine(voice="xiaoxiao", rate="+10%")
audio = tts.synthesize("请现在说一句话，比如今天天气怎么样。")
if audio is not None:
    from scipy.signal import resample as scipy_resample
    audio_out = scipy_resample(audio, int(len(audio) * a2dp_sr / 24000)).astype(np.float32)
    sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
    sd.wait()

time.sleep(0.3)

# 录音
print("开始录音 8 秒...")
recording = sd.rec(int(8 * hfp_in_sr), samplerate=hfp_in_sr, channels=1,
                   dtype='float32', device=hfp_in)
sd.wait()
audio_mono = recording[:, 0]
print(f"录音完成: max={np.max(np.abs(audio_mono)):.4f}, len={len(audio_mono)}")

# 重采样到 16kHz
audio_16k = scipy_resample(audio_mono, int(len(audio_mono) * 16000 / hfp_in_sr)).astype(np.float32)
print(f"重采样: {len(audio_16k)} samples @ 16kHz")

# ASR
print("\n初始化 ASR...")
asr = ASREngine()
asr.init()

# 直接操作底层，不经过 feed_audio
print("送入录音数据...")
chunk_size = 3200
for i in range(0, len(audio_16k), chunk_size):
    chunk = audio_16k[i:i+chunk_size]
    asr.stream.accept_waveform(16000, chunk)

print("解码中...")
t0 = time.time()
count = 0
while asr.recognizer.is_ready(asr.stream):
    asr.recognizer.decode_stream(asr.stream)
    count += 1
    if time.time() - t0 > 15:
        print("超时!")
        break

result = asr.recognizer.get_result(asr.stream)
text = result.text.strip() if hasattr(result, 'text') else str(result).strip()
print(f"音频解码 {count} 次, 结果: '{text}'")

# 送静音
print("送静音...")
silence = np.zeros(16000 * 3, dtype=np.float32)
for i in range(0, len(silence), chunk_size):
    asr.stream.accept_waveform(16000, silence[i:i+chunk_size])
t0 = time.time()
while asr.recognizer.is_ready(asr.stream):
    asr.recognizer.decode_stream(asr.stream)
    if time.time() - t0 > 10:
        break

result = asr.recognizer.get_result(asr.stream)
text = result.text.strip() if hasattr(result, 'text') else str(result).strip()
print(f"最终结果: '{text}'")
print(f"端点: {asr.recognizer.is_endpoint(asr.stream)}")

# 播报结果
if text:
    reply = f"识别结果是：{text}"
    print(f"\n播报: {reply}")
    audio = tts.synthesize(reply)
    if audio is not None:
        audio_out = scipy_resample(audio, int(len(audio) * a2dp_sr / 24000)).astype(np.float32)
        sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
        sd.wait()
else:
    print("未识别到内容")
    # 保存录音用于分析
    import wave
    with wave.open("D:/workdir/voice_agent/debug_recording.wav", 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes((audio_16k * 32767).astype(np.int16).tobytes())
    print("录音已保存到 debug_recording.wav")
