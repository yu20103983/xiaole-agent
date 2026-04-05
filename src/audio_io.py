"""
模块A: 音频输入输出 — 蓝牙耳机音频流管理
解决 Windows 蓝牙 HFP 问题：
  - 使用 DirectSound 接口（兼容性最好）
  - 输入输出都走 HFP 通道（避免 A2DP/HFP 冲突）
  - 后台静音保活维持 HFP SCO 链路
"""

import sounddevice as sd
import numpy as np
import threading
import queue
import time
from typing import Optional, Callable
from scipy.signal import resample as scipy_resample


def list_devices():
    """列出所有音频设备"""
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 or d['max_output_channels'] > 0:
            hostapi = sd.query_hostapis(d['hostapi'])['name']
            io = f"in={d['max_input_channels']} out={d['max_output_channels']}"
            print(f"  #{i}: [{hostapi}] {d['name']}  {io}  sr={d['default_samplerate']}")


def find_bluetooth_devices(keyword: str = "漫步者") -> tuple[Optional[int], Optional[int], dict]:
    """查找蓝牙耳机的 HFP 输入/输出设备 (优先 DirectSound)

    返回 (input_id, output_id, info)
    info 包含 input_name, output_name, input_sr, output_sr
    """
    devices = sd.query_devices()
    input_id = None
    output_id = None
    info = {}

    # 按优先级搜索: DirectSound > MME > WASAPI
    priority_order = ['DirectSound', 'MME', 'WASAPI']

    for target_api in priority_order:
        for i, d in enumerate(devices):
            name = d['name']
            if keyword not in name:
                continue
            hostapi = sd.query_hostapis(d['hostapi'])['name']
            if target_api not in hostapi:
                continue
            # 只选 Hands-Free (HFP) 设备，不选 Stereo (A2DP)
            if 'Stereo' in name:
                continue

            if d['max_input_channels'] > 0 and input_id is None:
                input_id = i
                info['input_name'] = name
                info['input_sr'] = int(d['default_samplerate'])
                info['input_api'] = hostapi

            if d['max_output_channels'] > 0 and output_id is None:
                output_id = i
                info['output_name'] = name
                info['output_sr'] = int(d['default_samplerate'])
                info['output_api'] = hostapi

        if input_id is not None and output_id is not None:
            break

    return input_id, output_id, info


class HFPKeepAlive:
    """HFP SCO 链路保活器 — 持续向 HFP 输出发送静音"""

    def __init__(self, device_id: int, sample_rate: int = 44100):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        time.sleep(0.3)  # 等待 SCO 链路建立

    def _worker(self):
        try:
            stream = sd.OutputStream(
                device=self.device_id,
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32'
            )
            stream.start()
            silence = np.zeros(self.sample_rate // 10, dtype=np.float32)  # 100ms
            while not self._stop.is_set():
                stream.write(silence)
            stream.stop()
            stream.close()
        except Exception as e:
            print(f"[HFPKeepAlive] 错误: {e}")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)


class AudioRecorder:
    """蓝牙 HFP 麦克风录音器"""

    def __init__(self, device_id: Optional[int] = None, sample_rate: int = 44100,
                 target_sr: int = 16000, block_size: int = 4410):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.target_sr = target_sr
        self.block_size = block_size
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._running = False
        self._callback: Optional[Callable[[np.ndarray], None]] = None

    def _audio_callback(self, indata, frames, time_info, status):
        if status and 'input' not in str(status).lower():
            print(f"[AudioRecorder] Status: {status}")
        audio = indata[:, 0].copy()
        # 重采样到目标采样率 (通常 44100 → 16000)
        if self.sample_rate != self.target_sr:
            target_len = int(len(audio) * self.target_sr / self.sample_rate)
            if target_len > 0:
                audio = scipy_resample(audio, target_len).astype(np.float32)
        self.audio_queue.put(audio)
        if self._callback:
            self._callback(audio)

    def start(self, callback: Optional[Callable[[np.ndarray], None]] = None):
        self._callback = callback
        self._running = True
        self._stream = sd.InputStream(
            device=self.device_id,
            samplerate=self.sample_rate,
            channels=1,
            blocksize=self.block_size,
            dtype='float32',
            callback=self._audio_callback
        )
        self._stream.start()
        print(f"[AudioRecorder] 录音启动 (设备={self.device_id}, {self.sample_rate}→{self.target_sr}Hz)")

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def get_audio(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear_queue(self):
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break


class AudioPlayer:
    """音频播放器 — 支持 HFP 和 Stereo 输出"""

    def __init__(self, device_id: Optional[int] = None, sample_rate: int = 44100):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self._playing = False

    def play(self, audio_data: np.ndarray, sample_rate: Optional[int] = None, blocking: bool = True):
        sr = sample_rate or self.sample_rate
        # 重采样到设备采样率
        if sr != self.sample_rate:
            audio_data = scipy_resample(
                audio_data, int(len(audio_data) * self.sample_rate / sr)
            ).astype(np.float32)
        self._playing = True
        try:
            sd.play(audio_data, samplerate=self.sample_rate, device=self.device_id)
            if blocking:
                sd.wait()
        finally:
            self._playing = False

    def stop(self):
        sd.stop()
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing


if __name__ == "__main__":
    print("=== 蓝牙音频设备检测 ===")
    list_devices()
    print()
    input_id, output_id, info = find_bluetooth_devices()
    print(f"蓝牙 HFP 输入: #{input_id} ({info.get('input_name', 'N/A')})")
    print(f"蓝牙 HFP 输出: #{output_id} ({info.get('output_name', 'N/A')})")
    print(f"设备信息: {info}")
