"""
模块B2: ASR 引擎 — VAD + SenseVoice 离线识别
用 silero-VAD 检测语音段，用 SenseVoice 做离线识别
比流式 zipformer 准确率高很多
"""

import numpy as np
import os
import threading
import time
import sherpa_onnx
from typing import Optional, Callable
from collections import deque

SENSEVOICE_DIR = os.path.join(os.path.dirname(__file__), "..", "models",
                              "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17")
VAD_MODEL = os.path.join(os.path.dirname(__file__), "..", "models", "silero_vad.onnx")


class ASREngine:
    """VAD + SenseVoice 离线语音识别引擎"""

    def __init__(self, model_dir: str = SENSEVOICE_DIR, vad_model: str = VAD_MODEL):
        self.model_dir = model_dir
        self.vad_model = vad_model
        self.recognizer: Optional[sherpa_onnx.OfflineRecognizer] = None
        self.vad: Optional[sherpa_onnx.VoiceActivityDetector] = None
        self._on_partial: Optional[Callable[[str], None]] = None
        self._on_final: Optional[Callable[[str], None]] = None
        self._last_text = ""
        self._lock = threading.Lock()
        # VAD 状态
        self._is_speaking = False
        self._speech_buffer = []
        self._silence_after_speech = 0  # 语音后的静音帧数

    def init(self):
        """初始化 VAD + SenseVoice 识别器"""
        # 初始化 SenseVoice 离线识别器
        model_path = os.path.join(self.model_dir, "model.onnx")
        tokens_path = os.path.join(self.model_dir, "tokens.txt")

        for f in [model_path, tokens_path]:
            if not os.path.exists(f):
                raise FileNotFoundError(f"模型文件不存在: {f}")

        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model_path,
            tokens=tokens_path,
            num_threads=4,
            sample_rate=16000,
            use_itn=True,
            language="zh",
        )

        # 初始化 VAD
        if not os.path.exists(self.vad_model):
            raise FileNotFoundError(f"VAD 模型不存在: {self.vad_model}")

        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = self.vad_model
        vad_config.silero_vad.min_silence_duration = 0.5  # 0.5秒静音视为语音结束
        vad_config.silero_vad.min_speech_duration = 0.25  # 最短语音0.25秒
        vad_config.silero_vad.threshold = 0.5
        vad_config.silero_vad.window_size = 512  # 16kHz下32ms
        vad_config.sample_rate = 16000
        vad_config.num_threads = 2

        self.vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=60)

        print("[ASR] VAD + SenseVoice 引擎初始化完成")

    def set_callbacks(self, on_partial: Optional[Callable[[str], None]] = None,
                      on_final: Optional[Callable[[str], None]] = None):
        self._on_partial = on_partial
        self._on_final = on_final

    def feed_audio(self, samples: np.ndarray):
        """输入音频数据（float32, 16kHz, mono）"""
        if self.vad is None or self.recognizer is None:
            return

        with self._lock:
            # VAD 需要逐窗口送入
            self.vad.accept_waveform(samples)

            # 检查是否有完整的语音段
            while not self.vad.empty():
                speech = self.vad.front
                samples_array = np.array(speech.samples, dtype=np.float32)

                # 用 SenseVoice 识别
                stream = self.recognizer.create_stream()
                stream.accept_waveform(16000, samples_array)
                self.recognizer.decode_stream(stream)
                text = stream.result.text.strip()

                # 清理 SenseVoice 的特殊标记
                text = self._clean_sensevoice_text(text)

                if text:
                    self._last_text = text
                    if self._on_final:
                        self._on_final(text)

                self.vad.pop()

    @staticmethod
    def _clean_sensevoice_text(text: str) -> str:
        """清理 SenseVoice 输出的特殊标记"""
        import re
        # 移除 <|xx|> 标记 (如 <|zh|>, <|HAPPY|>, <|BGM|> 等)
        text = re.sub(r'<\|[^|]*\|>', '', text)
        return text.strip()

    def reset(self):
        """重置识别状态"""
        with self._lock:
            if self.vad:
                self.vad.reset()
            self._last_text = ""
            self._is_speaking = False
            self._speech_buffer.clear()

    def get_current_text(self) -> str:
        return self._last_text


if __name__ == "__main__":
    import sys, io, wave
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=== SenseVoice ASR 测试 ===")
    engine = ASREngine()
    engine.init()

    # 用旧模型的测试 wav
    test_wav = os.path.join(os.path.dirname(__file__), "..", "models",
                            "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20",
                            "test_wavs", "0.wav")

    with wave.open(test_wav, 'rb') as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        print(f"测试音频: {sr}Hz, {len(audio)/sr:.1f}s")

    results = []
    engine.set_callbacks(
        on_partial=lambda t: print(f"  [部分] {t}"),
        on_final=lambda t: (print(f"  [最终] {t}"), results.append(t))
    )

    # 分块送入
    chunk_size = 512  # VAD window size
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i:i+chunk_size]
        if len(chunk) == chunk_size:
            engine.feed_audio(chunk)

    # 送一些静音触发最后的 VAD
    silence = np.zeros(16000, dtype=np.float32)
    for i in range(0, len(silence), chunk_size):
        engine.feed_audio(silence[i:i+chunk_size])

    print(f"\n结果: {results}")
