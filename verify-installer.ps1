# Compile and exercise a separately named installation. No real Nearlock settings are changed.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$testName = 'Nearlock Installer Verification'
$testSetup = Join-Path $PSScriptRoot 'Nearlock-Setup-Verification.exe'
$testRoot = Join-Path $PSScriptRoot 'verification\installer-test'
$target = Join-Path $testRoot 'Nearlock test'
$registryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$testName"
$runPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$desktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) "$testName.lnk"
$menuFolder = Join-Path ([Environment]::GetFolderPath('Programs')) $testName

function Run-Checked([string]$Executable, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000)) {
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        throw "Timed out: $Executable"
    }
    if ($process.ExitCode -ne 0) { throw "Exit $($process.ExitCode): $Executable" }
}

if (Test-Path -LiteralPath $registryPath) { throw 'An earlier test installation exists. Uninstall it before rerunning.' }
if (Test-Path -LiteralPath $desktopLink) { throw 'The test shortcut already exists; refusing to overwrite it.' }
if (Test-Path -LiteralPath $menuFolder) { throw 'The test Start-menu folder already exists; refusing to overwrite it.' }
if (Test-Path -LiteralPath $target) { throw 'The test destination already exists; use a fresh test directory.' }
& (Join-Path $PSScriptRoot 'build-installer.ps1') -ProductName $testName -OutputName 'Nearlock-Setup-Verification.exe'
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$uninstaller = Join-Path $target 'Uninstall.exe'
$results = [ordered]@{ product = $testName; installed = $false; payloadVerified = $false; shortcutsVerified = $false; startupVerified = $false; installedAppSmokePassed = $false; uninstalled = $false; userFilePreserved = $false }
try {
    # NSIS /D must be last and is intentionally not surrounded by quotes.
    Run-Checked $testSetup @('/S', "/D=$target")
    $install = Get-ItemProperty -LiteralPath $registryPath
    if ($install.InstallLocation -ne $target) { throw 'Unexpected installation directory.' }
    if (-not (Test-Path -LiteralPath $uninstaller)) { throw 'Uninstaller is missing.' }
    $results.installed = $true
    $payload = (Resolve-Path -LiteralPath 'dist\Nearlock').Path
    foreach ($file in Get-ChildItem -LiteralPath $payload -Recurse -File) {
        $relative = $file.FullName.Substring($payload.Length + 1)
        $installedFile = Join-Path $target $relative
        if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $installedFile).Hash) {
            throw "Payload mismatch: $relative"
        }
    }
    $results.payloadVerified = $true
    if (-not (Test-Path -LiteralPath $desktopLink) -or -not (Test-Path -LiteralPath (Join-Path $menuFolder "$testName.lnk"))) {
        throw 'Expected shortcuts were not created.'
    }
    $results.shortcutsVerified = $true
    $startup = Get-ItemPropertyValue -LiteralPath $runPath -Name $testName
    if ($startup -ne ('"' + (Join-Path $target 'Nearlock.exe') + '" --background')) { throw 'Startup command is incorrect.' }
    $results.startupVerified = $true
    $smokeOutput = Join-Path $testRoot 'ui'
    Run-Checked (Join-Path $target 'Nearlock.exe') @('--smoke-test', '--data-dir', ('"' + $smokeOutput + '"'))
    $smoke = Get-Content -LiteralPath (Join-Path $smokeOutput 'smoke-result.json') -Raw | ConvertFrom-Json
    if (-not $smoke.ok) { throw 'The installed app did not pass its smoke check.' }
    $results.installedAppSmokePassed = $true
    Set-Content -LiteralPath (Join-Path $target 'user-file-to-keep.txt') -Value 'The uninstaller must leave unrelated files intact.'
} finally {
    if (Test-Path -LiteralPath $uninstaller) {
        # _?= makes NSIS waitable without spawning a copied uninstaller.
        Run-Checked $uninstaller @('/S', "_?=$target")
        if (Test-Path -LiteralPath $registryPath) { throw 'Uninstall registration was not removed.' }
        if (Test-Path -LiteralPath $desktopLink) { throw 'The test desktop shortcut was not removed.' }
        if (Test-Path -LiteralPath $menuFolder) { throw 'The test Start-menu shortcuts were not removed.' }
        if (Test-Path -LiteralPath (Join-Path $target 'Nearlock.exe')) { throw 'The app executable was not removed.' }
        if (Test-Path -LiteralPath (Join-Path $target '_internal')) { throw 'Packaged runtime files were not removed.' }
        $runEntry = Get-ItemProperty -LiteralPath $runPath -Name $testName -ErrorAction SilentlyContinue
        if ($null -ne $runEntry) { throw 'The test startup entry was not removed.' }
        $results.uninstalled = $true
        $results.userFilePreserved = Test-Path -LiteralPath (Join-Path $target 'user-file-to-keep.txt')
        # A directly executed uninstaller cannot delete its own mapped file.
        if (Test-Path -LiteralPath $uninstaller) { Remove-Item -LiteralPath $uninstaller }
    }
    $results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testRoot 'results.json') -Encoding utf8
}
if (-not $results.userFilePreserved) { throw 'Uninstallation removed an unrelated user file.' }
$results | ConvertTo-Json
