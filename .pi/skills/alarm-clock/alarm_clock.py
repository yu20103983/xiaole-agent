"""
Alarm Clock - 闹钟和倒计时工具
支持设定闹钟、倒计时、查看、取消闹钟
"""

import sys
import os
import json
import time
import re
import subprocess
import signal
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
ALARMS_FILE = SCRIPT_DIR / "alarms.json"
RING_PID_FILE = SCRIPT_DIR / "ringing.pid"


def load_alarms():
    if ALARMS_FILE.exists():
        try:
            return json.loads(ALARMS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_alarms(alarms):
    ALARMS_FILE.write_text(json.dumps(alarms, ensure_ascii=False, indent=2), encoding="utf-8")


def next_id(alarms):
    if not alarms:
        return 1
    return max(a["id"] for a in alarms) + 1


def parse_duration(s):
    """解析时长字符串，如 5m, 30s, 1h30m, 1h30m20s"""
    total = 0
    pattern = re.findall(r"(\d+)\s*([hms])", s.lower())
    if not pattern:
        # 尝试纯数字，默认秒
        try:
            return int(s)
        except ValueError:
            return None
    for val, unit in pattern:
        val = int(val)
        if unit == "h":
            total += val * 3600
        elif unit == "m":
            total += val * 60
        elif unit == "s":
            total += val
    return total


def format_time(dt_str):
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str


def clean_expired(alarms):
    """清理已过期且进程已结束的闹钟"""
    now = datetime.now()
    cleaned = []
    for a in alarms:
        target = datetime.fromisoformat(a["target_time"])
        pid = a.get("pid")
        if target < now and not is_process_alive(pid):
            continue  # 已过期且进程已结束，移除
        cleaned.append(a)
    return cleaned


def is_process_alive(pid):
    if pid is None:
        return False
    try:
        # Windows: 用tasklist检查
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def ring_alarm(label, alarm_id):
    """响铃提醒 - 作为独立进程运行"""
    # 保存当前响铃进程PID
    try:
        RING_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

    # 构建PowerShell脚本：beep + 弹窗
    msg = f"闹钟提醒：{label}" if label else f"闹钟 #{alarm_id} 时间到了！"
    ps_script = f'''
Add-Type -AssemblyName PresentationFramework
$job = Start-Job -ScriptBlock {{
    for ($i = 0; $i -lt 10; $i++) {{
        [console]::beep(1000, 300)
        Start-Sleep -Milliseconds 200
        [console]::beep(1200, 300)
        Start-Sleep -Milliseconds 500
    }}
}}
[System.Windows.MessageBox]::Show("{msg}", "闹钟")
Stop-Job $job -ErrorAction SilentlyContinue
'''
    try:
        subprocess.run(["powershell", "-Command", ps_script], timeout=120)
    except Exception:
        pass

    # 清理PID文件
    try:
        if RING_PID_FILE.exists():
            RING_PID_FILE.unlink()
    except Exception:
        pass


def wait_and_ring(target_iso, label, alarm_id):
    """等待到目标时间然后响铃 - 作为后台进程运行"""
    target = datetime.fromisoformat(target_iso)
    now = datetime.now()
    wait_seconds = (target - now).total_seconds()
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    ring_alarm(label, alarm_id)


def cmd_set(args):
    """设定闹钟 - 指定时间"""
    if not args:
        print("用法: alarm_clock.py set HH:MM[:SS] [--label 标签]")
        return

    time_str = args[0]
    label = ""
    if "--label" in args:
        idx = args.index("--label")
        if idx + 1 < len(args):
            label = args[idx + 1]

    # 解析时间
    try:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        print(f"无法解析时间: {time_str}，请使用 HH:MM 或 HH:MM:SS 格式")
        return

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)

    # 如果时间已过，设为明天
    if target <= now:
        target += timedelta(days=1)
        print(f"[闹钟] 该时间今天已过，已设为明天")

    alarms = load_alarms()
    alarms = clean_expired(alarms)
    aid = next_id(alarms)

    # 启动后台进程
    pid = start_background(target.isoformat(), label, aid)

    alarm_entry = {
        "id": aid,
        "type": "alarm",
        "target_time": target.isoformat(),
        "label": label,
        "pid": pid,
        "created": now.isoformat()
    }
    alarms.append(alarm_entry)
    save_alarms(alarms)

    label_str = f"（{label}）" if label else ""
    print(f"[闹钟] 已设定闹钟 #{aid}{label_str}，将在 {target.strftime('%Y-%m-%d %H:%M:%S')} 响铃")


