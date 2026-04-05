"""
ASR 语音输入测试 — 先播报提示，然后录音5秒，送 ASR 识别
"""
import sys, os, time, io
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
import sounddevice as sd
from scipy.signal import resample as scipy_resample
from tts_engine import TTSEngine
from asr_engine import ASREngine

# 设备配置
a2dp_id = 11   # A2DP Stereo 输出
a2dp_sr = 44100
hfp_in = 9     # HFP 麦克风输入 (DirectSound)
hfp_in_sr = 44100

# 先用 TTS 提示用户说话
tts = TTSEngine(voice="xiaoxiao", rate="+10%")
prompt_text = "请现在对着耳机麦克风说一句话，比如说你好。"
print(f"播放提示: {prompt_text}")
audio = tts.synthesize(prompt_text)
if audio is not None:
    audio_out = scipy_resample(audio, int(len(audio) * a2dp_sr / 24000)).astype(np.float32)
    sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
    sd.wait()

time.sleep(0.5)

# 初始化 ASR
print("\n初始化 ASR...")
asr = ASREngine()
asr.init()

# 录音 5 秒
record_seconds = 8
print(f"\n开始录音 {record_seconds} 秒 (设备 #{hfp_in} @ {hfp_in_sr}Hz)...")

try:
    recording = sd.rec(int(record_seconds * hfp_in_sr), samplerate=hfp_in_sr, channels=1,
                       dtype='float32', device=hfp_in)
    sd.wait()
    print(f"录音完成: {recording.shape}, max={np.max(np.abs(recording)):.4f}")

    # 重采样到 16kHz
    audio_16k = scipy_resample(recording[:, 0], int(len(recording) * 16000 / hfp_in_sr)).astype(np.float32)
    print(f"重采样到 16kHz: {len(audio_16k)} samples")

    # 分块送入 ASR
    results = []
    def on_partial(text):
        print(f"  [部分] {text}")
    def on_final(text):
        print(f"  [最终] {text}")
        results.append(text)

    asr.set_callbacks(on_partial=on_partial, on_final=on_final)

    chunk_size = 1600  # 100ms @ 16kHz
    for i in range(0, len(audio_16k), chunk_size):
        chunk = audio_16k[i:i+chunk_size]
        asr.feed_audio(chunk)

    # 送一些静音触发端点检测
    silence = np.zeros(16000 * 3, dtype=np.float32)  # 3秒静音
    for i in range(0, len(silence), chunk_size):
        chunk = silence[i:i+chunk_size]
        asr.feed_audio(chunk)

    if results:
        print(f"\n✅ ASR 识别结果: {results}")
    else:
        print(f"\n⚠ 未检测到最终结果")
        print(f"  当前部分文本: '{asr.get_current_text()}'")
        print(f"  录音音量 max={np.max(np.abs(recording)):.6f}")
        if np.max(np.abs(recording)) < 0.01:
            print("  ⚠ 录音音量非常低，可能麦克风没有工作")

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
