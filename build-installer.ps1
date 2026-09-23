param(
    [string]$ProductName = 'Nearlock',
    [string]$OutputName = 'Nearlock-Setup.exe'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($ProductName -notmatch '^[A-Za-z0-9 -]+$' -or $OutputName -notmatch '^[A-Za-z0-9._-]+\.exe$') {
    throw 'Use a simple product name and an executable filename.'
}
$compiler = Join-Path $PSScriptRoot '.build-tools\nsis-3.12\makensis.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $command = Get-Command makensis.exe -ErrorAction SilentlyContinue
    if ($command) { $compiler = $command.Source }
    else { throw 'NSIS 3.12 is required. Extract its portable ZIP into .build-tools or add makensis.exe to PATH.' }
}
$payload = (Resolve-Path -LiteralPath 'dist\Nearlock').Path
if (-not (Test-Path -LiteralPath (Join-Path $payload 'Nearlock.exe'))) { throw 'Run build.ps1 first.' }
$generated = Join-Path $PSScriptRoot 'build\installer'
New-Item -ItemType Directory -Path $generated -Force | Out-Null
$uninstallList = Join-Path $generated 'payload-uninstall.nsh'
$files = @(Get-ChildItem -LiteralPath $payload -Recurse -File)
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('; Generated from the packaged payload. Delete only installed filenames.')
foreach ($file in $files) {
    $relative = $file.FullName.Substring($payload.Length + 1).Replace('$', '$$')
    $lines.Add('Delete "$INSTDIR\' + $relative + '"')
}
$directories = Get-ChildItem -LiteralPath $payload -Recurse -Directory | Sort-Object { $_.FullName.Length } -Descending
foreach ($directory in $directories) {
    $relative = $directory.FullName.Substring($payload.Length + 1).Replace('$', '$$')
    $lines.Add('RMDir "$INSTDIR\' + $relative + '"')
}
$lines | Set-Content -LiteralPath $uninstallList -Encoding utf8
$sizeKiB = [int][Math]::Ceiling(($files | Measure-Object Length -Sum).Sum / 1024)
$output = Join-Path $PSScriptRoot $OutputName
$arguments = @('/NOCD', '/V3', "/DPRODUCT_NAME=$ProductName", "/DOUTPUT_PATH=$output", "/DUNINSTALL_LIST=$uninstallList", "/DSIZE_KB=$sizeKiB", 'installer.nsi')
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
Get-Item -LiteralPath $output | Select-Object FullName, Length
Get-FileHash -LiteralPath $output -Algorithm SHA256
