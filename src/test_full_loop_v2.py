"""
端到端语音回路测试（修复版）
TTS 走 A2DP Stereo，录音走 HFP
Mock Agent 回复
"""
import sys, os, io, time, signal, threading
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import sounddevice as sd
from scipy.signal import resample as scipy_resample
from audio_io import AudioRecorder, find_bluetooth_devices
from asr_engine import ASREngine
from tts_engine import TTSEngine
from session_controller import SessionController, SessionState

# ============ 设备配置 ============
a2dp_id = 11; a2dp_sr = 44100   # A2DP Stereo 输出 (TTS)
hfp_in = 9; hfp_in_sr = 44100   # HFP 麦克风输入

print("=" * 50)
print("  端到端语音回路测试 (A2DP TTS)")
print("  说 '嗨派' 唤醒, 然后说话")
print("  说 '休息派' 休眠")
print("  Ctrl+C 退出")
print("=" * 50)

# ============ 初始化 ============
print("\n初始化 ASR...")
asr = ASREngine()
asr.init()

tts = TTSEngine(voice="xiaoxiao", rate="+10%")
session = SessionController()
recorder = AudioRecorder(device_id=hfp_in, sample_rate=hfp_in_sr, target_sr=16000,
                         block_size=hfp_in_sr // 10)

running = True
speaking = False

def speak(text):
    """TTS 播报 — 停录音 → A2DP 播放 → 恢复录音"""
    global speaking
    if not text:
        return
    speaking = True
    print(f"[TTS] {text}")
    
    # 停止录音
    recorder.stop()
    asr.reset()
    time.sleep(0.1)
    
    try:
        audio = tts.synthesize(text)
        if audio is not None:
            audio_out = scipy_resample(
                audio, int(len(audio) * a2dp_sr / 24000)
            ).astype(np.float32)
            sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
            sd.wait()
    except Exception as e:
        print(f"[TTS Error] {e}")
    
    time.sleep(0.3)
    speaking = False
    # 恢复录音
    asr.reset()
    recorder.start(callback=lambda data: asr.feed_audio(data))

def on_wake():
    speak("我在，请说")

def on_sleep():
    speak("好的，再见")

def on_command(cmd):
    print(f"\n[指令] {cmd}")
    # Mock Agent 回复
    reply = f"你说的是：{cmd}。这是模拟回复，真正的派还没接入。"
    speak(reply)
    session.set_state(SessionState.ACTIVE)

session.set_callbacks(on_wake=on_wake, on_sleep=on_sleep, on_command=on_command)

def on_partial(text):
    if speaking:
        return
    print(f"\r  [识别] {text}        ", end="", flush=True)
    if session.state in (SessionState.SLEEPING, SessionState.ACTIVE):
        session.process_text(text, is_final=False)

def on_final(text):
    if speaking:
        return
    print(f"\n  [最终] {text}")
    session.process_text(text, is_final=True)

asr.set_callbacks(on_partial=on_partial, on_final=on_final)

# ============ 启动 ============
# 先启动录音
recorder.start(callback=lambda data: asr.feed_audio(data))
# 播放欢迎语
speak("语音助手已启动，说嗨派唤醒我")

print("\n等待语音输入...\n")

try:
    while running:
        time.sleep(0.5)
except KeyboardInterrupt:
    pass

recorder.stop()
print("测试结束")
