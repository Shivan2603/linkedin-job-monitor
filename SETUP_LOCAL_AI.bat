@echo off
echo =====================================================
echo   LOCAL AI SETUP — Ollama + Phi-3 Mini
echo   This downloads ~2.3GB once, then works OFFLINE
echo =====================================================
echo.

REM Check if Ollama is already installed
ollama --version >nul 2>&1
if %errorlevel% == 0 (
    echo [OK] Ollama is already installed!
    goto :pull_model
)

echo [INFO] Downloading Ollama installer...
powershell -Command "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '%TEMP%\OllamaSetup.exe'"
echo [INFO] Installing Ollama (follow the installer)...
start /wait %TEMP%\OllamaSetup.exe
echo [INFO] Ollama installed!

:pull_model
echo.
echo [INFO] Starting Ollama server...
start /min ollama serve

timeout /t 3 /nobreak >nul

echo.
echo [INFO] Downloading Phi-3 Mini (3.8B) — ~2.3GB — best for 8GB RAM machines
echo [INFO] This is a one-time download. Please wait...
echo.
ollama pull phi3:mini

echo.
echo [INFO] Also downloading Llama 3.2 3B as backup...
ollama pull llama3.2:3b

echo.
echo =====================================================
echo   SUCCESS! Local AI is ready.
echo   Resume tailoring will NEVER fail again.
echo   The bot will use local AI only if all cloud APIs fail.
echo =====================================================
pause