def cmd_timer(args):
    """设定倒计时"""
    if not args:
        print("用法: alarm_clock.py timer <时长> [--label 标签]")
        print("示例: timer 5m, timer 30s, timer 1h30m")
        return

    duration_str = args[0]
    label = ""
    if "--label" in args:
        idx = args.index("--label")
        if idx + 1 < len(args):
            label = args[idx + 1]

    seconds = parse_duration(duration_str)
    if seconds is None or seconds <= 0:
        print(f"无法解析时长: {duration_str}")
        return

    now = datetime.now()
    target = now + timedelta(seconds=seconds)

    alarms = load_alarms()
    alarms = clean_expired(alarms)
    aid = next_id(alarms)

    # 启动后台进程
    pid = start_background(target.isoformat(), label, aid)

    alarm_entry = {
        "id": aid,
        "type": "timer",
        "target_time": target.isoformat(),
        "duration": duration_str,
        "label": label,
        "pid": pid,
        "created": now.isoformat()
    }
    alarms.append(alarm_entry)
    save_alarms(alarms)

    # 格式化剩余时间
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h > 0:
        parts.append(f"{h}小时")
    if m > 0:
        parts.append(f"{m}分钟")
    if s > 0:
        parts.append(f"{s}秒")
    time_desc = "".join(parts)

    label_str = f"（{label}）" if label else ""
    print(f"[闹钟] 已设定倒计时 #{aid}{label_str}，{time_desc}后（{target.strftime('%H:%M:%S')}）响铃")


def start_background(target_iso, label, alarm_id):
    """启动后台等待进程"""
    script = f'''
import sys
sys.path.insert(0, r"{SCRIPT_DIR}")
from alarm_clock import wait_and_ring
wait_and_ring("{target_iso}", """{label}""", {alarm_id})
'''
    # 用pythonw在后台运行，无窗口
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.pid
    except Exception:
        # 回退方案
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.pid


def cmd_list(args):
    """查看所有闹钟"""
    alarms = load_alarms()
    alarms = clean_expired(alarms)
    save_alarms(alarms)

    if not alarms:
        print("[闹钟] 当前没有活跃的闹钟")
        return

    now = datetime.now()
    print(f"[闹钟] 当前有 {len(alarms)} 个活跃闹钟：")
    for a in alarms:
        target = datetime.fromisoformat(a["target_time"])
        remaining = target - now
        if remaining.total_seconds() > 0:
            h, r = divmod(int(remaining.total_seconds()), 3600)
            m, s = divmod(r, 60)
            parts = []
            if h > 0:
                parts.append(f"{h}小时")
            if m > 0:
                parts.append(f"{m}分钟")
            parts.append(f"{s}秒")
            remain_str = "".join(parts)
        else:
            remain_str = "即将响铃"

        type_str = "闹钟" if a["type"] == "alarm" else "倒计时"
        label_str = f"「{a['label']}」" if a.get("label") else ""
        alive = "运行中" if is_process_alive(a.get("pid")) else "已停止"
        print(f"  #{a['id']} [{type_str}]{label_str} {target.strftime('%H:%M:%S')} (剩余{remain_str}) [{alive}]")


def cmd_cancel(args):
    """取消闹钟"""
    if not args:
        print("用法: alarm_clock.py cancel <ID>")
        return

    try:
        cancel_id = int(args[0])
    except ValueError:
        print(f"无效的ID: {args[0]}")
        return

    alarms = load_alarms()
    found = None
    for a in alarms:
        if a["id"] == cancel_id:
            found = a
            break

    if not found:
        print(f"[闹钟] 未找到闹钟 #{cancel_id}")
        return

    # 终止后台进程
    pid = found.get("pid")
    if pid and is_process_alive(pid):
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        except Exception:
            pass

    alarms = [a for a in alarms if a["id"] != cancel_id]
    save_alarms(alarms)
    label_str = f"「{found.get('label', '')}」" if found.get("label") else ""
    print(f"[闹钟] 已取消闹钟 #{cancel_id}{label_str}")


def cmd_cancel_all(args):
    """取消所有闹钟"""
    alarms = load_alarms()
    if not alarms:
        print("[闹钟] 当前没有活跃的闹钟")
        return

    count = len(alarms)
    for a in alarms:
        pid = a.get("pid")
        if pid and is_process_alive(pid):
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
            except Exception:
                pass

    save_alarms([])
    print(f"[闹钟] 已取消全部 {count} 个闹钟")


def cmd_stop(args):
    """停止正在响的闹钟"""
    stopped = False
    # 通过PID文件找到响铃进程
    if RING_PID_FILE.exists():
        try:
            pid = int(RING_PID_FILE.read_text(encoding="utf-8").strip())
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5)
            RING_PID_FILE.unlink(missing_ok=True)
            stopped = True
        except Exception:
            pass

    # 同时查找所有已到期的闹钟进程并终止
    alarms = load_alarms()
    now = datetime.now()
    for a in alarms:
        target = datetime.fromisoformat(a["target_time"])
        if target <= now:
            pid = a.get("pid")
            if pid and is_process_alive(pid):
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5)
                    stopped = True
                except Exception:
                    pass

    alarms = clean_expired(alarms)
    save_alarms(alarms)

    if stopped:
        print("[闹钟] 已停止响铃")
    else:
        print("[闹钟] 当前没有正在响的闹钟")


def main():
    if len(sys.argv) < 2:
        print("用法: alarm_clock.py <命令> [参数]")
        print("命令: set, timer, list, cancel, cancel-all, stop")
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "set": cmd_set,
        "timer": cmd_timer,
        "list": cmd_list,
        "cancel": cmd_cancel,
        "cancel-all": cmd_cancel_all,
        "stop": cmd_stop,
    }

    if cmd in commands:
        commands[cmd](args)
    else:
        print(f"未知命令: {cmd}")
        print("可用命令: set, timer, list, cancel, cancel-all, stop")


if __name__ == "__main__":
    main()
