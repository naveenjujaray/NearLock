$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot '.pyinstaller-cache'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
}
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv --cache-dir .uv-cache pip install --python $python -r requirements-build.txt
} else {
    & $python -m pip install -r requirements-build.txt
}
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python test_nearlock.py
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $python verify_app.py icon
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
& $python -m PyInstaller --noconfirm Nearlock.spec
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
$appExe = Join-Path $PSScriptRoot 'dist\Nearlock\Nearlock.exe'
$smoke = Start-Process -FilePath $appExe -ArgumentList '--smoke-test','--data-dir','verification\build-smoke' -WindowStyle Hidden -PassThru
if (-not $smoke.WaitForExit(60000)) {
    Stop-Process -Id $smoke.Id -ErrorAction SilentlyContinue
    throw 'Packaged app did not finish its UI smoke check.'
}
if ($smoke.ExitCode -ne 0) { throw 'Packaged app failed its UI smoke check.' }
Copy-Item -LiteralPath README.md -Destination 'dist\Nearlock\README.md' -Force
Write-Output 'Built dist\Nearlock\Nearlock.exe. Keep it alongside the _internal folder.'
