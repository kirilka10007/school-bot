@echo off
setlocal

set ROOT=%~dp0
set PYTHON=%ROOT%school-bot\venv\Scripts\python.exe

if not exist "%PYTHON%" (
  set PYTHON=%ROOT%school_admin_bot\venv\Scripts\python.exe
)

if not exist "%PYTHON%" (
  echo [ERROR] Python not found in school-bot or school_admin_bot venv
  exit /b 1
)

cd /d "%ROOT%"
"%PYTHON%" scripts\healthcheck.py
