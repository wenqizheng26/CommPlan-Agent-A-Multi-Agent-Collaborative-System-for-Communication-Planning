@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
if defined COMMPLAN_PYTHON (
  "%COMMPLAN_PYTHON%" -m venv .venv
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3.12 -m venv .venv
  ) else (
    where python >nul 2>nul
    if errorlevel 1 goto missing_python
    python -m venv .venv
  )
)
if errorlevel 1 goto failed
:install
.venv\Scripts\python.exe -c "import sys; assert sys.version_info[:2] == (3, 12), 'Python 3.12 required'"
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements-planning.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip check
if errorlevel 1 goto failed
echo Planning Demo is ready. Double-click start.cmd.
exit /b 0
:missing_python
echo Python 3.12 was not found. Install Python 3.12, or set COMMPLAN_PYTHON to its python.exe, then rerun setup_planning.cmd.
exit /b 1
:failed
echo Setup failed. Check Python 3.12 and package download access; use a new directory if this .venv belongs to another project.
exit /b 1
