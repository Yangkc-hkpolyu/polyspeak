@echo off
cd /d "%~dp0"
set "TEMP=%CD%\speaking-runtime\temp"
set "TMP=%TEMP%"
set "PYTHONNOUSERSITE=1"
set "NUMBA_CACHE_DIR=%CD%\speaking-runtime\numba-cache"
set "MPLCONFIGDIR=%CD%\speaking-runtime\matplotlib"
set "CUDA_CACHE_PATH=%CD%\speaking-runtime\cuda-cache"
set "TORCH_HOME=%CD%\speaking-runtime\torch-cache"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist ".venv\Scripts\python.exe" (
  echo Please follow README.md to install the Python environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -s run-speaking.py
pause
