@echo off
setlocal

set ROOT=%~dp0
set PYTHON=%ROOT%school-bot\venv\Scripts\python.exe

if not exist "%PYTHON%" (
  echo [ERROR] Python not found: %PYTHON%
  echo Create venv first: python -m venv school-bot\venv
  exit /b 1
)

cd /d "%ROOT%"
"%PYTHON%" school-bot\bot.py
