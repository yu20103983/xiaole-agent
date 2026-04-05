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

SYSTEM_PROMPT = """你是"小乐"，通过蓝牙耳机与用户语音对话的个人助理。

核心能力：
1. 你拥有完整的系统操作能力：执行任意命令行、读写文件、安装软件、管理进程
2. 你可以联网：用 curl/wget 搜索、下载、访问 API、爬取网页
3. 你可以编写和执行代码（Python/Node/PowerShell等）来完成复杂任务
4. 遇到不会的事，主动搜索解决方案，不要说"做不到"

回复规则（回复会被 TTS 播放）：
1. 简洁口语化，禁止 markdown、表格、代码块、emoji、特殊符号
2. 一般回复 2-3 句话，列举不超过3条
3. 执行操作前先说一句“好的，我来xxx”让用户知道你在工作
4. 执行完只说结果，不重复过程

行动原则：
- 用户让你做什么就做什么，不要反问“你确定吗”
- 缺少工具就安装，缺少文件就下载，主动解决问题
- 播放音乐可以用 PowerShell 调用系统播放器或下载音乐文件后播放
- 查询信息可以用 curl 访问搜索引擎或 API
- 充分发挥你的编程和系统操作能力，做一个真正有用的助手"""


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

    # 逐句播放 + 预合成下一句 + 空闲时监听打断
    # 所有音频设备操作(recorder/sd)均在主线程，避免蓝牙切换问题
    aborted = False
    stop_event = threading.Event()
    listening = False
    first_play = True

    # 预合成：后台线程合成下一句
    prefetch = {"audio": None, "ready": threading.Event(), "sentence": None}

    def _prefetch_synth(sentence):
        """后台合成一句"""
        prefetch["sentence"] = sentence
        prefetch["audio"] = None
        prefetch["ready"].clear()
        def _do():
            print(f"  [预合成] {sentence[:40]}", flush=True)
            prefetch["audio"] = tts.synthesize(sentence)
            prefetch["ready"].set()
        threading.Thread(target=_do, daemon=True).start()

    def _get_next_sentence(timeout=0.5):
        """从 sentence_queue 取下一句，返回 (sentence, is_done)"""
        try:
            return sentence_queue.get(timeout=timeout), False
        except queue.Empty:
            if buf["done"] and sentence_queue.empty():
                return None, True
            return None, False

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
            time.sleep(1)
            play_simple("好的，已停止")
            break

        # 取句子
        sentence, is_done = _get_next_sentence()
        if is_done:
            break
        if sentence is None:
            # 空闲期 → 开始监听打断
            if not listening:
                start_interrupt_listen(stop_event)
                listening = True
            continue

        # 有句子要播放 → 主线程停监听 + BT切换
        if listening:
            stop_interrupt_listen()
            listening = False
            sd.stop()
            time.sleep(0.5)  # 等 BT 切回 A2DP

        if stop_event.is_set():
            continue

        # 合成当前句（或用预合成结果）
        audio = None
        if prefetch["ready"].is_set() and prefetch["sentence"] == sentence:
            audio = prefetch["audio"]
            print(f"  [命中预合成]", flush=True)
        if audio is None:
            print(f"  [合成] {sentence[:40]}", flush=True)
            audio = tts.synthesize(sentence)

        if audio is None:
            continue

        # 播放前启动下一句的预合成
        next_s, _ = _get_next_sentence(timeout=0.05)
        if next_s:
            _prefetch_synth(next_s)

        # 播放（仅第一句或 HFP切换后加静音前缀）
        use_prefix = first_play
        if first_play:
            sd.stop()
            time.sleep(0.3)
        print(f"  [播放] {sentence[:40]}", flush=True)
        play_audio(audio, first=use_prefix)
        first_play = False

        # 播放完毕，如果预合成的下一句已就绪，下次循环立即取用

    if not aborted:
        pi._response_event.wait(timeout=10)

    # 确保停止监听
    if listening:
        stop_interrupt_listen()

    processing = False
    session.set_state(SessionState.ACTIVE)
    # 恢复正常 ASR 回调（打断监听期间会被替换）
    asr.set_callbacks(on_final=on_asr_final)
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
    print("  🎧 蓝牙语音 Pi Agent v4")
    print("  '小乐小乐' 唤醒 | '小乐小乐退下' 休眠")
    print("  '小乐，xxx' 发送指令（等静音后发送）")
    print("  '小乐，长段输入' → 说完后说'好了'")
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
    play_simple("语音助手已启动，说小乐小乐唤醒我")

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
