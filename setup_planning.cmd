@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -m venv .venv
if errorlevel 1 goto failed
:install
.venv\Scripts\python.exe -m pip install -r requirements-planning.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip check
if errorlevel 1 goto failed
echo Ready. Run start_commplan.py --without-model or use the startup CMD.
exit /b 0
:failed
echo Setup failed. Read the error above; Python 3.12 and package download access are required.
exit /b 1
