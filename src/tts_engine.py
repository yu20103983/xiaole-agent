"""
模块C: TTS 引擎 — 双引擎: edge-tts(在线,高音质) + sherpa-onnx(本地,兜底)
"""

import numpy as np
import threading
import queue
import os
import re
from typing import Optional


class TTSEngine:
    """文本转语音引擎 (edge-tts 主引擎 + sherpa-onnx 本地兜底)"""

    PRECACHE_PHRASES = [
        "好的", "我在", "好的，我来查一下", "好的，我来处理一下",
        "好的，稍等", "好的，已停止", "我在，请说",
        "语音助手已启动，说小乐小乐唤醒我",
        "好的，再见", "好的，我来看看", "嗯", "好",
        "好的，我来帮你", "好的，马上",
    ]

    def __init__(self, voice: str = "xiaoxiao", rate: str = "+10%", volume: str = "+0%"):
        self._output_sr = 24000
        self._voice = self._resolve_voice(voice)
        self._rate = rate
        self._volume = volume

        self._cache: dict[str, Optional[np.ndarray]] = {}
        self._cache_lock = threading.Lock()

        # 尝试初始化本地 sherpa-onnx 引擎作为 fallback
        self._local_tts = None
        self._local_lock = threading.Lock()
        self._init_local_fallback()

    def _resolve_voice(self, short: str) -> str:
        voice_map = {
            "xiaoxiao": "zh-CN-XiaoxiaoNeural",
            "yunxi": "zh-CN-YunxiNeural",
            "xiaoyi": "zh-CN-XiaoyiNeural",
            "yunjian": "zh-CN-YunjianNeural",
        }
        return voice_map.get(short, short)

    def _init_local_fallback(self):
        """尝试初始化 sherpa-onnx 本地 TTS 作为 fallback"""
        try:
            import sherpa_onnx
            model_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                     "models", "vits-melo-tts-zh_en")
            model_path = os.path.join(model_dir, "model.onnx")
            if not os.path.exists(model_path):
                print("[TTS] 本地模型不存在，仅使用 edge-tts")
                return

            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=model_path,
                        tokens=os.path.join(model_dir, "tokens.txt"),
                        lexicon=os.path.join(model_dir, "lexicon.txt"),
                        dict_dir=model_dir,
                    ),
                    num_threads=4,
                ),
            )
            self._local_tts = sherpa_onnx.OfflineTts(tts_config)
            self._local_sr = self._local_tts.sample_rate
            print(f"[TTS] 双引擎: edge-tts(主) + sherpa-onnx(兜底, {self._local_sr}Hz)")
        except Exception as e:
            print(f"[TTS] 本地引擎加载失败({e})，仅使用 edge-tts")

    def _generate_edge(self, text: str) -> Optional[np.ndarray]:
        """用 edge-tts 在线合成"""
        import asyncio
        import edge_tts
        import io

        async def _synth():
            comm = edge_tts.Communicate(text, self._voice,
                                        rate=self._rate, volume=self._volume)
            buf = io.BytesIO()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()

        loop = asyncio.new_event_loop()
        try:
            mp3_data = loop.run_until_complete(_synth())
        finally:
            loop.close()

        if not mp3_data:
            return None

        import miniaudio
        decoded = miniaudio.decode(mp3_data, output_format=miniaudio.SampleFormat.FLOAT32)
        samples = np.frombuffer(decoded.samples, dtype=np.float32)
        if decoded.nchannels > 1:
            samples = samples[::decoded.nchannels]

        if decoded.sample_rate != self._output_sr:
            from scipy.signal import resample as scipy_resample
            samples = scipy_resample(samples,
                int(len(samples) * self._output_sr / decoded.sample_rate)).astype(np.float32)

        return samples

    def _generate_local(self, text: str) -> Optional[np.ndarray]:
        """用 sherpa-onnx 本地合成"""
        if self._local_tts is None:
            return None
        # 清理文本中本地模型不支持的字符
        clean = re.sub(r'[^\u4e00-\u9fff\u3000-\u303fa-zA-Z0-9,，。！？!?、；;：\s]', '', text)
        if not clean.strip():
            return None
        with self._local_lock:
            result = self._local_tts.generate(clean, sid=0, speed=0.91)
        samples = np.array(result.samples, dtype=np.float32)
        if len(samples) == 0:
            return None
        if self._local_sr != self._output_sr:
            ratio = self._output_sr / self._local_sr
            new_len = int(len(samples) * ratio)
            indices = np.arange(new_len) / ratio
            idx_f = np.floor(indices).astype(int)
            idx_c = np.minimum(idx_f + 1, len(samples) - 1)
            frac = indices - idx_f
            samples = (samples[idx_f] * (1 - frac) + samples[idx_c] * frac).astype(np.float32)
        return samples

    def precache(self, phrases: list[str] = None):
        """预缓存常用短语"""
        phrases = phrases or self.PRECACHE_PHRASES
        print(f"[TTS] 预缓存 {len(phrases)} 个常用短语...")
        cached = 0
        for phrase in phrases:
            try:
                # 预缓存优先用本地引擎(快)，没有则用 edge-tts
                audio = self._generate_local(phrase) if self._local_tts else None
                if audio is None:
                    audio = self._generate_edge(phrase)
                if audio is not None:
                    with self._cache_lock:
                        self._cache[phrase] = audio
                    cached += 1
            except Exception as e:
                print(f"[TTS] 预缓存失败 '{phrase}': {e}")
        print(f"[TTS] 预缓存完成: {cached}/{len(phrases)} 个")

    def get_cached(self, text: str) -> Optional[np.ndarray]:
        with self._cache_lock:
            return self._cache.get(text)

    def synthesize(self, text: str, retries: int = 3) -> Optional[np.ndarray]:
        """合成语音: 先查缓存 → edge-tts → sherpa-onnx fallback"""
        cached = self.get_cached(text)
        if cached is not None:
            return cached.copy()

        # 主引擎: edge-tts
        for attempt in range(retries):
            try:
                audio = self._generate_edge(text)
                if audio is not None and len(audio) > 0:
                    return audio
            except Exception as e:
                print(f"[TTS] 第{attempt+1}次合成错误: {e}")

        # Fallback: 本地引擎
        if self._local_tts:
            try:
                audio = self._generate_local(text)
                if audio is not None and len(audio) > 0:
                    print(f"[TTS] 使用本地引擎兜底")
                    return audio
            except Exception as e:
                print(f"[TTS] 本地引擎也失败: {e}")

        print(f"[TTS] 合成失败，已重试{retries}次")
        return None

    def synthesize_streaming(self, text: str, audio_queue: queue.Queue,
                              done_event: threading.Event):
        """流式合成"""
        def _worker():
            try:
                audio = self.synthesize(text)
                if audio is not None and len(audio) > 0:
                    audio_queue.put(audio)
                audio_queue.put(None)
                done_event.set()
            except Exception as e:
                print(f"[TTS] 流式合成错误: {e}")
                audio_queue.put(None)
                done_event.set()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t
