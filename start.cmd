@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Planning environment missing. Run setup_planning.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B -X utf8 start_commplan.py %*
set "COMMPLAN_EXIT=%ERRORLEVEL%"
pause
exit /b %COMMPLAN_EXIT%
