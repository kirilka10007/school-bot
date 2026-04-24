@echo off
setlocal

set TASK_NAME=SchoolSystemSoftCleanup
schtasks /Delete /TN "%TASK_NAME%" /F

if %ERRORLEVEL% EQU 0 (
  echo [OK] Weekly cleanup task removed: %TASK_NAME%
) else (
  echo [ERROR] Task not removed. It may not exist or current user has no access.
)
