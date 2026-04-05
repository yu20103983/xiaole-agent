"""
ASR 引擎调试 — 用模型自带 wav 验证
"""
import sys, os, io, time
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import wave
from asr_engine import ASREngine

print("初始化 ASR...")
asr = ASREngine()
asr.init()
print("ASR 就绪")

# 只测一个文件
wav_path = os.path.join(asr.model_dir, "test_wavs", "0.wav")
print(f"\n测试文件: {wav_path}")

with wave.open(wav_path, 'rb') as wf:
    sr = wf.getframerate()
    ch = wf.getnchannels()
    n = wf.getnframes()
    frames = wf.readframes(n)
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio[::ch]
    print(f"采样率: {sr}Hz, 通道: {ch}, 长度: {len(audio)/sr:.1f}s, max: {np.max(np.abs(audio)):.4f}")

# 如果不是16kHz需要重采样
if sr != 16000:
    from scipy.signal import resample as scipy_resample
    audio = scipy_resample(audio, int(len(audio) * 16000 / sr)).astype(np.float32)
    print(f"重采样到 16kHz: {len(audio)} samples")

# 分块送入
print("\n送入音频...")
chunk_size = 3200  # 200ms
for i in range(0, len(audio), chunk_size):
    chunk = audio[i:i+chunk_size]
    asr.stream.accept_waveform(16000, chunk)

print("解码中...")
t0 = time.time()
while asr.recognizer.is_ready(asr.stream):
    asr.recognizer.decode_stream(asr.stream)
    if time.time() - t0 > 10:
        print("解码超时!")
        break

result = asr.recognizer.get_result(asr.stream)
text = result.text if hasattr(result, 'text') else str(result)
print(f"识别结果: '{text.strip()}'")
print(f"是否端点: {asr.recognizer.is_endpoint(asr.stream)}")

# 送静音
print("\n送入3秒静音触发端点...")
silence = np.zeros(16000 * 3, dtype=np.float32)
for i in range(0, len(silence), chunk_size):
    asr.stream.accept_waveform(16000, silence[i:i+chunk_size])

t0 = time.time()
while asr.recognizer.is_ready(asr.stream):
    asr.recognizer.decode_stream(asr.stream)
    if time.time() - t0 > 10:
        print("解码超时!")
        break

result = asr.recognizer.get_result(asr.stream)
text = result.text if hasattr(result, 'text') else str(result)
print(f"静音后结果: '{text.strip()}'")
print(f"是否端点: {asr.recognizer.is_endpoint(asr.stream)}")

print("\n完成")
