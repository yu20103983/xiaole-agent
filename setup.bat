@echo off
chcp 65001 >nul
echo ============================================
echo   小乐语音助手 - 环境安装
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] 安装 Python 依赖...
pip install -r requirements.txt
if errorlevel 1 (
    echo   Python 依赖安装失败！
    pause
    exit /b 1
)
echo   完成
echo.

echo [2/3] 安装 Node.js 依赖 (Pi Agent)...
npm install
if errorlevel 1 (
    echo   Node.js 依赖安装失败！
    pause
    exit /b 1
)
echo   完成
echo.

echo [3/3] 下载模型...
call download_models.bat

echo.
echo ============================================
echo   安装完成！使用 start.bat 启动语音助手
echo ============================================
pause
