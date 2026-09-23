"""Current-user Windows integration; no service, credentials, or elevation."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import subprocess
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Nearlock"


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        arguments = [sys.executable, "--background"]
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        arguments = [str(pythonw), str(Path(__file__).with_name("app.py")), "--background"]
    return subprocess.list2cmdline(arguments)


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value == startup_command()
    except FileNotFoundError:
        return False


def set_startup(enabled: bool) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


user32 = C.WinDLL("user32", use_last_error=True)
user32.LockWorkStation.argtypes = []
user32.LockWorkStation.restype = W.BOOL
wts = C.WinDLL("wtsapi32", use_last_error=True)
wts.WTSRegisterSessionNotification.argtypes = [W.HWND, W.DWORD]
wts.WTSRegisterSessionNotification.restype = W.BOOL
wts.WTSUnRegisterSessionNotification.argtypes = [W.HWND]
wts.WTSUnRegisterSessionNotification.restype = W.BOOL


def lock_workstation() -> None:
    if not user32.LockWorkStation():
        raise C.WinError(C.get_last_error())


def register_session(hwnd: int) -> None:
    if not wts.WTSRegisterSessionNotification(hwnd, 0):
        raise C.WinError(C.get_last_error())


def unregister_session(hwnd: int) -> None:
    wts.WTSUnRegisterSessionNotification(hwnd)


def native_event(message) -> tuple[str, bool] | None:
    msg = W.MSG.from_address(int(message))
    if msg.message == 0x02B1:  # WM_WTSSESSION_CHANGE
        if msg.wParam == 0x7:
            return "session", True
        if msg.wParam == 0x8:
            return "session", False
    if msg.message == 0x0218 and msg.wParam in (7, 18):  # resume from suspend
        return "resume", True
    return None
