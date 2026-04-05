"""
TTS 引擎 — sherpa-onnx 本地推理 (Matcha-TTS) + 磁盘缓存

特点:
  - 纯本地推理，无需联网，延迟极低 (RTF ≈ 0.08)
  - Matcha-TTS + HiFi-GAN vocoder
  - 磁盘缓存：常用短语秒级响应
  - 保留 SAPI 保底 fallback
"""

import os
import time
import hashlib
import threading
import queue
import subprocess
import tempfile
import numpy as np
import sherpa_onnx
from typing import Optional


class TTSEngine:
    """文本转语音引擎 (基于 sherpa-onnx Matcha-TTS 本地推理)"""

    # 支持的模型配置
    MODELS = {
        "matcha-zh-baker": {
            "type": "matcha",
            "dir": "matcha-icefall-zh-baker",
            "acoustic_model": "model-steps-3.onnx",
            "vocoder": "hifigan_v2.onnx",
            "lexicon": "lexicon.txt",
            "tokens": "tokens.txt",
            "dict_dir": "dict",
            "description": "中文女声 (Baker, 22050Hz)",
        },
        "melo-zh": {
            "type": "vits",
            "dir": "vits-melo-tts-zh_en",
            "model": "model.onnx",
            "lexicon": "lexicon.txt",
            "tokens": "tokens.txt",
            "description": "中文女声 (MeloTTS, 44100Hz)",
        },
    }

    # 常用短语预缓存列表
    PRECACHE_PHRASES = [
        "好的", "我在", "好的，我来查一下", "好的，我来处理一下",
        "好的，稍等", "好的，已终止", "我在，请说",
        "语音助手已启动，说小乐小乐唤醒我",
        "好的，再见", "好的，我来看看", "嗯", "好",
        "好的，我来帮你", "好的，马上",
        "连续对话已结束，需要时再叫我",
    ]

    # 磁盘缓存目录
    CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "tts")

    def __init__(self, voice: str = "matcha-zh-baker", speed: float = 1.0,
                 models_dir: str = None, num_threads: int = 4):
        self.voice = voice
        self.speed = speed
        self.num_threads = num_threads
        self._models_dir = models_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "models"
        )
        self._tts: Optional[sherpa_onnx.OfflineTts] = None
        self._cache: dict[str, Optional[np.ndarray]] = {}
        self._cache_lock = threading.Lock()
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        self._init_tts()

    def _init_tts(self):
        """初始化 sherpa-onnx TTS 引擎"""
        model_cfg = self.MODELS.get(self.voice)
        if model_cfg is None:
            raise ValueError(f"未知模型: {self.voice}, 可选: {list(self.MODELS.keys())}")

        model_dir = os.path.join(self._models_dir, model_cfg["dir"])
        if not os.path.isdir(model_dir):
            raise FileNotFoundError(f"模型目录不存在: {model_dir}")

        model_type = model_cfg["type"]

        if model_type == "matcha":
            config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    matcha=sherpa_onnx.OfflineTtsMatchaModelConfig(
                        acoustic_model=os.path.join(model_dir, model_cfg["acoustic_model"]),
                        vocoder=os.path.join(model_dir, model_cfg["vocoder"]),
                        lexicon=os.path.join(model_dir, model_cfg["lexicon"]),
                        tokens=os.path.join(model_dir, model_cfg["tokens"]),
                        dict_dir=os.path.join(model_dir, model_cfg.get("dict_dir", "")),
                        length_scale=1.0,
                    ),
                    num_threads=self.num_threads,
                ),
            )
        elif model_type == "vits":
            config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=os.path.join(model_dir, model_cfg["model"]),
                        lexicon=os.path.join(model_dir, model_cfg["lexicon"]),
                        tokens=os.path.join(model_dir, model_cfg["tokens"]),
                        dict_dir=os.path.join(model_dir, model_cfg.get("dict_dir", model_dir)),
                        length_scale=0.9,
                    ),
                    num_threads=self.num_threads,
                ),
            )
        else:
            raise ValueError(f"不支持的模型类型: {model_type}")

        self._tts = sherpa_onnx.OfflineTts(config)
        print(f"[TTS] 本地模型: {model_cfg['description']}")
        print(f"[TTS] 采样率: {self._tts.sample_rate}Hz, 说话人: {self._tts.num_speakers}")

    @property
    def sample_rate(self) -> int:
        """输出音频采样率"""
        return self._tts.sample_rate if self._tts else 24000

    def _cache_file_path(self, text: str) -> str:
        """根据文本+模型+语速生成磁盘缓存文件路径"""
        key = f"{self.voice}_{self.speed}_{text}"
        h = hashlib.md5(key.encode('utf-8')).hexdigest()
        return os.path.join(self.CACHE_DIR, f"{h}.npy")

    def _load_from_disk(self, text: str) -> Optional[np.ndarray]:
        """从磁盘加载缓存音频"""
        path = self._cache_file_path(text)
        if os.path.exists(path):
            try:
                return np.load(path)
            except Exception:
                pass
        return None

    def _save_to_disk(self, text: str, audio: np.ndarray):
        """保存音频到磁盘缓存"""
        try:
            path = self._cache_file_path(text)
            np.save(path, audio)
        except Exception as e:
            print(f"[TTS] 磁盘缓存写入失败: {e}")

    def precache(self, phrases: list[str] = None):
        """预缓存常用短语的TTS音频"""
        phrases = phrases or self.PRECACHE_PHRASES
        print(f"[TTS] 预缓存 {len(phrases)} 个常用短语...")

        # 先从磁盘加载
        need_synth = []
        disk_loaded = 0
        for phrase in phrases:
            audio = self._load_from_disk(phrase)
            if audio is not None:
                with self._cache_lock:
                    self._cache[phrase] = audio
                disk_loaded += 1
            else:
                need_synth.append(phrase)

        if disk_loaded > 0:
            print(f"[TTS] 从磁盘加载 {disk_loaded} 个")

        if not need_synth:
            print(f"[TTS] 预缓存完成: {disk_loaded}/{len(phrases)} 个(全部命中磁盘)")
            return

        print(f"[TTS] 需合成 {len(need_synth)} 个...")
        synth_count = 0
        for phrase in need_synth:
            try:
                audio = self._do_synthesize(phrase)
                if audio is not None:
                    with self._cache_lock:
                        self._cache[phrase] = audio
                    self._save_to_disk(phrase, audio)
                    synth_count += 1
            except Exception as e:
                print(f"[TTS] 预缓存失败 '{phrase}': {e}")

        with self._cache_lock:
            cached = len([v for v in self._cache.values() if v is not None])
        print(f"[TTS] 预缓存完成: {cached}/{len(phrases)} 个")

    def get_cached(self, text: str) -> Optional[np.ndarray]:
        """查找缓存，命中返回音频，未命中返回None"""
        with self._cache_lock:
            return self._cache.get(text)

    def _do_synthesize(self, text: str, sid: int = 0) -> Optional[np.ndarray]:
        """底层合成调用"""
        if self._tts is None:
            return None
        try:
            audio = self._tts.generate(text, sid=sid, speed=self.speed)
            if audio and audio.samples:
                return np.array(audio.samples, dtype=np.float32)
        except Exception as e:
            print(f"[TTS] 本地合成错误: {e}")
        return None

    def synthesize(self, text: str, retries: int = 2) -> Optional[np.ndarray]:
        """合成语音，返回 numpy 音频数组 (float32)"""
        # 先查缓存
        cached = self.get_cached(text)
        if cached is not None:
            return cached.copy()

        for attempt in range(retries):
            audio = self._do_synthesize(text)
            if audio is not None and len(audio) > 0:
                # 缓存合成结果
                with self._cache_lock:
                    if len(self._cache) < 200:
                        self._cache[text] = audio
                return audio
            print(f"[TTS] 第{attempt+1}次合成失败，重试...")
            time.sleep(0.1)

        print(f"[TTS] 本地合成失败，尝试 SAPI 保底: {text[:30]}")
        return self._fallback_sapi(text)

    def synthesize_to_file(self, text: str, output_path: str) -> bool:
        """合成语音到文件 (WAV)"""
        try:
            audio = self.synthesize(text)
            if audio is not None:
                import wave
                with wave.open(output_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes((audio * 32767).astype(np.int16).tobytes())
                return True
        except Exception as e:
            print(f"[TTS] 合成到文件错误: {e}")
        return False

    def _fallback_sapi(self, text: str) -> Optional[np.ndarray]:
        """Windows SAPI 保底 TTS，无需网络"""
        target_sr = self.sample_rate
        tmp_wav = None
        tmp_ps1 = None
        try:
            tmp_fd, tmp_wav = tempfile.mkstemp(suffix='.wav')
            os.close(tmp_fd)
            tmp_ps1 = tmp_wav.replace('.wav', '.ps1')
            safe_text = text.replace('"', "'").replace('\n', ' ')
            with open(tmp_ps1, 'w', encoding='utf-8-sig') as f:
                f.write(f'Add-Type -AssemblyName System.Speech\n')
                f.write(f'$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer\n')
                f.write(f'$synth.Rate = 2\n')
                f.write(f'$synth.SetOutputToWaveFile("{tmp_wav}")\n')
                f.write(f'$synth.Speak("{safe_text}")\n')
                f.write(f'$synth.Dispose()\n')
            result = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', tmp_ps1],
                capture_output=True, timeout=15
            )
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='ignore')[:100]
                print(f"[TTS-SAPI] PowerShell 错误: {stderr}")
                return None
            if not os.path.exists(tmp_wav) or os.path.getsize(tmp_wav) < 100:
                print("[TTS-SAPI] WAV 文件无效")
                return None
            audio = self._decode_wav(tmp_wav, target_sr)
            if audio is not None:
                print(f"[TTS-SAPI] 保底合成OK: {len(audio)} samples")
            return audio
        except Exception as e:
            print(f"[TTS-SAPI] 保底合成失败: {e}")
            return None
        finally:
            for f in (tmp_wav, tmp_ps1):
                if f and os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

    @staticmethod
    def _decode_wav(wav_path: str, target_sr: int = 24000) -> Optional[np.ndarray]:
        """WAV 解码 + 重采样为 float32"""
        try:
            import wave
            with wave.open(wav_path, 'rb') as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                src_sr = wf.getframerate()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)

            if sample_width == 2:
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            elif sample_width == 1:
                samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            else:
                return None

            if n_channels > 1:
                samples = samples[::n_channels]

            if src_sr != target_sr:
                duration = len(samples) / src_sr
                target_len = int(duration * target_sr)
                indices = np.linspace(0, len(samples) - 1, target_len)
                samples = np.interp(indices, np.arange(len(samples)), samples).astype(np.float32)

            return samples
        except Exception as e:
            print(f"[TTS-SAPI] WAV 解码错误: {e}")
            return None


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    import sounddevice as sd

    print("=== TTS 引擎测试 (本地 Matcha-TTS) ===")
    tts = TTSEngine(voice="matcha-zh-baker", speed=1.0)

    texts = [
        "你好，我是语音助手小乐，很高兴为你服务！",
        "好的，我来帮你查一下天气。",
        "今天北京晴，最高温度二十五度，适合出行。",
        "好的，我来处理一下。",
    ]

    for text in texts:
        t0 = time.time()
        audio = tts.synthesize(text)
        elapsed = time.time() - t0
        if audio is not None:
            duration = len(audio) / tts.sample_rate
            print(f"{text}")
            print(f"  合成 {elapsed:.3f}s → 时长 {duration:.2f}s (RTF={elapsed/duration:.3f})")
            sd.play(audio, samplerate=tts.sample_rate)
            sd.wait()
            time.sleep(0.3)
        else:
            print(f"  合成失败: {text}")

    print("\n=== 预缓存测试 ===")
    tts.precache()
    t0 = time.time()
    audio = tts.synthesize("好的，我来查一下")
    print(f"缓存命中: {time.time()-t0:.4f}s")
