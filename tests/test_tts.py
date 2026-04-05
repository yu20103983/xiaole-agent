"""
测试 TTS 引擎：合成并播放
运行: python -X utf8 tests/test_tts.py
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tts_engine import TTSEngine
from audio_io import auto_detect_devices, fast_resample
import sounddevice as sd


def main():
    print("=== TTS 合成播放测试 (Matcha-TTS 本地推理) ===\n")

    # 自动检测输出设备
    det = auto_detect_devices()
    out_id = det['output_id']
    out_sr = det['output_sr']
    print(f"输出设备: #{out_id} ({out_sr}Hz)\n")

    # 初始化 TTS
    tts = TTSEngine()
    print(f"模型采样率: {tts.sample_rate}Hz\n")

    texts = [
        "你好，我是小乐，很高兴为你服务。",
        "今天天气不错，适合出门走走。",
        "好的，我来帮你查一下。",
    ]

    for text in texts:
        t0 = time.time()
        audio = tts.synthesize(text)
        elapsed = time.time() - t0
        if audio is not None:
            duration = len(audio) / tts.sample_rate
            print(f"合成: {text}")
            print(f"  {elapsed:.3f}s → {duration:.2f}s (RTF={elapsed/duration:.3f})")
            out = fast_resample(audio, tts.sample_rate, out_sr)
            sd.play(out, samplerate=out_sr, device=out_id)
            sd.wait()
            time.sleep(0.3)
        else:
            print(f"合成失败: {text}")

    print("\n=== 预缓存测试 ===")
    tts.precache()
    t0 = time.time()
    audio = tts.synthesize("好的，我来查一下")
    print(f"缓存命中: {time.time()-t0:.4f}s")

    print("\n测试结束")


if __name__ == "__main__":
    main()
