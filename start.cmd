@echo off
chcp 65001 >nul
title xiaole
D:
cd D:\workdir\xiaole-agent

:loop
echo starting...
set "PYTHONIOENCODING=utf-8"
C:\Python314\python.exe -X utf8 src\main.py
echo.
echo restarting in 3s...
timeout /t 3 /nobreak >nul
goto loop
