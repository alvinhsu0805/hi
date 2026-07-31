@echo off
cd /d "%~dp0"
echo Freeing port 8000 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
  echo Killing PID %%a
  taskkill /PID %%a /F
)
echo Done. Now run start_offline.bat
pause
