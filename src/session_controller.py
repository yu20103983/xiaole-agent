"""
模块E: 会话控制器 — 状态机 + 唤醒词检测 + 指令分发
"""

import re
import time
import threading
from enum import Enum
from typing import Optional, Callable


class SessionState(Enum):
    SLEEPING = "sleeping"   # 休眠：只监听唤醒词
    ACTIVE = "active"       # 活跃：监听指令
    PROCESSING = "processing"  # 处理中：等待 Pi 响应
    SPEAKING = "speaking"   # 播报中：TTS 输出


# 唤醒词模式
WAKE_PATTERNS = [
    r"小派.{0,2}你好",
    r"小派.{0,2}(在吗|醒醒)",
]

# 休眠词模式
SLEEP_PATTERNS = [
    r"小派.{0,2}退下",
]

# 指令前缀（活跃状态下，提取"小派，xxx"中的 xxx）
COMMAND_PATTERNS = [
    r"小派[,，:：。\.\s](.+)",          # "小派，xxx"
    r"小派(.{2,})",                          # "小派xxx"（无标点回退）
]


class SessionController:
    """会话状态机控制器"""

    def __init__(self):
        self.state = SessionState.SLEEPING
        self._on_wake: Optional[Callable[[], None]] = None
        self._on_sleep: Optional[Callable[[], None]] = None
        self._on_command: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()
        self._last_activity = time.time()
        self._auto_sleep_timeout = 120  # 2分钟无活动自动休眠
        self._active_text_buffer = ""

    def set_callbacks(self,
                      on_wake: Optional[Callable[[], None]] = None,
                      on_sleep: Optional[Callable[[], None]] = None,
                      on_command: Optional[Callable[[str], None]] = None):
        self._on_wake = on_wake
        self._on_sleep = on_sleep
        self._on_command = on_command

    def process_text(self, text: str, is_final: bool = False):
        """处理 ASR 识别出的文本"""
        if not text:
            return

        text_lower = text.lower().strip()

        with self._lock:
            if self.state == SessionState.SLEEPING:
                self._handle_sleeping(text_lower)
            elif self.state == SessionState.ACTIVE:
                if is_final:
                    self._handle_active(text_lower, text.strip())
            # PROCESSING 和 SPEAKING 状态下忽略输入

    def _handle_sleeping(self, text: str):
        """休眠状态：检测唤醒词"""
        for pattern in WAKE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                self._transition(SessionState.ACTIVE)
                print(f"[Session] 🔔 唤醒! (匹配: {text})")
                if self._on_wake:
                    self._on_wake()
                return

    def _handle_active(self, text_lower: str, text_original: str):
        """活跃状态：检测休眠词或提取指令（必须以'小派'开头）"""
        self._last_activity = time.time()

        # 检查休眠词
        for pattern in SLEEP_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                self._transition(SessionState.SLEEPING)
                print(f"[Session] 😴 休眠 (匹配: {text_lower})")
                if self._on_sleep:
                    self._on_sleep()
                return

        # 提取指令：必须是 "小派，xxx" 格式
        command = self._extract_command(text_lower, text_original)
        if command:
            self._transition(SessionState.PROCESSING)
            print(f"[Session] 📝 指令: {command}")
            if self._on_command:
                self._on_command(command)
        # 不含"小派"前缀的文本忽略

    def _extract_command(self, text_lower: str, text_original: str) -> Optional[str]:
        """从文本中提取指令内容（匹配 '小派，xxx'）"""
        for pattern in COMMAND_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                return match.group(1).strip()
        return None

    def _transition(self, new_state: SessionState):
        """状态转换"""
        old = self.state
        self.state = new_state
        print(f"[Session] 状态: {old.value} → {new_state.value}")

    def set_state(self, state: SessionState):
        """直接设置状态"""
        with self._lock:
            self._transition(state)

    def check_auto_sleep(self):
        """检查是否需要自动休眠"""
        if (self.state == SessionState.ACTIVE and
                time.time() - self._last_activity > self._auto_sleep_timeout):
            self.set_state(SessionState.SLEEPING)
            print("[Session] ⏰ 自动休眠（超时）")
            if self._on_sleep:
                self._on_sleep()


if __name__ == "__main__":
    print("=== 会话控制器测试 ===")
    ctrl = SessionController()

    ctrl.set_callbacks(
        on_wake=lambda: print("  → 回调: 唤醒!"),
        on_sleep=lambda: print("  → 回调: 休眠!"),
        on_command=lambda cmd: print(f"  → 回调: 指令=[{cmd}]"),
    )

    test_cases = [
        ("嗨派", True),
        ("今天天气怎么样", True),
        ("派，帮我查一下北京天气", True),
        ("休息吧派", True),
        ("嘿派你好", True),
        ("这是一个很长的句子用来测试", True),
        ("再见派", True),
    ]

    for text, is_final in test_cases:
        print(f"\n输入: '{text}' (final={is_final}), 当前状态: {ctrl.state.value}")
        ctrl.process_text(text, is_final)
