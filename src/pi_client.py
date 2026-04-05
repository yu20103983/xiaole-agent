"""
模块D: Pi Agent RPC 客户端
通过 stdin/stdout JSON 协议与 pi --mode rpc 通信
"""

import subprocess
import json
import threading
import time
from typing import Optional, Callable


class PiClient:
    """Pi Agent RPC 客户端"""

    def __init__(self, working_dir: str = ".",
                 provider: str = "claude-proxy", model: str = "claude-opus-4-6",
                 auto_restart: bool = True, max_restarts: int = 3):
        self.working_dir = working_dir
        self.provider = provider
        self.model = model
        self.auto_restart = auto_restart
        self.max_restarts = max_restarts
        self._restart_count = 0
        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._health_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_text_delta: Optional[Callable[[str], None]] = None
        self._on_response_complete: Optional[Callable[[str], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._current_response = ""
        self._response_event = threading.Event()
        self._lock = threading.Lock()
        self._steer_message: Optional[str] = None  # 保存system prompt用于重启后恢复

    def start(self):
        """启动 pi RPC 进程（使用项目本地 node_modules 中的 pi）"""
        import os as _os
        # 优先用项目本地的 pi
        local_pi = _os.path.join(self.working_dir, "node_modules", ".bin", "pi.cmd")
        if not _os.path.exists(local_pi):
            local_pi = _os.path.join(self.working_dir, "node_modules", ".bin", "pi")
        if not _os.path.exists(local_pi):
            import shutil
            local_pi = shutil.which("pi") or "pi"
        print(f"[PiClient] 使用: {local_pi}")
        # 继承当前环境变量（包含 API 代理配置）
        env = _os.environ.copy()
        self._proc = subprocess.Popen(
            [local_pi, "--mode", "rpc", "--no-session",
             "--provider", self.provider, "--model", self.model],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            cwd=self.working_dir,
            bufsize=1,
            env=env
        )
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_events, daemon=True)
        self._reader_thread.start()
        # 启动健康检查线程
        if self.auto_restart:
            self._health_thread = threading.Thread(target=self._health_check, daemon=True)
            self._health_thread.start()
        time.sleep(1)  # 等待 pi 启动
        print("[PiClient] Pi Agent RPC 已启动")

    def _send(self, cmd: dict):
        """发送命令到 pi"""
        if self._proc and self._proc.stdin:
            line = json.dumps(cmd, ensure_ascii=False) + "\n"
            self._proc.stdin.write(line)
            self._proc.stdin.flush()

    def _read_events(self):
        """持续读取 pi 输出的事件（按行读取，高效）"""
        while self._running and self._proc:
            try:
                line = self._proc.stdout.readline()
                if not line:
                    if self._running:
                        print("[PiClient] Pi 进程输出流已关闭")
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    self._handle_event(event)
                except json.JSONDecodeError:
                    pass
            except Exception as e:
                if self._running:
                    print(f"[PiClient] 读取错误: {e}")
                break

    def _handle_event(self, event: dict):
        """处理 pi 事件"""
        event_type = event.get("type", "")

        if event_type == "message_update":
            ame = event.get("assistantMessageEvent", {})
            if ame.get("type") == "text_delta":
                delta = ame.get("delta", "")
                self._current_response += delta
                if self._on_text_delta:
                    self._on_text_delta(delta)

        elif event_type == "tool_execution_start":
            # 工具开始执行，如果还没有任何文字输出，注入提示
            if not self._current_response.strip() and self._on_text_delta:
                tool_name = event.get("toolName", "")
                hint = "好的，我来处理一下。"
                self._current_response += hint
                self._on_text_delta(hint)

        elif event_type == "agent_end":
            response = self._current_response.strip()
            if response and self._on_response_complete:
                self._on_response_complete(response)
            self._response_event.set()

        elif event_type == "response":
            if not event.get("success", True):
                error = event.get("error", "Unknown error")
                if self._on_error:
                    self._on_error(error)

    def set_callbacks(self,
                      on_text_delta: Optional[Callable[[str], None]] = None,
                      on_response_complete: Optional[Callable[[str], None]] = None,
                      on_error: Optional[Callable[[str], None]] = None):
        """设置事件回调"""
        self._on_text_delta = on_text_delta
        self._on_response_complete = on_response_complete
        self._on_error = on_error

    def prompt(self, message: str, timeout: float = 60) -> Optional[str]:
        """发送提示并等待完整响应"""
        self._current_response = ""
        self._response_event.clear()
        self._send({"type": "prompt", "message": message})

        if self._response_event.wait(timeout=timeout):
            return self._current_response.strip()
        else:
            print("[PiClient] 等待响应超时")
            return None

    def prompt_async(self, message: str):
        """异步发送提示（不等待响应）"""
        self._current_response = ""
        self._response_event.clear()
        self._send({"type": "prompt", "message": message})

    def abort(self):
        """中止当前操作"""
        self._send({"type": "abort"})

    def _health_check(self):
        """定期检查 Pi 进程是否存活，崩溃时自动重启"""
        while self._running:
            time.sleep(3)
            if not self._running:
                break
            if self._proc and self._proc.poll() is not None:
                exit_code = self._proc.poll()
                print(f"[PiClient] Pi 进程已退出 (code={exit_code})")
                if self._restart_count < self.max_restarts:
                    self._restart_count += 1
                    print(f"[PiClient] 自动重启 ({self._restart_count}/{self.max_restarts})...")
                    try:
                        self._proc = None
                        time.sleep(1)
                        self.start()
                        # 重启后恢复 system prompt
                        if self._steer_message:
                            time.sleep(0.5)
                            self._send({"type": "steer", "message": self._steer_message})
                        print(f"[PiClient] 重启成功")
                    except Exception as e:
                        print(f"[PiClient] 重启失败: {e}")
                else:
                    print(f"[PiClient] 已达最大重启次数，停止重试")
                    break

    def save_steer(self, message: str):
        """保存 steer 消息，用于进程重启后恢复"""
        self._steer_message = message

    def stop(self):
        """停止 pi 进程"""
        self._running = False
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        print("[PiClient] Pi Agent RPC 已停止")

    @property
    def is_running(self) -> bool:
        return self._running and self._proc is not None and self._proc.poll() is None


if __name__ == "__main__":
    print("=== Pi RPC 客户端测试 ===")
    client = PiClient(working_dir="D:/workdir/voice_agent")

    def on_delta(delta):
        print(delta, end="", flush=True)

    def on_complete(text):
        print(f"\n\n[完整响应] 共 {len(text)} 字符")

    client.set_callbacks(on_text_delta=on_delta, on_response_complete=on_complete)
    client.start()

    response = client.prompt("你好，请用一句话介绍自己")
    print(f"\n响应: {response}")

    client.stop()
