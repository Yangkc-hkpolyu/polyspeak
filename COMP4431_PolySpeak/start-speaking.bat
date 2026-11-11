@echo off
cd /d "%~dp0"
set "TEMP=%CD%\speaking-runtime\temp"
set "TMP=%TEMP%"
set "PYTHONNOUSERSITE=1"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist ".venv\Scripts\python.exe" (
  echo Please follow START_HERE.md to create the local Python environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -s run-speaking.py
pause

