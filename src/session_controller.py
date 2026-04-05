"""
模块E: 会话控制器 — 状态机 + 唤醒词检测 + 指令分发
v5: 上下文关联优化
  - 唤醒词 "小乐小乐"，只要1个"小乐"(含近音)即唤醒
  - 指令 "小乐，xxx"，宽松匹配前缀
  - 上下文关联：用户说"小乐"(停顿)"帮我xxx" → 自动拼接为指令
  - 休眠 "小乐(小乐)退下/再见"，宽松匹配
"""

import re
import time
import threading
from enum import Enum
from typing import Optional, Callable
from config import AUTO_SLEEP_TIMEOUT


class SessionState(Enum):
    SLEEPING = "sleeping"   # 休眠：只监听唤醒词
    ACTIVE = "active"       # 活跃：监听指令
    PROCESSING = "processing"  # 处理中：等待 Pi 响应
    SPEAKING = "speaking"   # 播报中：TTS 输出


# ============ 模糊匹配工具 ============

# "小乐" 的常见 ASR 误识别变体
_XIAO_CHARS = r"[小肖晓消笑筱]"
_LE_CHARS = r"[乐勒了乐洛落络罗]"
# 匹配一个 "小乐" (含变体)，中间允许0-1个杂字
_ONE_XL = _XIAO_CHARS + r".{0,1}" + _LE_CHARS
# 匹配 "小乐小乐" (两次)，中间允许杂字/标点
_TWO_XL = _ONE_XL + r".{0,3}" + _ONE_XL

# "退下" 的常见变体
_TUI_CHARS = r"[退对腿推]"
_XIA_CHARS = r"[下夏]"
_TUIXIA = _TUI_CHARS + r".{0,1}" + _XIA_CHARS

# "再见" 的变体
_ZAIJIAN = r"再.{0,1}见"

# 等待后续指令的超时秒数（用户说"小乐"后的等待窗口）
_PENDING_TIMEOUT = 5.0


def _has_xiaole(text: str) -> bool:
    """检测文本中是否包含至少一个 '小乐' (含近音变体)"""
    return bool(re.search(_ONE_XL, text))


def _is_only_xiaole(text: str) -> bool:
    """检测文本是否只包含'小乐'(1~2次)，没有其他有意义的内容"""
    cleaned = re.sub(_ONE_XL, '', text)
    cleaned = re.sub(r'[,，:：。.、\s！!？?]', '', cleaned)
    return len(cleaned) == 0


def _strip_xiaole_prefix(text: str) -> str:
    """去掉文本开头的 '小乐' 前缀（含标点分隔），返回指令部分"""
    # 先尝试去掉 "小乐小乐" 前缀
    m = re.match(_TWO_XL + r"[,，:：。.、\s]*", text)
    if m:
        return text[m.end():].strip()
    # 再尝试去掉单个 "小乐" 前缀
    m = re.match(_ONE_XL + r"[,，:：。.、\s]*", text)
    if m:
        return text[m.end():].strip()
    return ""


def _is_sleep_command(text: str) -> bool:
    """检测是否是休眠指令: 小乐(小乐)退下/再见"""
    if not _has_xiaole(text):
        return False
    if re.search(_TUIXIA, text):
        return True
    if re.search(_ZAIJIAN, text):
        return True
    return False


# ============ 会话控制器 ============

