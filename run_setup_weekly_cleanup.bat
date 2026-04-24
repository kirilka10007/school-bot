@echo off
setlocal

set ROOT=%~dp0
set TASK_NAME=SchoolSystemSoftCleanup
set TASK_TIME=03:00

schtasks /Create ^
  /TN "%TASK_NAME%" ^
  /SC WEEKLY ^
  /D SUN ^
  /ST %TASK_TIME% ^
  /TR "\"%ROOT%run_soft_cleanup.bat\"" ^
  /F

if %ERRORLEVEL% EQU 0 (
  echo [OK] Weekly cleanup task created: %TASK_NAME%
  echo Schedule: weekly on Sunday at %TASK_TIME%
) else (
  echo [ERROR] Failed to create task. Run this file as the same Windows user who owns the project.
)
