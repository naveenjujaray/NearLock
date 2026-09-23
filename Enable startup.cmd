@echo off
setlocal
cd /d "%~dp0"
if not exist "dist\Nearlock\Nearlock.exe" (
    echo Build the app first using build.ps1.
    pause
    exit /b 1
)
start /wait "" "dist\Nearlock\Nearlock.exe" --install-startup
if errorlevel 1 (
    echo Windows did not allow startup registration. Open Nearlock Preferences to try again.
    pause
    exit /b 1
)
echo Nearlock will start in your tray when you sign in to Windows.
pause