class SessionController:
    """会话状态机控制器"""

    def __init__(self):
        self.state = SessionState.SLEEPING
        self._on_wake: Optional[Callable[[], None]] = None
        self._on_sleep: Optional[Callable[[], None]] = None
        self._on_command: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()
        self._last_activity = time.time()
        self._auto_sleep_timeout = AUTO_SLEEP_TIMEOUT
        # 上下文关联：用户说了"小乐"但没跟指令，等待下一句
        self._pending_command = False
        self._pending_time = 0.0

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

        text = text.strip()

        with self._lock:
            if self.state == SessionState.SLEEPING:
                self._handle_sleeping(text)
            elif self.state == SessionState.ACTIVE:
                if is_final:
                    self._handle_active(text)
            # PROCESSING 和 SPEAKING 状态下忽略输入

    def _handle_sleeping(self, text: str):
        """休眠状态：检测唤醒词
        只要出现至少一个 '小乐' 即唤醒
        """
        if _has_xiaole(text):
            self._transition(SessionState.ACTIVE)
            self._pending_command = False
            print(f"[Session] 唤醒! ({text})")

            # 唤醒的同时检查是否带了指令（"小乐帮我xxx"）
            cmd = self._try_extract_command(text)
            if cmd:
                # 唤醒 + 指令一起来了，不播唤醒提示，直接执行
                print(f"[Session] 唤醒即指令: {cmd}")
                self._transition(SessionState.PROCESSING)
                if self._on_command:
                    self._on_command(cmd)
            else:
                # 只是唤醒，等后续指令
                self._pending_command = True
                self._pending_time = time.time()
                if self._on_wake:
                    self._on_wake()

    def _handle_active(self, text: str):
        """活跃状态：检测休眠词或提取指令
        支持上下文关联：
          - "小乐"(停顿)"帮我放歌" → 第一句设置pending，第二句作为指令
          - "小乐，帮我放歌" → 直接提取指令
        """
        self._last_activity = time.time()

        # 1. 检查休眠词
        if _is_sleep_command(text):
            self._pending_command = False
            self._transition(SessionState.SLEEPING)
            print(f"[Session] 休眠 ({text})")
            if self._on_sleep:
                self._on_sleep()
            return

        # 2. 尝试从文本中提取带"小乐"前缀的指令
        command = self._try_extract_command(text)
        if command:
            self._pending_command = False
            self._transition(SessionState.PROCESSING)
            print(f"[Session] 指令: {command}")
            if self._on_command:
                self._on_command(command)
            return

        # 3. 文本包含"小乐"但没有提取到指令（只喊了名字）
        if _has_xiaole(text) and _is_only_xiaole(text):
            self._pending_command = True
            self._pending_time = time.time()
            print(f"[Session] 等待指令... ({text})")
            return

        # 4. 上下文关联：前面刚说了"小乐"，这句是指令内容
        if self._pending_command:
            elapsed = time.time() - self._pending_time
            if elapsed <= _PENDING_TIMEOUT:
                # 去掉可能的前缀标点
                cmd = re.sub(r'^[,，:：。.、\s]+', '', text)
                cmd = re.sub(r'[。．.！!？?]+$', '', cmd).strip()
                if cmd and len(cmd) > 1:
                    self._pending_command = False
                    self._transition(SessionState.PROCESSING)
                    print(f"[Session] 关联指令: {cmd} (间隔{elapsed:.1f}s)")
                    if self._on_command:
                        self._on_command(cmd)
                    return
            else:
                # 超时，清除pending
                self._pending_command = False
                print(f"[Session] 等待超时，忽略 ({text})")

        # 5. 不含"小乐"且非pending → 忽略（环境噪音）

    def _try_extract_command(self, text: str) -> Optional[str]:
        """从文本中提取指令内容
        策略:
          1. 文本包含"小乐" → 去掉前缀，剩余即指令
          2. 指令部分不能为空或太短（<=1字）
          3. 如果剩余部分又是"小乐"本身，返回None
        """
        if not _has_xiaole(text):
            return None

        cmd = _strip_xiaole_prefix(text)

        # 去掉末尾句号等
        cmd = re.sub(r'[。．.！!？?]+$', '', cmd).strip()

        if not cmd or len(cmd) <= 1:
            return None

        # 如果剩余部分又是 "小乐" 本身，不当指令
        if _is_only_xiaole(cmd):
            return None

        return cmd

    def _transition(self, new_state: SessionState):
        """状态转换"""
        old = self.state
        self.state = new_state
        print(f"[Session] {old.value} -> {new_state.value}")

    def set_state(self, state: SessionState):
        """直接设置状态"""
        with self._lock:
            self._transition(state)

    def check_auto_sleep(self):
        """检查是否需要自动休眠"""
        if (self.state == SessionState.ACTIVE and
                time.time() - self._last_activity > self._auto_sleep_timeout):
            self.set_state(SessionState.SLEEPING)
            print("[Session] 自动休眠(超时)")
            if self._on_sleep:
                self._on_sleep()


