---
name: alarm-clock
description: 设定闹钟和倒计时。支持指定时间响铃、倒计时提醒、查看和取消闹钟。当用户要求设闹钟、定时、倒计时、提醒时使用此skill。
---

# Alarm Clock

设定闹钟和倒计时，到时间后发出提示音提醒。

## 使用方式

### 设定闹钟（指定时间）

```bash
python .pi/skills/alarm-clock/alarm_clock.py set 19:30
python .pi/skills/alarm-clock/alarm_clock.py set 19:30:00
python .pi/skills/alarm-clock/alarm_clock.py set 19:30 --label "开会"
```

### 设定倒计时

```bash
python .pi/skills/alarm-clock/alarm_clock.py timer 5m
python .pi/skills/alarm-clock/alarm_clock.py timer 30s
python .pi/skills/alarm-clock/alarm_clock.py timer 1h30m
python .pi/skills/alarm-clock/alarm_clock.py timer 90s --label "泡面好了"
```

### 查看所有闹钟

```bash
python .pi/skills/alarm-clock/alarm_clock.py list
```

### 取消闹钟

```bash
# 按ID取消
python .pi/skills/alarm-clock/alarm_clock.py cancel 1

# 取消所有闹钟
python .pi/skills/alarm-clock/alarm_clock.py cancel-all
```

### 停止正在响的闹钟

```bash
python .pi/skills/alarm-clock/alarm_clock.py stop
```

## 说明

- 闹钟数据保存在 `.pi/skills/alarm-clock/alarms.json`
- 每个闹钟在后台独立运行，关闭终端不影响
- 到时间后会发出系统提示音并弹窗提醒
- 支持设置标签方便识别不同闹钟
