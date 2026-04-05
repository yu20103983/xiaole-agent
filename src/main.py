"""
蓝牙语音 Pi Agent — v3
1. 打断词"停止"
2. agent执行前先汇报，回复简短
3. 长输入：积累多句后再送agent；"小派我要长段输入"→等"好了"
"""
import sys, os, time, signal, threading, re, queue
import numpy as np
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, os.path.dirname(__file__))

import sounddevice as sd
from scipy.signal import resample as scipy_resample
from audio_io import AudioRecorder
from asr_engine import ASREngine
from tts_engine import TTSEngine
from pi_client import PiClient
from session_controller import SessionController, SessionState

# ============ 设备配置 ============
A2DP_ID = 11; A2DP_SR = 44100
HFP_IN = 9; HFP_IN_SR = 44100

SYSTEM_PROMPT = """你是"小派"，通过蓝牙耳机与用户语音对话的个人助理。

核心规则：
1. 回复会被TTS播放，必须简洁口语化：
   - 禁止markdown、表格、代码块、emoji、特殊符号
   - 一般回复控制在2-3句话以内
   - 列举事项不超过3条，用口语连接词而非编号
2. 执行任何操作前，先说一句话告知用户你要做什么，例如"好的，我来查一下"或"正在帮你处理"，让用户知道你在工作
3. 执行完毕后只说结果，不重复过程
4. 你有文件读写、命令执行等工具能力，但汇报时要简洁"""


def clean_for_speech(text):
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'[#*`\[\]()]', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[\U0001F600-\U0001F9FF]', '', text)
    text = re.sub(r'-\s+', '', text)  # 去列表标记
    return text.strip()


def play_audio(audio_float32, first=False):
    out = scipy_resample(audio_float32, int(len(audio_float32) * A2DP_SR / 24000)).astype(np.float32)
    if first:
        out = np.concatenate([np.zeros(int(A2DP_SR * 0.5), dtype=np.float32), out])
    sd.play(out, samplerate=A2DP_SR, device=A2DP_ID)
    sd.wait()


