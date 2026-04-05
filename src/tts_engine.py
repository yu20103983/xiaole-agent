"""
模块C: TTS 引擎 — sherpa-onnx 本地文本转语音
"""

import numpy as np
import sherpa_onnx
import threading
import queue
import os
from typing import Optional


def fast_resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """简单线性插值重采样"""
    if src_sr == dst_sr:
        return audio
    ratio = dst_sr / src_sr
    new_len = int(len(audio) * ratio)
    indices = np.arange(new_len) / ratio
    indices_floor = np.floor(indices).astype(int)
    indices_ceil = np.minimum(indices_floor + 1, len(audio) - 1)
    frac = indices - indices_floor
    return (audio[indices_floor] * (1 - frac) + audio[indices_ceil] * frac).astype(np.float32)


class TTSEngine:
    """文本转语音引擎 (基于 sherpa-onnx 本地推理)"""

    # 常用短语预缓存列表
    PRECACHE_PHRASES = [
        "好的", "我在", "好的，我来查一下", "好的，我来处理一下",
        "好的，稍等", "好的，已停止", "我在，请说",
        "语音助手已启动，说小乐小乐唤醒我",
        "好的，再见", "好的，我来看看", "嗯", "好",
        "好的，我来帮你", "好的，马上",
    ]

    # 默认模型目录（相对于项目根目录）
    DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                      "models", "vits-melo-tts-zh_en")

    def __init__(self, voice: str = "xiaoxiao", rate: str = "+0%", volume: str = "+0%",
                 model_dir: str = None):
        self.model_dir = model_dir or self.DEFAULT_MODEL_DIR
        self._output_sr = 24000  # 对外输出采样率，保持兼容

        # 解析语速：rate 格式 "+10%" -> speed 1.1 (注意：sherpa speed 越大越慢)
        self.speed = 1.0
        try:
            rate_val = int(rate.replace('%', '').replace('+', ''))
            # edge-tts rate +10% 表示快10%，对应 sherpa speed = 1/1.1
            self.speed = 1.0 / (1.0 + rate_val / 100.0)
        except:
            pass

        self._cache: dict[str, Optional[np.ndarray]] = {}
        self._cache_lock = threading.Lock()
        self._synth_lock = threading.Lock()  # sherpa-onnx 不是线程安全的

        # 初始化 sherpa-onnx TTS
        self._init_model()

    def _init_model(self):
        """初始化 sherpa-onnx 离线 TTS 模型"""
        model_path = os.path.join(self.model_dir, "model.onnx")
        tokens_path = os.path.join(self.model_dir, "tokens.txt")
        lexicon_path = os.path.join(self.model_dir, "lexicon.txt")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"TTS 模型不存在: {model_path}")

        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=model_path,
                    tokens=tokens_path,
                    lexicon=lexicon_path,
                    dict_dir=self.model_dir,
                ),
                num_threads=4,
            ),
        )

        self._tts = sherpa_onnx.OfflineTts(tts_config)
        self._model_sr = self._tts.sample_rate
        print(f"[TTS] sherpa-onnx 本地 TTS 已加载 (采样率={self._model_sr}Hz, 语速={self.speed:.2f})")

    def _generate(self, text: str) -> Optional[np.ndarray]:
        """调用 sherpa-onnx 合成，返回 float32 音频 (24kHz)"""
        with self._synth_lock:
            result = self._tts.generate(text, sid=0, speed=self.speed)

        samples = np.array(result.samples, dtype=np.float32)
        if len(samples) == 0:
            return None

        # 重采样到目标输出采样率
        if self._model_sr != self._output_sr:
            samples = fast_resample(samples, self._model_sr, self._output_sr)

        return samples

    def precache(self, phrases: list[str] = None):
        """预缓存常用短语的TTS音频"""
        phrases = phrases or self.PRECACHE_PHRASES
        print(f"[TTS] 预缓存 {len(phrases)} 个常用短语...")

        # 本地推理很快，串行即可（sherpa-onnx 非线程安全）
        cached = 0
        for phrase in phrases:
            try:
                audio = self._generate(phrase)
                if audio is not None:
                    with self._cache_lock:
                        self._cache[phrase] = audio
                    cached += 1
            except Exception as e:
                print(f"[TTS] 预缓存失败 '{phrase}': {e}")

        print(f"[TTS] 预缓存完成: {cached}/{len(phrases)} 个")

    def get_cached(self, text: str) -> Optional[np.ndarray]:
        """查找缓存，命中返回音频，未命中返回None"""
        with self._cache_lock:
            return self._cache.get(text)

    def synthesize(self, text: str, retries: int = 3) -> Optional[np.ndarray]:
        """合成语音，返回 numpy 音频数组 (float32, 24kHz)，优先用缓存"""
        # 先查缓存
        cached = self.get_cached(text)
        if cached is not None:
            return cached.copy()

        for attempt in range(retries):
            try:
                audio = self._generate(text)
                if audio is not None and len(audio) > 0:
                    return audio
                print(f"[TTS] 第{attempt+1}次合成无数据，重试...")
            except Exception as e:
                print(f"[TTS] 第{attempt+1}次合成错误: {e}")
        print(f"[TTS] 合成失败，已重试{retries}次")
        return None

    def synthesize_to_file(self, text: str, output_path: str) -> bool:
        """合成语音到文件"""
        try:
            audio = self.synthesize(text)
            if audio is not None:
                import wave
                with wave.open(output_path, 'w') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self._output_sr)
                    data = (audio * 32767).astype(np.int16)
                    wf.writeframes(data.tobytes())
                return True
        except Exception as e:
            print(f"[TTS] 合成到文件错误: {e}")
        return False

    def synthesize_streaming(self, text: str, audio_queue: queue.Queue,
                              done_event: threading.Event):
        """流式合成：本地推理直接生成完整音频放入队列"""
        def _worker():
            try:
                audio = self._generate(text)
                if audio is not None and len(audio) > 0:
                    audio_queue.put(audio)
                audio_queue.put(None)  # sentinel
                done_event.set()
            except Exception as e:
                print(f"[TTS] 流式合成错误: {e}")
                audio_queue.put(None)
                done_event.set()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from audio_io import AudioPlayer, find_bluetooth_devices

    print("=== TTS 引擎测试 (sherpa-onnx 本地版) ===")
    tts = TTSEngine(rate="+10%")

    text = "你好，我是语音助手小乐，很高兴为你服务！"
    print(f"合成: {text}")

    import time
    t0 = time.time()
    audio = tts.synthesize(text)
    t1 = time.time()

    if audio is not None:
        print(f"合成完成: {len(audio)} 样本, {len(audio)/24000:.1f} 秒, 耗时 {t1-t0:.2f}s")

        _, output_id = find_bluetooth_devices()
        player = AudioPlayer(device_id=output_id, sample_rate=24000)
        print("播放中...")
        player.play(audio, blocking=True)
        print("播放完成")
    else:
        print("合成失败")
