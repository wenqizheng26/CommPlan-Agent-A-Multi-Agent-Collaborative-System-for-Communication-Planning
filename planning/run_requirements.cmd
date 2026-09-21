@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Missing local Python environment. See planning\README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B -X utf8 -m planning.demo %*
set "agent_exit=%errorlevel%"
if "%~1"=="" pause
exit /b %agent_exit%
