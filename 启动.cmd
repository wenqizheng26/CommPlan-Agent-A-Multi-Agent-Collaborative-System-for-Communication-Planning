@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 launch.py
if errorlevel 1 pause
