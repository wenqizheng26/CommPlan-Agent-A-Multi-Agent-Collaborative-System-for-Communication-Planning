@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv\Scripts\python.exe. Please prepare the environment described in README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B -X utf8 start_commplan.py %*
set "COMMPLAN_EXIT=%ERRORLEVEL%"
pause
exit /b %COMMPLAN_EXIT%
