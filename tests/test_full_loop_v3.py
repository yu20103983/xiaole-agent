"""
端到端语音回路测试（SenseVoice 版）
TTS 走 A2DP Stereo，录音走 HFP
VAD + SenseVoice 识别
修复：speak 在独立线程执行，避免在录音回调中死锁
"""
import sys, os, time, signal, threading
import numpy as np
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, os.path.dirname(__file__))

import sounddevice as sd
from scipy.signal import resample as scipy_resample
from audio_io import AudioRecorder
from asr_engine import ASREngine
from tts_engine import TTSEngine
from session_controller import SessionController, SessionState

# ============ 设备配置 ============
a2dp_id = 11; a2dp_sr = 44100
hfp_in = 9; hfp_in_sr = 44100

print("=" * 50)
print("  端到端语音回路测试 (SenseVoice)")
print("  说 '小派你好' 唤醒, 然后说 '小派，xxx'")
print("  说 '小派退下' 休眠")
print("  Ctrl+C 退出")
print("=" * 50)

# ============ 初始化 ============
print("\n初始化 ASR (SenseVoice)...")
asr = ASREngine()
asr.init()

tts = TTSEngine(voice="xiaoxiao", rate="+10%")
session = SessionController()
recorder = AudioRecorder(device_id=hfp_in, sample_rate=hfp_in_sr, target_sr=16000,
                         block_size=hfp_in_sr // 10)

running = True
speaking = False
speak_lock = threading.Lock()

def _do_speak(text, then_state=None):
    """实际 TTS 播报（在独立线程中执行）"""
    global speaking
    with speak_lock:
        speaking = True
        print(f"[TTS] {text}", flush=True)
        recorder.stop()
        time.sleep(0.1)
        try:
            audio = tts.synthesize(text)
            if audio is not None:
                audio_out = scipy_resample(
                    audio, int(len(audio) * a2dp_sr / 24000)
                ).astype(np.float32)
                # 加 0.5s 前导静音，给 A2DP 切换时间
                pad = np.zeros(int(a2dp_sr * 0.5), dtype=np.float32)
                audio_out = np.concatenate([pad, audio_out])
                sd.play(audio_out, samplerate=a2dp_sr, device=a2dp_id)
                sd.wait()
            else:
                print("[TTS] 合成失败", flush=True)
        except Exception as e:
            print(f"[TTS Error] {e}", flush=True)
        time.sleep(0.3)
        speaking = False
        if then_state:
            session.set_state(then_state)
        asr.reset()
        recorder.start(callback=feed_audio)

def speak(text, then_state=None):
    """TTS 播报（提交到独立线程，避免在回调中死锁）"""
    threading.Thread(target=_do_speak, args=(text, then_state), daemon=True).start()

def feed_audio(data):
    if not speaking:
        asr.feed_audio(data)

def on_wake():
    speak("我在，请说")

def on_sleep():
    speak("好的，再见")

def on_command(cmd):
    print(f"\n[指令] {cmd}", flush=True)
    reply = f"你说的是：{cmd}。这是模拟回复。"
    speak(reply, then_state=SessionState.ACTIVE)

session.set_callbacks(on_wake=on_wake, on_sleep=on_sleep, on_command=on_command)

def on_final(text):
    if speaking:
        return
    print(f"\n  [识别] {text}", flush=True)
    session.process_text(text, is_final=True)

asr.set_callbacks(on_final=on_final)

# ============ 启动 ============
# 欢迎语直接在主线程播放（此时没有录音回调冲突）
recorder.start(callback=feed_audio)
_do_speak("语音助手已启动，说小派你好唤醒我")

print("\n等待语音输入...\n", flush=True)

try:
    while running:
        time.sleep(0.5)
except KeyboardInterrupt:
    pass

recorder.stop()
print("测试结束")
