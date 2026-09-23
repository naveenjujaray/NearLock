"""BLE advertisements + live Classic inquiry. All radio work runs off the GUI thread."""
from __future__ import annotations

import asyncio
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import logging
import queue
import threading
import time

from bleak import BleakClient, BleakScanner
from PySide6.QtCore import QObject, Signal

LOG = logging.getLogger(__name__)
DEVICE_NAME_UUID = "00002a00-0000-1000-8000-00805f9b34fb"


def clean_name(value: str | None) -> str:
    value = " ".join((value or "").replace("\x00", "").split())[:120]
    return "" if value.lower() in ("unknown", "unknown device", "bluetooth device", "n/a") else value


def address_text(number: int) -> str:
    raw = f"{number:012X}"
    return ":".join(raw[i:i + 2] for i in range(0, 12, 2))


class SystemTime(C.Structure):
    _fields_ = [(name, W.WORD) for name in (
        "year", "month", "day_of_week", "day", "hour", "minute", "second", "milliseconds"
    )]

    def timestamp(self) -> float:
        try:
            return datetime(self.year, self.month, self.day, self.hour, self.minute,
                            self.second, self.milliseconds * 1000, timezone.utc).timestamp()
        except ValueError:
            return 0.0


class DeviceInfo(C.Structure):
    _fields_ = [
        ("size", W.DWORD), ("address", C.c_ulonglong), ("device_class", W.ULONG),
        ("connected", W.BOOL), ("remembered", W.BOOL), ("authenticated", W.BOOL),
        ("last_seen", SystemTime), ("last_used", SystemTime), ("name", W.WCHAR * 248),
    ]


class SearchParams(C.Structure):
    _fields_ = [
        ("size", W.DWORD), ("authenticated", W.BOOL), ("remembered", W.BOOL),
        ("unknown", W.BOOL), ("connected", W.BOOL), ("inquiry", W.BOOL),
        ("timeout", C.c_ubyte), ("radio", W.HANDLE),
    ]


class RadioParams(C.Structure):
    _fields_ = [("size", W.DWORD)]


bt = C.WinDLL("bthprops.cpl", use_last_error=True)
bt.BluetoothFindFirstDevice.argtypes = [C.POINTER(SearchParams), C.POINTER(DeviceInfo)]
bt.BluetoothFindFirstDevice.restype = W.HANDLE
bt.BluetoothFindNextDevice.argtypes = [W.HANDLE, C.POINTER(DeviceInfo)]
bt.BluetoothFindNextDevice.restype = W.BOOL
bt.BluetoothFindDeviceClose.argtypes = [W.HANDLE]
bt.BluetoothFindDeviceClose.restype = W.BOOL
bt.BluetoothFindFirstRadio.argtypes = [C.POINTER(RadioParams), C.POINTER(W.HANDLE)]
bt.BluetoothFindFirstRadio.restype = W.HANDLE
bt.BluetoothFindRadioClose.argtypes = [W.HANDLE]
bt.BluetoothFindRadioClose.restype = W.BOOL
kernel32 = C.WinDLL("kernel32", use_last_error=True)
kernel32.CloseHandle.argtypes = [W.HANDLE]
kernel32.CloseHandle.restype = W.BOOL


def classic_scan(inquiry: bool = True) -> list[dict]:
    radio = W.HANDLE()
    params = RadioParams(C.sizeof(RadioParams))
    handle = bt.BluetoothFindFirstRadio(C.byref(params), C.byref(radio))
    if not handle:
        error = C.get_last_error()
        raise OSError(error, "No Classic Bluetooth radio available. Check Bluetooth in Windows Settings.")
    kernel32.CloseHandle(radio)
    bt.BluetoothFindRadioClose(handle)
    started = time.time()
    search = SearchParams(C.sizeof(SearchParams), True, True, True, True, inquiry, 4, None)
    info = DeviceInfo()
    info.size = C.sizeof(DeviceInfo)
    find = bt.BluetoothFindFirstDevice(C.byref(search), C.byref(info))
    if not find:
        error = C.get_last_error()
        if error in (0, 259):  # successful empty inquiry
            return []
        raise C.WinError(error)
    devices = []
    try:
        while True:
            devices.append({
                "kind": "device", "address": address_text(info.address), "transport": "classic",
                "name": clean_name(info.name), "source": "Windows Bluetooth name",
                "paired": bool(info.authenticated), "connected": bool(info.connected),
                # Cached paired/remembered records alone are NOT proof of proximity.
                "live": bool(info.connected) or (inquiry and info.last_seen.timestamp() >= started - 1),
                "time": time.monotonic(),
            })
            if not bt.BluetoothFindNextDevice(find, C.byref(info)):
                error = C.get_last_error()
                if error not in (0, 259):
                    raise C.WinError(error)
                break
    finally:
        bt.BluetoothFindDeviceClose(find)
    return devices


