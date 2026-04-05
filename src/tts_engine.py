"""
模块C: TTS 引擎 — edge-tts 文本转语音 + 音频解码播放
"""

import asyncio
import edge_tts
import io
import numpy as np
import miniaudio
import threading
import queue
import os
from typing import Optional


class TTSEngine:
    """文本转语音引擎 (基于 edge-tts)"""

    # 推荐中文语音
    VOICES = {
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",   # 女声，温柔
        "yunxi": "zh-CN-YunxiNeural",          # 男声，自然
        "xiaoyi": "zh-CN-XiaoyiNeural",        # 女声，活泼
        "yunjian": "zh-CN-YunjianNeural",       # 男声，沉稳
    }

    def __init__(self, voice: str = "xiaoxiao", rate: str = "+0%", volume: str = "+0%"):
        self.voice = self.VOICES.get(voice, voice)
        self.rate = rate
        self.volume = volume
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._init_event_loop()

    def _init_event_loop(self):
        """初始化独立的事件循环线程"""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def _run_async(self, coro):
        """在事件循环中运行协程"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30)

    async def _synthesize_to_bytes(self, text: str) -> bytes:
        """合成语音并返回 mp3 字节"""
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, volume=self.volume)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        return audio_bytes

    def synthesize(self, text: str, retries: int = 3) -> Optional[np.ndarray]:
        """合成语音，返回 numpy 音频数组 (float32, 24kHz)，失败自动重试"""
        import time as _time
        for attempt in range(retries):
            try:
                mp3_data = self._run_async(self._synthesize_to_bytes(text))
                if mp3_data:
                    return self._decode_mp3(mp3_data)
                print(f"[TTS] 第{attempt+1}次合成无数据，重试...")
            except Exception as e:
                print(f"[TTS] 第{attempt+1}次合成错误: {e}")
            _time.sleep(0.5)
        print(f"[TTS] 合成失败，已重试{retries}次")
        return None

    def synthesize_to_file(self, text: str, output_path: str) -> bool:
        """合成语音到文件"""
        try:
            mp3_data = self._run_async(self._synthesize_to_bytes(text))
            if mp3_data:
                with open(output_path, 'wb') as f:
                    f.write(mp3_data)
                return True
        except Exception as e:
            print(f"[TTS] 合成到文件错误: {e}")
        return False

    def synthesize_streaming(self, text: str, audio_queue: queue.Queue,
                              done_event: threading.Event):
        """流式合成：边生成边放入队列"""
        def _worker():
            try:
                async def _stream():
                    communicate = edge_tts.Communicate(text, self.voice,
                                                        rate=self.rate, volume=self.volume)
                    buffer = b""
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            buffer += chunk["data"]
                            # 攒够一定量再解码
                            if len(buffer) > 8192:
                                audio = self._decode_mp3(buffer)
                                if audio is not None and len(audio) > 0:
                                    audio_queue.put(audio)
                                buffer = b""
                    # 处理剩余
                    if buffer:
                        audio = self._decode_mp3(buffer)
                        if audio is not None and len(audio) > 0:
                            audio_queue.put(audio)
                    audio_queue.put(None)  # sentinel
                    done_event.set()

                self._run_async(_stream())
            except Exception as e:
                print(f"[TTS] 流式合成错误: {e}")
                done_event.set()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t

    @staticmethod
    def _decode_mp3(mp3_data: bytes, sample_rate: int = 24000) -> Optional[np.ndarray]:
        """用 miniaudio 解码 MP3 数据为 float32 numpy 数组"""
        try:
            decoded = miniaudio.decode(mp3_data,
                                       output_format=miniaudio.SampleFormat.FLOAT32,
                                       nchannels=1,
                                       sample_rate=sample_rate)
            return np.frombuffer(decoded.samples, dtype=np.float32).copy()
        except Exception as e:
            print(f"[TTS] MP3 解码错误: {e}")
            return None


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from audio_io import AudioPlayer, find_bluetooth_devices

    print("=== TTS 引擎测试 ===")
    tts = TTSEngine(voice="xiaoxiao")

    text = "你好，我是语音助手小派，很高兴为你服务！"
    print(f"合成: {text}")

    audio = tts.synthesize(text)
    if audio is not None:
        print(f"合成完成: {len(audio)} 样本, {len(audio)/24000:.1f} 秒")

        _, output_id = find_bluetooth_devices()
        player = AudioPlayer(device_id=output_id, sample_rate=24000)
        print("播放中...")
        player.play(audio, blocking=True)
        print("播放完成")
    else:
        print("合成失败")
