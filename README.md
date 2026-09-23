# NiceLock

A Windows 11 Bluetooth proximity lock, built with Python. Choose a device you carry, adjust its proximity settings, and let the app lock Windows when you walk away. A quiet, Apple-inspired desktop interface provides rounded cards, live signal history, device selection, and a system tray icon.

[Source](https://github.com/naveenjujaray/NiceLock) · [Releases](https://github.com/naveenjujaray/NiceLock/releases) · [Report an issue](https://github.com/naveenjujaray/NiceLock/issues) · [GPLv3 license](LICENSE)

> **App naming:** this repository is named **NiceLock**. The current application, installer, tray menu, and settings folder use **Nearlock**. The filenames and instructions below match those builds.

**Windows unlock still requires Windows Hello, your PIN, or your password.** The app detects your return but does not unlock Windows automatically, store sign-in credentials, or bypass Windows authentication. Microsoft's [LockWorkStation documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-lockworkstation) explains that unlocking requires the user to sign in.

## Features

- Automatic Windows locking when the selected device stays out of range or disappears.
- Bluetooth Low Energy (LE) scanning with live signal strength and signal history.
- Bluetooth Classic discovery and connection/presence tracking.
- Configurable signal threshold, lock delay, missing-signal allowance, and desk calibration.
- Device names from advertisements, Windows records, and supported GATT name reads, with a nickname option.
- System tray controls for pause/resume, manual locking, preferences, and quitting.
- Optional startup at sign-in for the current Windows account.
- A per-user setup executable with shortcuts and an uninstaller; no administrator access or separate Python installation is required for packaged builds.
- Local settings and logs, with no account, cloud service, or telemetry.

## Requirements

- **Windows 11, x64.**
- A working Bluetooth adapter with Bluetooth enabled in Windows. LE signal tracking requires an LE-capable adapter and a device that advertises regularly.
- A phone, watch, tag, or other Bluetooth device that you carry with you. Device compatibility depends on its advertising, discoverability, and connection behavior.
- **Python 3.11 or later only for running or building from source.** The setup and portable app include the required runtime.

## Install

### Setup executable

Use **Nearlock-Setup.exe** from a packaged [release](https://github.com/naveenjujaray/NiceLock/releases), when available, or [build it from source](#build-the-setup-executable). GitHub's automatically generated source ZIP is not the Windows installer.

1. If Nearlock is already running, right-click its tray icon and choose **Quit Nearlock**.
2. Double-click **Nearlock-Setup.exe** using your normal Windows account.
3. Follow **Next → Install → Finish**. Choose whether to add a desktop shortcut and start the app at sign-in.
4. Open **Nearlock** from the Start menu or the installer finish page.

Setup installs to `%LOCALAPPDATA%\Programs\Nearlock` by default. It adds Start menu shortcuts and an entry in **Settings → Apps → Installed apps**. Existing device preferences are retained. Both setup and the app run without requesting administrator elevation.

### Portable app

Extract **Nearlock-Windows11.zip**, then open **Nearlock.exe** inside the extracted **Nearlock** folder. Keep the executable and its `_internal` folder together. A local source build produces the same app folder at `dist\Nearlock`.

If you enable startup for a portable copy, keep it in a permanent location. After moving it, toggle **Launch at sign-in** off and on to register the new path.

## Choose a device and enable protection

1. Enable Bluetooth in Windows and keep your device beside the PC.
2. Open **Devices**. LE scanning and Classic inquiry run automatically in the background.
3. Select your device, choose **Bluetooth LE · signal range** or **Bluetooth Classic · presence**, and click **Use this device**.
4. For LE, open **Preferences → Calibrate at my desk**. Keep the device beside you for the eight-second reading, then adjust the threshold or timing if needed.
5. Click **Enable protection**. Keep the device nearby until protection is active; the app requires fresh nearby observations before it arms.
6. Enable **Preferences → Launch at sign-in** if you want the app to start quietly in the tray after you sign in.

Settings save automatically. Closing the window leaves the app running in the notification area, which Windows may place under the tray overflow arrow. Click its icon to reopen the window. The tray menu also provides pause/resume, **Lock Windows now**, **Preferences**, and **Quit Nearlock**. Quitting stops protection until the next launch.

Startup runs after your Windows account signs in. It is not a service that runs before login. From a source checkout, **Enable startup.cmd** and **Disable startup.cmd** provide the same startup controls.

## Bluetooth modes and device names

| Mode | How it observes your device | Proximity control |
| --- | --- | --- |
| Bluetooth LE | Active advertisements and scan responses provide live RSSI and advertised names. | Signal threshold, calibration, missing-signal allowance, and lock delay. |
| Bluetooth Classic | Native Windows inquiry and connection state provide live presence observations. | Missing-signal allowance and lock delay. The Classic APIs used here do not provide RSSI. |

- **Names:** the app combines advertised names, Windows paired-device names, and a selected device's standard GATT Device Name characteristic. If a device exposes no readable name, the app shows its transport and address suffix. Use **Nickname** to assign your own label.
- **LE connections:** with **Reconnect to read the LE name** enabled, the app can briefly connect to the selected device when it appears or returns, read its name, and disconnect. This lets devices that pause advertising during a connection resume sending signal readings. **Read name** also attempts a manual name read. A device may reject the connection or omit the characteristic.
- **Pairing and Classic reconnection:** use **Pair in Windows** for Windows-managed pairing and profile connections. There is no universal connection command for arbitrary nearby Bluetooth devices. The app does not automatically pair with every device it finds.
- **Live presence:** remembered or paired records alone never count as a live sighting. A disconnected, non-discoverable Classic device cannot reliably be tracked by inquiry.
- **Private addresses:** Classic and LE addresses are not guessed to belong to the same physical device. Devices that rotate their LE address may require pairing or reselection.
- **Phone behavior:** a phone may stop advertising when its screen turns off or an app is backgrounded. Check your chosen device in the conditions in which you will actually use it.

## Configure proximity

| Setting | Default | What it does |
| --- | --- | --- |
| LE lock threshold | −75 dBm | Starts the lock countdown when the smoothed signal is at or below this level. Adjustable from −95 to −40 dBm. |
| Return margin | 6 dB | Requires a stronger signal to cancel a countdown or detect a nearby return. This margin is fixed. |
| Allow signal silence | 15 seconds | Time without a live observation before the device counts as missing. Adjustable from 5 to 90 seconds. |
| Wait before locking | 20 seconds | Continuous time away before requesting a Windows lock. Adjustable from 5 to 120 seconds. |

More negative RSSI values indicate a weaker signal. A threshold of −60 dBm generally locks closer to the PC than −85 dBm. RSSI is not a distance in metres: walls, body position, interference, radio hardware, and device power behavior all affect it.

The live LE signal uses a seven-sample median. Desk calibration collects eight seconds of new readings and places the threshold 12 dB below their median. A fresh signal at or above the return threshold cancels an active countdown. When all signal disappears, the missing-signal allowance expires first, followed by the lock delay. Turning Bluetooth off while protection is armed is treated as signal loss; scanning retries after radio errors.

Protection requires a fresh nearby observation before arming after launch, a device change, resuming protection, waking from sleep, or signing back in. This avoids repeatedly locking the PC when you intentionally sign in without your device. Verify that protection is active before relying on it, and test a walk-away/return cycle with your own device.

## Security and local data

The executable manifest uses `asInvoker` and `uiAccess=false`. The app installs no service or driver and makes no machine-wide registry changes. Startup uses only the current account's `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Nearlock` value. Windows or organization policy can still restrict Bluetooth or startup apps. Locally built executables are unsigned; code signing is separate from administrator elevation.

Windows locking uses `LockWorkStation`, with confirmation through Windows session notifications and retries for failed or unconfirmed requests. Return notifications depend on Windows notification and lock-screen settings. Bluetooth proximity is not cryptographic proof of identity and is never used to unlock Windows. If the app, radio driver, or Windows session stops running, the app cannot guarantee a lock; **Win+L** remains available.

Preferences are stored in `%LOCALAPPDATA%\Nearlock\settings.json`. Rotating `nearlock.log` files are stored beside them. Device addresses and nicknames remain local, and the app has no internet dependency at runtime. Open the folder using **Preferences → Open local logs**.

### Uninstall

- **Installed copy:** quit Nearlock, then use **Settings → Apps → Installed apps → Nearlock → Uninstall**. The uninstaller removes its installed files, shortcuts, and associated startup entry while preserving preferences and unrelated files.
- **Portable copy:** disable **Launch at sign-in**, quit the app, and delete the portable app folder.
- To erase saved device preferences and logs as well, remove `%LOCALAPPDATA%\Nearlock` after quitting the app.

## Run from source

On Windows 11 x64, with Python 3.11+ and Git available:

```powershell
git clone https://github.com/naveenjujaray/NiceLock.git
cd NiceLock
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

If you already have the source folder, open PowerShell there and start with the `python -m venv` command. **Start Nearlock.cmd** is also available after installing the dependencies.

Runtime dependencies are pinned in [requirements.txt](requirements.txt). The verified build used Python 3.14.6, PySide6 Essentials 6.11.2, and Bleak 3.0.2. [requirements-build.txt](requirements-build.txt) adds PyInstaller for packaging.

## Build the standalone app

Run the build script from the repository root:

```powershell
.\build.ps1
```

The script creates the local Python environment if needed, installs dependencies, runs the automated checks, generates the icon, packages the application, and checks that the packaged UI opens. Internet access is required to download missing dependencies.

The output is `dist\Nearlock\Nearlock.exe` and its supporting files. Keep the entire `dist\Nearlock` folder together when distributing a portable build.

## Build the setup executable

After building the standalone app, extract the official [NSIS 3.12 portable package](https://sourceforge.net/projects/nsis/files/NSIS%203/3.12/) so that `makensis.exe` is at `.build-tools\nsis-3.12\makensis.exe`, or add it to `PATH`. Then run:

```powershell
.\build-installer.ps1
```

This produces **Nearlock-Setup.exe** in the repository root. [installer.nsi](installer.nsi) uses NSIS's [user execution level](https://nsis.sourceforge.io/Reference/RequestExecutionLevel), current-user shell folders, and HKCU registry entries. Its uninstaller deletes an exact generated list of installed filenames and removes empty directories; it does not recursively erase the chosen installation folder.

Generated environments, build output, verification data, ZIP archives, and setup executables are excluded from Git by [.gitignore](.gitignore). Attach packaged downloads to GitHub Releases separately from the source repository, and provide the matching source, build scripts, and license with each release.

## Verification

Run checks from the repository root after installing the dependencies:

```powershell
# Policy and UI behavior checks; the real Windows lock function is substituted.
.\.venv\Scripts\python.exe test_nearlock.py

# Render the interface with synthetic device data in an isolated folder.
.\.venv\Scripts\python.exe app.py --smoke-test --data-dir .\verification\ui

# Scan real Bluetooth hardware without pairing, connecting, or locking.
.\.venv\Scripts\python.exe verify_app.py hardware

# Run the same hardware diagnostic from a packaged build.
.\dist\Nearlock\Nearlock.exe --diagnose --data-dir .\verification\packaged-hardware

# Build, install, launch, and uninstall a separate installer test copy.
.\verify-installer.ps1
```

Automated checks cover arming, hysteresis, missing signals, lock delay, Classic presence, return detection, settings validation, device selection, calibration, and lock failure handling. The UI smoke test uses synthetic data and does not lock Windows.

The installer verification creates a separately named test installation with temporary current-user registry entries and shortcuts, verifies all payload hashes, runs the installed app's UI check, and uninstalls the test copy. It also checks that an unrelated user file survives removal. It requires the packaged app and NSIS, and refuses to overwrite an existing test installation.

The existing build passed its automated checks, packaged UI check, live LE/Classic discovery check, and installation/uninstallation check. A physical walk-away test, successful GATT name reads for your selected device, and startup after an actual sign-out or reboot still depend on your hardware and session.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Device is absent or its signal stops updating | Enable Bluetooth, bring the device nearby, and check its discoverability or LE advertising, including with its screen off. Use **Pair in Windows** if pairing is needed. |
| Device has an address label instead of a name | Try **Read name**, pair in Windows, or assign a **Nickname**. Some devices do not expose a name. |
| Locks too close or too far away | Recalibrate at your desk and adjust the LE threshold. Increase the delay or signal-silence allowance for intermittent advertisements. |
| Protection stays waiting | Check the selected transport and device. LE needs a fresh signal at or above the return threshold before protection can arm. |
| Closing the window appears to do nothing | The app remains in the system tray. Use **Quit Nearlock** to stop it. |
| App does not start after sign-in | Check **Launch at sign-in** and Windows startup-app settings. If you moved a portable copy, toggle startup off and on again. |

For other problems, [open an issue](https://github.com/naveenjujaray/NiceLock/issues) with your Windows version, Bluetooth adapter, device model, chosen transport, and steps to reproduce. Redact Bluetooth addresses and personal device names from shared logs.

## Project files

| File | Purpose |
| --- | --- |
| [app.py](app.py) | Qt desktop interface, tray controls, and application lifecycle. |
| [bluetooth_windows.py](bluetooth_windows.py) | LE scanning, native Classic discovery, and device-name reads. |
| [proximity.py](proximity.py) | Proximity decisions and persisted settings. |
| [windows_integration.py](windows_integration.py) | Windows locking, session notifications, and startup registration. |
| [build.ps1](build.ps1) / [Nearlock.spec](Nearlock.spec) | Standalone application packaging. |
| [build-installer.ps1](build-installer.ps1) / [installer.nsi](installer.nsi) | Per-user setup and uninstaller packaging. |
| [test_nearlock.py](test_nearlock.py) / [verify_app.py](verify_app.py) / [verify-installer.ps1](verify-installer.ps1) | Policy, UI, hardware, and installer verification. |

## License

Copyright (C) 2026 Naveen Jujaray.

NiceLock, including the application currently named Nearlock, is licensed under the **GNU General Public License, version 3 only** (`GPL-3.0-only`). You may use, modify, and redistribute it under those terms. The software is provided without warranty. See [LICENSE](LICENSE) for the complete license text.

Third-party dependencies retain their respective licenses.
