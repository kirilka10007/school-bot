@echo off
setlocal

set ROOT=%~dp0
set PYTHON=
set PYTHONPATH=%ROOT%.python_packages;%ROOT%

for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Python\PythonCore\3.13\InstallPath" /v ExecutablePath 2^>nul ^| find "ExecutablePath"') do set PYTHON=%%B

if not defined PYTHON (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    set PYTHON=%%P
    goto :python_found
  )
)

:python_found
if not defined PYTHON if exist "%ROOT%school-bot\venv\Scripts\python.exe" set PYTHON=%ROOT%school-bot\venv\Scripts\python.exe
if not defined PYTHON if exist "%ROOT%school_admin_bot\venv\Scripts\python.exe" set PYTHON=%ROOT%school_admin_bot\venv\Scripts\python.exe

if not defined PYTHON (
  echo [ERROR] Python not found. Install Python 3.13 or fix PATH.
  exit /b 1
)

cd /d "%ROOT%"
"%PYTHON%" scripts\soft_cleanup.py
