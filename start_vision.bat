@echo off
cd /d "%~dp0"

echo ========================================
echo  Vision header OCR (needs internet)
echo ========================================
echo.

if "%OPENAI_API_KEY%"=="" (
  echo OPENAI_API_KEY is empty.
  echo Get a key from https://platform.openai.com/api-keys
  set /p OPENAI_API_KEY=Paste your API key here: 
)

if "%OPENAI_API_KEY%"=="" (
  echo No API key. Exit.
  pause
  exit /b 1
)

set OPENAI_API_KEY=%OPENAI_API_KEY%
if "%OCR_VISION_MODEL%"=="" set OCR_VISION_MODEL=gpt-4o-mini

echo Using model: %OCR_VISION_MODEL%
echo Freeing port 8000 if busy...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
  taskkill /PID %%a /F >nul 2>&1
)

echo Starting http://127.0.0.1:8000/vision
py -3.12 main.py serve --port 8000
pause
