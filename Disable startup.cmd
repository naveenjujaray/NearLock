@echo off
setlocal
cd /d "%~dp0"
if not exist "dist\Nearlock\Nearlock.exe" (
    echo Open Nearlock Preferences to disable launch at sign-in.
    pause
    exit /b 1
)
start /wait "" "dist\Nearlock\Nearlock.exe" --remove-startup
if errorlevel 1 (
    echo Windows did not allow removal. Open Nearlock Preferences to try again.
    pause
    exit /b 1
)
echo Nearlock startup is disabled.
pause
