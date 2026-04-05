@echo off
chcp 65001 >nul
echo ============================================
echo   小乐语音助手 - 模型下载工具
echo ============================================
echo.

cd /d "%~dp0"
if not exist models mkdir models
cd models

echo [1/4] 下载 SenseVoice ASR 模型...
if exist sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17\model.int8.onnx (
    echo   已存在，跳过
) else (
    echo   下载中... (约 200MB)
    curl -L -O https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
    if errorlevel 1 (
        echo   下载失败！请设置代理后重试:
        echo   set HTTPS_PROXY=http://127.0.0.1:7890
        goto :step2
    )
    tar -xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
    del sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
    echo   完成
)

:step2
echo.
echo [2/4] 下载 Silero VAD 模型...
if exist silero_vad.onnx (
    echo   已存在，跳过
) else (
    echo   下载中... (约 2MB)
    curl -L -o silero_vad.onnx https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
    if errorlevel 1 (
        echo   下载失败！
    ) else (
        echo   完成
    )
)

echo.
echo [3/4] 下载 Matcha-TTS 中文模型...
if exist matcha-icefall-zh-baker\model-steps-3.onnx (
    echo   已存在，跳过
) else (
    echo   下载中... (约 72MB)
    curl -L -O https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/matcha-icefall-zh-baker.tar.bz2
    if errorlevel 1 (
        echo   下载失败！请设置代理后重试
        goto :step4
    )
    tar -xjf matcha-icefall-zh-baker.tar.bz2
    del matcha-icefall-zh-baker.tar.bz2
    echo   完成
)

:step4
echo.
echo [4/4] 下载 HiFi-GAN Vocoder...
if exist matcha-icefall-zh-baker\hifigan_v2.onnx (
    echo   已存在，跳过
) else (
    echo   下载中... (约 4MB)
    curl -L -o matcha-icefall-zh-baker\hifigan_v2.onnx https://github.com/k2-fsa/sherpa-onnx/releases/download/vocoder-models/hifigan_v2.onnx
    if errorlevel 1 (
        echo   下载失败！
    ) else (
        echo   完成
    )
)

echo.
echo ============================================
echo   模型检查
echo ============================================
set OK=1
if not exist sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17\model.int8.onnx (
    echo   [缺失] SenseVoice ASR 模型
    set OK=0
)
if not exist silero_vad.onnx (
    echo   [缺失] Silero VAD 模型
    set OK=0
)
if not exist matcha-icefall-zh-baker\model-steps-3.onnx (
    echo   [缺失] Matcha-TTS 模型
    set OK=0
)
if not exist matcha-icefall-zh-baker\hifigan_v2.onnx (
    echo   [缺失] HiFi-GAN Vocoder
    set OK=0
)
if "%OK%"=="1" (
    echo   所有模型已就绪 ✓
)

echo.
echo 提示: 下载失败可设置代理后重试:
echo   set HTTPS_PROXY=http://127.0.0.1:7890
echo   download_models.bat
echo.
pause
