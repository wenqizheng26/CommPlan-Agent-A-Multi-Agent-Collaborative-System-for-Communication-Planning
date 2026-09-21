@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Missing local Python environment. See planning\README.md.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:18082 in Chrome after the server starts.
".venv\Scripts\python.exe" -B -X utf8 -m planning.web_server %*
if errorlevel 1 pause
