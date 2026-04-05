@echo off
chcp 65001 >nul
title 小乐语音助手
cd /d D:\workdir\voice_agent

:loop
echo [%date% %time%] 启动语音助手...
C:\Python314\python.exe src/main.py
echo.
echo [%date% %time%] 程序退出，3秒后自动重启...
echo 按 Ctrl+C 取消重启
timeout /t 3 /nobreak >nul
goto loop
