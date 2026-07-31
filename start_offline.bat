@echo off
cd /d "%~dp0"

echo Using Python 3.12 ...
py -3.12 --version
if errorlevel 1 (
  echo Please install Python 3.12 first.
  pause
  exit /b 1
)

echo Checking easyocr ...
py -3.12 -c "import easyocr; print('easyocr ok')"
if errorlevel 1 (
  echo Installing requirements ...
  py -3.12 -m pip install -r requirements.txt
)

echo.
echo If port 8000 is busy, free it first:
echo   netstat -ano ^| findstr :8000
echo   taskkill /PID ^<pid^> /F
echo.
echo Starting http://127.0.0.1:8000/offline
py -3.12 main.py serve --port 8000
pause
