"""
用模型自带的测试 wav 文件验证 ASR 引擎
"""
import sys, os, io
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import wave
from asr_engine import ASREngine

asr = ASREngine()
asr.init()

results = []
def on_partial(text):
    print(f"  [部分] {text}")
def on_final(text):
    print(f"  [最终] {text}")
    results.append(text)

asr.set_callbacks(on_partial=on_partial, on_final=on_final)

# 测试模型自带的 wav
test_dir = os.path.join(asr.model_dir, "test_wavs")
for wav_file in sorted(os.listdir(test_dir)):
    if not wav_file.endswith('.wav'):
        continue
    wav_path = os.path.join(test_dir, wav_file)
    print(f"\n--- 测试: {wav_file} ---")
    
    with wave.open(wav_path, 'rb') as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if ch > 1:
            audio = audio[::ch]
        print(f"  采样率: {sr}Hz, 长度: {len(audio)/sr:.1f}s, max: {np.max(np.abs(audio)):.4f}")
    
    # 如果不是16kHz需要重采样
    if sr != 16000:
        from scipy.signal import resample as scipy_resample
        audio = scipy_resample(audio, int(len(audio) * 16000 / sr)).astype(np.float32)
        print(f"  重采样到 16kHz: {len(audio)} samples")
    
    asr.reset()
    results.clear()
    
    chunk_size = 1600
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i:i+chunk_size]
        asr.feed_audio(chunk)
    
    # 送静音触发端点
    silence = np.zeros(16000 * 3, dtype=np.float32)
    for i in range(0, len(silence), chunk_size):
        asr.feed_audio(silence[i:i+chunk_size])
    
    if not results:
        print(f"  当前部分文本: '{asr.get_current_text()}'")

print("\n=== 测试完成 ===")
