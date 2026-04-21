@echo off
setlocal

set ROOT=%~dp0
set PYTHON=C:\Users\Den\AppData\Local\Programs\Python\Python313\python.exe
set PYTHONPATH=%ROOT%.python_packages;%ROOT%

if not exist "%PYTHON%" (
  echo [ERROR] Python not found: %PYTHON%
  exit /b 1
)

cd /d "%ROOT%"
"%PYTHON%" school-bot\bot.py
