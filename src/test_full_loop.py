"""
端到端测试：蓝牙HFP 麦克风 → ASR → 会话控制 → TTS → 蓝牙HFP 扬声器
不含 Pi Agent，用固定回复代替
"""
import sys, os, time, signal
sys.path.insert(0, os.path.dirname(__file__))

from audio_io import AudioRecorder, AudioPlayer, HFPKeepAlive, find_bluetooth_devices
from asr_engine import ASREngine
from tts_engine import TTSEngine
from session_controller import SessionController, SessionState

print("=" * 50)
print("  端到端语音回路测试")
print("  说 '嗨派' 唤醒, 然后说话")
print("  Ctrl+C 退出")
print("=" * 50)

# 设备
input_id, output_id, info = find_bluetooth_devices()
input_sr = info.get('input_sr', 44100)
output_sr = info.get('output_sr', 44100)
print(f"HFP 输入: #{input_id} @ {input_sr}Hz")
print(f"HFP 输出: #{output_id} @ {output_sr}Hz")

# 初始化
keepalive = HFPKeepAlive(device_id=output_id, sample_rate=output_sr)
keepalive.start()

asr = ASREngine()
asr.init()

tts = TTSEngine(voice="xiaoxiao", rate="+10%")
player = AudioPlayer(device_id=output_id, sample_rate=output_sr)
session = SessionController()
recorder = AudioRecorder(device_id=input_id, sample_rate=input_sr, target_sr=16000)

running = True

def speak(text):
    """TTS 播报"""
    global recorder
    print(f"[TTS] {text}")
    recorder.stop()
    keepalive.stop()
    audio = tts.synthesize(text)
    if audio is not None:
        player.play(audio, sample_rate=24000, blocking=True)
        time.sleep(0.2)
    keepalive.start()
    recorder.start(callback=lambda data: asr.feed_audio(data))

def on_wake():
    speak("我在，请说")

def on_sleep():
    speak("好的，再见")

def on_command(cmd):
    print(f"[指令] {cmd}")
    # 模拟 Pi 回复
    reply = f"你说的是{cmd}，这是一个测试回复"
    speak(reply)
    session.set_state(SessionState.ACTIVE)

session.set_callbacks(on_wake=on_wake, on_sleep=on_sleep, on_command=on_command)

asr.set_callbacks(
    on_partial=lambda t: (
        print(f"\r  [识别] {t}    ", end="", flush=True),
        session.process_text(t, is_final=False)
        if session.state in (SessionState.SLEEPING, SessionState.ACTIVE) else None
    ),
    on_final=lambda t: (
        print(f"\n  [最终] {t}"),
        session.process_text(t, is_final=True)
    )
)

# 启动
recorder.start(callback=lambda data: asr.feed_audio(data))
speak("语音助手已启动，说嗨派唤醒我")

print("\n等待语音输入...\n")
signal.signal(signal.SIGINT, lambda s, f: globals().__setitem__('running', False))

try:
    while running:
        time.sleep(0.5)
except KeyboardInterrupt:
    pass

recorder.stop()
keepalive.stop()
print("测试结束")
