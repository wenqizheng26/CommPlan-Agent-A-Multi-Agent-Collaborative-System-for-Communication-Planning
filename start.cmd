@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "COMMPLAN_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%COMMPLAN_PY%" set "COMMPLAN_PY=%~dp0..\CommPlan-Agent\.venv\Scripts\python.exe"
if not exist "%COMMPLAN_PY%" (
  echo Planning environment missing. Run setup_planning.cmd first.
  pause
  exit /b 1
)
"%COMMPLAN_PY%" -B -X utf8 start_commplan.py %*
set "COMMPLAN_EXIT=%ERRORLEVEL%"
pause
exit /b %COMMPLAN_EXIT%
