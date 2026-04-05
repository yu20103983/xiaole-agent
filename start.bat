@echo off
chcp 65001 >nul
title 小乐语音助手
cd /d "%~dp0"

:loop
echo [%date% %time%] 启动语音助手...
set PYTHONIOENCODING=utf-8
python -X utf8 src/main.py
echo.
echo [%date% %time%] 程序退出，3秒后自动重启...
echo 按 Ctrl+C 取消重启
timeout /t 3 /nobreak >nul
goto loop
