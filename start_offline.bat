@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 使用 Python 3.12
py -3.12 --version || (
  echo 請先安裝 Python 3.12
  pause
  exit /b 1
)

echo [2/3] 檢查 easyocr
py -3.12 -c "import easyocr; print('easyocr ok')" || (
  echo 正在安裝套件...
  py -3.12 -m pip install -r requirements.txt
)

echo [3/3] 啟動網頁 http://127.0.0.1:8000/offline
py -3.12 main.py serve
pause