# ============ 全局组件 ============
asr = ASREngine()
tts = TTSEngine(voice="xiaoxiao", rate="+10%")
pi = PiClient(working_dir="D:/workdir/voice_agent")
session = SessionController()
recorder = AudioRecorder(device_id=HFP_IN, sample_rate=HFP_IN_SR, target_sr=16000,
                         block_size=HFP_IN_SR // 10)

running = True
processing = False
long_input_mode = False      # 长输入模式
input_buffer = []            # 输入积累缓冲
input_timer = None           # 静音超时定时器
INPUT_SILENCE_TIMEOUT = 3.0  # 普通模式：3秒无新输入→发送


def feed_audio(data):
    asr.feed_audio(data)


def play_simple(text):
    recorder.stop()
    sd.stop()  # 确保之前的播放已停止
    time.sleep(0.3)
    print(f"[TTS] {text}", flush=True)
    audio = tts.synthesize(text)
    if audio is not None:
        print(f"  [TTS] 合成OK: {len(audio)} samples", flush=True)
        play_audio(audio, first=True)
        print(f"  [TTS] 播放完成", flush=True)
    else:
        print(f"  [TTS] 合成失败!", flush=True)
    time.sleep(0.2)
    asr.reset()
    recorder.start(callback=feed_audio)


def speak_async(text, then_state=None):
    def _w():
        play_simple(text)
        if then_state:
            session.set_state(then_state)
    threading.Thread(target=_w, daemon=True).start()


# ============ 打断监听 ============
STOP_CHARS = set('停听挺庭叮顶定丁町亭铤廷婷')

def start_interrupt_listen(stop_event):
    """开始监听打断（非阻塞），检测到'停'音时设置stop_event"""
    def _on_final(text):
        print(f"\n  [监听] {text}", flush=True)
        if any(c in text for c in STOP_CHARS) or 'stop' in text.lower():
            stop_event.set()

    asr.set_callbacks(on_final=_on_final)
    asr.reset()
    recorder.start(callback=feed_audio)

def stop_interrupt_listen():
    """停止监听"""
    recorder.stop()
    time.sleep(0.05)


# ============ Agent 指令处理 ============
def handle_command(cmd):
    global processing
    processing = True
    print(f"\n[→ Pi] {cmd}", flush=True)

    recorder.stop()
    time.sleep(0.1)

    # 流式文本收集
    sentence_queue = queue.Queue()
    buf = {"text": "", "done": False}
    SENT_END = re.compile(r'[。！？!?\n]')

    def on_delta(delta):
        print(delta, end="", flush=True)
        buf["text"] += delta
        while True:
            m = SENT_END.search(buf["text"])
            if not m:
                break
            pos = m.end()
            s = clean_for_speech(buf["text"][:pos].strip())
            buf["text"] = buf["text"][pos:]
            if s and len(s) > 1:
                sentence_queue.put(s)

    def on_complete(full):
        print(flush=True)
        r = clean_for_speech(buf["text"].strip())
        if r and len(r) > 1:
            sentence_queue.put(r)
        buf["text"] = ""
        buf["done"] = True

    pi.set_callbacks(on_text_delta=on_delta, on_response_complete=on_complete)
    pi.prompt_async(cmd)

    # 逐句播放 + 空闲时监听打断
    first = True
    aborted = False
    stop_event = threading.Event()
    listening = False

    while True:
        # 检查打断
        if stop_event.is_set():
            print("\n[打断] 用户说停止", flush=True)
            if listening:
                stop_interrupt_listen()
                listening = False
            pi.abort()
            aborted = True
            pi._response_event.wait(timeout=5)
            while not sentence_queue.empty():
                try: sentence_queue.get_nowait()
                except: break
            # 等待 abort 完全完成后再播报
            time.sleep(1)
            play_simple("好的，已停止")
            break

        # 尝试取句子
        sentence = None
        try:
            sentence = sentence_queue.get(timeout=0.5)
        except queue.Empty:
            if buf["done"] and sentence_queue.empty():
                break  # 全部完成
            # 队列空但agent还在工作 → 空闲期，开始监听打断
            if not listening:
                start_interrupt_listen(stop_event)
                listening = True
            continue

        # 有句子要播放 → 先停监听
        if listening:
            stop_interrupt_listen()
            listening = False
            time.sleep(0.3)  # 等BT从 HFP 切回 A2DP

        if stop_event.is_set():
            continue  # 回到循环顶部处理打断

        print(f"  [播放] {sentence[:60]}", flush=True)
        audio = tts.synthesize(sentence)
        if audio is not None:
            play_audio(audio, first=first)
            first = False

    if not aborted:
        pi._response_event.wait(timeout=10)

    # 确保停止监听
    if listening:
        stop_interrupt_listen()

    processing = False
    session.set_state(SessionState.ACTIVE)
    asr.reset()
    recorder.start(callback=feed_audio)
    print(flush=True)


# ============ 输入积累逻辑 ============
def flush_input_buffer():
    """把积累的输入合并发送给agent"""
    global input_buffer, input_timer, long_input_mode
    if not input_buffer:
        return
    full_cmd = "。".join(input_buffer)
    input_buffer = []
    long_input_mode = False
    input_timer = None
    print(f"\n[合并输入] {full_cmd}", flush=True)
    session.set_state(SessionState.PROCESSING)
    threading.Thread(target=handle_command, args=(full_cmd,), daemon=True).start()


def reset_input_timer():
    """重置静音超时定时器"""
    global input_timer
    if input_timer:
        input_timer.cancel()
    input_timer = threading.Timer(INPUT_SILENCE_TIMEOUT, flush_input_buffer)
    input_timer.start()


# ============ 会话回调 ============
def on_wake():
    speak_async("我在，请说")

def on_sleep():
    global long_input_mode, input_buffer
    long_input_mode = False
    input_buffer = []
    speak_async("好的，再见")

def on_command(cmd):
    global long_input_mode, input_buffer

    if processing:
        # 播放中无法用此路径打断（打断由 listen_for_interrupt 处理）
        return

    # 检测长输入模式触发
    if re.search(r'(长段|长篇|多段|详细)(输入|说明|描述)', cmd):
        long_input_mode = True
        input_buffer = []
        speak_async("好的，请说，说完后说好了")
        return

    if long_input_mode:
        # 长输入模式：检测"好了"结束
        if re.search(r'^好了[。．.！!]?$', cmd.strip()):
            flush_input_buffer()
        else:
            input_buffer.append(cmd)
            print(f"  [积累] {cmd} (共{len(input_buffer)}段)", flush=True)
        return

    # 普通模式：积累输入，等静音超时后发送
    input_buffer.append(cmd)
    print(f"  [积累] {cmd} (等{INPUT_SILENCE_TIMEOUT}s静音)", flush=True)
    reset_input_timer()

session.set_callbacks(on_wake=on_wake, on_sleep=on_sleep, on_command=on_command)


# ============ ASR 回调 ============
def on_asr_final(text):
    print(f"\n  [识别] {text}", flush=True)
    session.process_text(text, is_final=True)

asr.set_callbacks(on_final=on_asr_final)


# ============ 主函数 ============
def main():
    global running

    print("=" * 50)
    print("  🎧 蓝牙语音 Pi Agent v3")
    print("  '小派你好' 唤醒 | '小派退下' 休眠")
    print("  '小派，xxx' 发送指令（等静音后发送）")
    print("  '小派，长段输入' → 说完后说'好了'")
    print("  播放中说 '停止' 打断")
    print("  Ctrl+C 退出")
    print("=" * 50, flush=True)

    print("\n[Init] ASR...", flush=True)
    asr.init()
    print("[Init] Pi Agent...", flush=True)
    pi.start()
    print("[Init] 系统提示词...", flush=True)
    pi._send({"type": "steer", "message": SYSTEM_PROMPT})
    time.sleep(0.5)
    print("[Init] ✅ 就绪\n", flush=True)

    recorder.start(callback=feed_audio)
    play_simple("语音助手已启动，说小派你好唤醒我")

    def auto_sleep():
        while running:
            session.check_auto_sleep()
            time.sleep(10)
    threading.Thread(target=auto_sleep, daemon=True).start()

    print("\n等待语音输入...\n", flush=True)
    try:
        while running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    recorder.stop()
    pi.stop()
    print("语音助手已关闭")


if __name__ == "__main__":
    main()
