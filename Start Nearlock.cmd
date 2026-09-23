@echo off
setlocal
cd /d "%~dp0"
if exist "dist\Nearlock\Nearlock.exe" (
    start "" "dist\Nearlock\Nearlock.exe"
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
    exit /b
)
echo Build the app first by running build.ps1 with Python 3.11 or later installed.
pause
