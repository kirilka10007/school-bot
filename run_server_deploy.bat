@echo off
setlocal

REM Быстрый деплой на сервер одной командой.
REM Перед первым запуском проверьте параметры ниже.
set SERVER_HOST=151.243.176.132
set SERVER_USER=root
set PROJECT_DIR=/opt/school-system
set BRANCH=main

echo [INFO] Deploy to %SERVER_USER%@%SERVER_HOST% ...
ssh %SERVER_USER%@%SERVER_HOST% "cd %PROJECT_DIR% && git pull origin %BRANCH% && . .venv/bin/activate && pip install -r requirements.txt && systemctl restart school-bot school-admin-bot && systemctl --no-pager --full status school-bot && systemctl --no-pager --full status school-admin-bot"

if errorlevel 1 (
  echo [ERROR] Deploy failed.
  exit /b 1
)

echo [OK] Deploy finished.
endlocal
