@echo off
chcp 65001 >nul
echo ============================================
echo   小乐语音助手 - 模型下载工具
echo ============================================
echo.

cd /d "%~dp0"
if not exist models mkdir models
cd models

echo [1/3] 下载 SenseVoice ASR 模型...
if exist sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17\model.int8.onnx (
    echo   已存在，跳过
) else (
    echo   下载中... (约 200MB)
    curl -L -O https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
    if errorlevel 1 (
        echo   下载失败！请手动下载或使用代理:
        echo   curl -x http://127.0.0.1:7890 -L -O https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
        goto :step2
    )
    tar -xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
    del sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
    echo   完成
)

:step2
echo.
echo [2/3] 下载 Silero VAD 模型...
if exist silero_vad.onnx (
    echo   已存在，跳过
) else (
    echo   下载中... (约 2MB)
    curl -L -o silero_vad.onnx https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
    if errorlevel 1 (
        echo   下载失败！请手动下载
    ) else (
        echo   完成
    )
)

echo.
echo [3/3] 检查模型文件...
set OK=1
if not exist sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17\model.int8.onnx (
    echo   [缺失] SenseVoice ASR 模型
    set OK=0
)
if not exist silero_vad.onnx (
    echo   [缺失] Silero VAD 模型
    set OK=0
)
if "%OK%"=="1" (
    echo   所有模型已就绪 ✓
)

echo.
echo 提示: 如果下载失败，可以设置代理后重试:
echo   set HTTP_PROXY=http://127.0.0.1:7890
echo   set HTTPS_PROXY=http://127.0.0.1:7890
echo   download_models.bat
echo.
pause