class BluetoothWorker(QObject):
    event = Signal(dict)

    def __init__(self):
        super().__init__()
        self.commands = queue.Queue()
        self.stopping = threading.Event()
        self.thread = None
        self.devices = {}
        self.last_seen = {}
        self.target = ""
        self.auto_name = True
        self.next_connect = 0.0
        self.previous_target_seen = 0.0

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run, name="Nearlock Bluetooth", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stopping.set()

    def configure(self, address: str, reconnect: bool) -> None:
        self.commands.put(("configure", (address, reconnect)))

    def read_name(self, address: str) -> None:
        self.commands.put(("name", address))

    def refresh(self) -> None:
        self.commands.put(("refresh", None))

    def run(self) -> None:
        try:
            asyncio.run(self.main())
        except Exception as exc:
            LOG.exception("Bluetooth worker stopped")
            self.event.emit({"kind": "health", "transport": "ble", "ok": False, "message": str(exc)})

    def advertisement(self, device, data) -> None:
        address = device.address.upper()
        self.devices[address] = device
        now = time.monotonic()
        previous = self.last_seen.get(address, 0.0)
        self.last_seen[address] = now
        if address == self.target and now - previous > 30:
            self.next_connect = 0
        self.event.emit({
            "kind": "device", "address": address, "transport": "ble", "time": now,
            "name": clean_name(data.local_name) or clean_name(device.name),
            "source": "Bluetooth LE advertisement", "live": True,
            "rssi": data.rssi if -127 < data.rssi < 0 else None,
        })
        # Bound private-address churn in a long-running tray process.
        if len(self.devices) > 400:
            for old, seen in list(self.last_seen.items()):
                if old != self.target and now - seen > 180:
                    self.devices.pop(old, None)
                    self.last_seen.pop(old, None)

    async def known_names(self) -> None:
        from winrt.windows.devices.bluetooth import BluetoothLEDevice
        from winrt.windows.devices.enumeration import DeviceInformation
        try:
            found = await asyncio.wait_for(DeviceInformation.find_all_async_aqs_filter(
                BluetoothLEDevice.get_device_selector_from_pairing_state(True)
            ), timeout=12)
            for info in found:
                remote = None
                try:
                    remote = await asyncio.wait_for(BluetoothLEDevice.from_id_async(info.id), timeout=3)
                    if remote:
                        self.event.emit({
                            "kind": "device", "address": address_text(remote.bluetooth_address),
                            "transport": "ble", "name": clean_name(info.name),
                            "source": "Windows paired-device name", "paired": True,
                            "live": False, "time": time.monotonic(),
                        })
                except Exception:
                    LOG.debug("Could not resolve a Windows BLE record", exc_info=True)
                finally:
                    if remote:
                        remote.close()
        except Exception:
            LOG.warning("Windows paired names unavailable", exc_info=True)

    async def resolve_name(self, address: str, automatic: bool = False) -> None:
        device = self.devices.get(address)
        if not device:
            self.event.emit({"kind": "name_result", "address": address, "message":
                             "No live LE advertisement yet. Bring the device closer and try again."})
            return
        self.event.emit({"kind": "connection", "address": address, "message": "Connecting to read the device name…"})
        try:
            # A short connection avoids suppressing advertisements on devices that stop
            # advertising while connected. RSSI always comes from real advertisements.
            async with asyncio.timeout(14):
                async with BleakClient(device, timeout=10) as client:
                    raw = await client.read_gatt_char(DEVICE_NAME_UUID)
                    name = clean_name(raw.decode("utf-8", errors="replace"))
                    if not name:
                        raise ValueError("The device returned an empty name.")
                    self.event.emit({
                        "kind": "device", "address": address, "transport": "ble", "live": False,
                        "name": name, "source": "Device Name service (GATT)", "time": time.monotonic(),
                    })
                    self.event.emit({"kind": "name_result", "address": address,
                                     "message": f"Name read: {name}. Signal scanning continues."})
        except Exception as exc:
            LOG.info("Name read unavailable for selected device: %s", exc)
            self.event.emit({"kind": "name_result", "address": address, "message":
                "This device doesn't expose a readable LE name. Pair in Windows or give it a nickname.",
                "automatic": automatic})

    async def classic_loop(self) -> None:
        while not self.stopping.is_set():
            try:
                for observation in await asyncio.to_thread(classic_scan):
                    self.event.emit(observation)
                self.event.emit({"kind": "health", "transport": "classic", "ok": True, "message": "Classic inquiry active"})
            except Exception as exc:
                self.event.emit({"kind": "health", "transport": "classic", "ok": False, "message": str(exc)})
            for _ in range(6):
                if self.stopping.is_set():
                    break
                await asyncio.sleep(.5)

    async def main(self) -> None:
        classic = asyncio.create_task(self.classic_loop())
        names = asyncio.create_task(self.known_names())
        scanner = None
        name_task = None
        restart_at = 0.0
        try:
            while not self.stopping.is_set():
                now = time.monotonic()
                if scanner is None and now >= restart_at:
                    try:
                        scanner = BleakScanner(self.advertisement, scanning_mode="active")
                        await asyncio.wait_for(scanner.start(), timeout=15)
                        self.event.emit({"kind": "health", "transport": "ble", "ok": True,
                                         "message": "Bluetooth LE scanning active"})
                    except Exception as exc:
                        if scanner:
                            try:
                                await asyncio.wait_for(scanner.stop(), timeout=3)
                            except Exception:
                                pass
                        scanner = None
                        restart_at = time.monotonic() + 8
                        self.event.emit({"kind": "health", "transport": "ble", "ok": False, "message": str(exc)})
                if scanner:
                    # Bleak's Windows watcher can abort when the radio is switched off.
                    watcher = getattr(scanner._backend, "watcher", None)
                    if watcher is not None and int(watcher.status) != 1:  # Started = 1
                        try:
                            await asyncio.wait_for(scanner.stop(), timeout=3)
                        except Exception:
                            LOG.debug("Interrupted scanner cleanup failed", exc_info=True)
                        scanner = None
                        restart_at = 0
                        self.event.emit({"kind": "health", "transport": "ble", "ok": False,
                                         "message": "Bluetooth interrupted. Retrying…"})
                while not self.commands.empty():
                    command, argument = self.commands.get_nowait()
                    if command == "configure":
                        target, self.auto_name = argument
                        if target != self.target:
                            self.target = target
                            self.next_connect = 0
                    elif command == "name" and (name_task is None or name_task.done()):
                        name_task = asyncio.create_task(self.resolve_name(argument))
                    elif command == "refresh":
                        restart_at = 0
                        if names.done():
                            names = asyncio.create_task(self.known_names())
                if (self.target and self.auto_name and now >= self.next_connect
                        and now - self.last_seen.get(self.target, 0) < 5
                        and (name_task is None or name_task.done())):
                    self.next_connect = now + 3600
                    name_task = asyncio.create_task(self.resolve_name(self.target, automatic=True))
                await asyncio.sleep(.5)
        finally:
            for task in (names, name_task):
                if task:
                    task.cancel()
            await asyncio.gather(*(t for t in (names, name_task) if t), return_exceptions=True)
            if scanner:
                try:
                    await asyncio.wait_for(scanner.stop(), timeout=4)
                except Exception:
                    LOG.debug("Scanner cleanup failed", exc_info=True)
            await classic


def diagnose_radios(duration_ms=20000) -> dict:
    """Exercise the real background worker without selecting, connecting, or locking."""
    from PySide6.QtCore import QCoreApplication, QTimer
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = BluetoothWorker()
    events = []
    worker.event.connect(events.append)
    worker.start()
    QTimer.singleShot(duration_ms, app.quit)
    app.exec()
    worker.stop()
    worker.thread.join(timeout=20)
    health = {}
    devices = {}
    for event in events:
        if event["kind"] == "health":
            health[event["transport"]] = {"ok": event["ok"], "message": event["message"]}
        elif event["kind"] == "device":
            key = (event["address"], event["transport"])
            entry = devices.setdefault(key, {"named": False, "live": False})
            entry["named"] |= bool(event.get("name"))
            entry["live"] |= event.get("live", False)
    return {"health": health, "device_count": len(devices),
            "live_count": sum(d["live"] for d in devices.values()),
            "named_count": sum(d["named"] for d in devices.values()),
            "transports": {kind: sum(transport == kind for _, transport in devices) for kind in ("ble", "classic")},
            "worker_stopped_cleanly": not worker.thread.is_alive()}