# ============ 测试 ============
if __name__ == "__main__":
    import sys

    print("=== 模糊匹配单元测试 ===\n")

    # 唤醒测试
    wake_tests = [
        ("小乐小乐", True),
        ("小乐你好", True),
        ("肖乐", True),
        ("晓勒晓勒", True),
        ("小洛小洛", True),
        ("小了", True),
        ("笑乐你好", True),
        ("今天天气不错", False),
        ("好的", False),
    ]
    print("--- 唤醒词检测 ---")
    for text, expected in wake_tests:
        result = _has_xiaole(text)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] '{text}' -> {result} (期望{expected})")

    # 纯唤醒词检测
    only_tests = [
        ("小乐", True),
        ("小乐小乐", True),
        ("小乐。", True),
        ("小乐，帮我", False),
        ("小乐帮我查天气", False),
    ]
    print("\n--- 纯唤醒词(无指令)检测 ---")
    for text, expected in only_tests:
        result = _has_xiaole(text) and _is_only_xiaole(text)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] '{text}' -> {result} (期望{expected})")

    # 休眠测试
    sleep_tests = [
        ("小乐小乐退下", True),
        ("小乐退下", True),
        ("小勒对下", True),
        ("小乐再见", True),
        ("晓乐推下", True),
        ("退下", False),
        ("再见", False),
    ]
    print("\n--- 休眠词检测 ---")
    for text, expected in sleep_tests:
        result = _is_sleep_command(text)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] '{text}' -> {result} (期望{expected})")

    # 指令提取测试
    cmd_tests = [
        ("小乐，帮我查天气", "帮我查天气"),
        ("小乐小乐，今天几号", "今天几号"),
        ("小乐帮我放首歌", "帮我放首歌"),
        ("小勒，打开文件", "打开文件"),
        ("小乐 你好", "你好"),
        ("小乐小乐", None),
        ("今天天气好", None),
        ("小乐。", None),
    ]
    print("\n--- 指令提取 ---")
    for text, expected in cmd_tests:
        ctrl = SessionController()
        result = ctrl._try_extract_command(text)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] '{text}' -> '{result}' (期望'{expected}')")

    # 上下文关联测试
    print("\n\n=== 上下文关联测试 ===\n")
    results = []
    ctrl = SessionController()
    ctrl.set_callbacks(
        on_wake=lambda: results.append(("wake", None)),
        on_sleep=lambda: results.append(("sleep", None)),
        on_command=lambda cmd: results.append(("cmd", cmd)),
    )

    # 场景1: 休眠 → "小乐"唤醒 → (停顿) → "帮我放歌" 关联为指令
    print("场景1: 小乐(停顿)帮我放歌")
    results.clear()
    ctrl.state = SessionState.SLEEPING
    ctrl._pending_command = False
    ctrl.process_text("小乐。", is_final=True)
    assert ctrl.state == SessionState.ACTIVE, f"应为active, 实为{ctrl.state}"
    assert ctrl._pending_command == True, "应为pending"
    assert results == [("wake", None)], f"应为wake回调, 实为{results}"
    ctrl.process_text("帮我放一首歌曲。", is_final=True)
    assert ctrl.state == SessionState.PROCESSING, f"应为processing, 实为{ctrl.state}"
    assert results[-1] == ("cmd", "帮我放一首歌曲"), f"指令错误: {results}"
    print("  OK!")

    # 场景2: 活跃 → "小乐"(停顿) → "今天几号" 关联为指令
    print("场景2: 活跃态 小乐(停顿)今天几号")
    results.clear()
    ctrl.state = SessionState.ACTIVE
    ctrl._pending_command = False
    ctrl.process_text("小乐。", is_final=True)
    assert ctrl._pending_command == True
    ctrl.process_text("今天几号？", is_final=True)
    assert results[-1] == ("cmd", "今天几号"), f"指令错误: {results}"
    print("  OK!")

    # 场景3: "小乐帮我查天气" 一句搞定
    print("场景3: 小乐帮我查天气(一句)")
    results.clear()
    ctrl.state = SessionState.ACTIVE
    ctrl._pending_command = False
    ctrl.process_text("小乐帮我查天气。", is_final=True)
    assert results[-1] == ("cmd", "帮我查天气"), f"指令错误: {results}"
    print("  OK!")

    # 场景4: 休眠态 → "小乐帮我查天气" 唤醒+指令一步到位
    print("场景4: 休眠态 小乐帮我查天气(唤醒即指令)")
    results.clear()
    ctrl.state = SessionState.SLEEPING
    ctrl._pending_command = False
    ctrl.process_text("小乐帮我查天气。", is_final=True)
    assert ctrl.state == SessionState.PROCESSING
    assert results == [("cmd", "帮我查天气")], f"应无wake直接cmd, 实为{results}"
    print("  OK!")

    # 场景5: pending超时
    print("场景5: pending超时")
    results.clear()
    ctrl.state = SessionState.ACTIVE
    ctrl._pending_command = True
    ctrl._pending_time = time.time() - 10  # 10秒前
    ctrl.process_text("随便说的话", is_final=True)
    assert len(results) == 0, f"超时不应触发: {results}"
    assert ctrl._pending_command == False
    print("  OK!")

    print("\n=== 全部测试通过 ===")
