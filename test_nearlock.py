"""Run with Python; tests never call the real Windows lock function."""
import ctypes
import json
from contextlib import contextmanager
from pathlib import Path
import shutil
import time
import unittest
from unittest.mock import patch
import uuid

from proximity import Settings, Proximity

TEST_TEMP = Path(__file__).parent / "verification" / "test-temp"
TEST_TEMP.mkdir(parents=True, exist_ok=True)


@contextmanager
def test_directory():
    # Inherit workspace ACLs; Python 3.14's private tempfile ACL excludes the sandbox token.
    directory = TEST_TEMP / uuid.uuid4().hex
    directory.mkdir()
    try:
        yield directory
    finally:
        target = directory.resolve()
        assert target.is_relative_to(TEST_TEMP.resolve()) and target != TEST_TEMP.resolve()
        shutil.rmtree(target)


class ProximityChecks(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(address="AA:BB:CC:DD:EE:FF", enabled=True)
        self.policy = Proximity(self.settings)

    def arm(self):
        self.assertEqual(self.policy.tick(0, 0, -55).state, "waiting")
        self.assertEqual(self.policy.tick(3, 3, -55).state, "near")

    def test_must_observe_nearby_before_arming(self):
        for now in (0, 50, 500):
            self.assertFalse(self.policy.tick(now, None, None).lock)
        self.policy.tick(501, 501, -55)
        self.assertEqual(self.policy.tick(506, 500, -55).state, "waiting")
        self.assertEqual(self.policy.tick(507, 507, -55).state, "near")

    def test_sustained_weak_signal_locks_once(self):
        self.arm()
        self.assertEqual(self.policy.tick(4, 4, -82).remaining, 20)
        self.assertFalse(self.policy.tick(23, 23, -82).lock)
        self.assertTrue(self.policy.tick(24, 24, -82).lock)
        self.assertFalse(self.policy.tick(30, 30, -82).lock)

    def test_hysteresis_does_not_flap(self):
        self.arm()
        self.assertEqual(self.policy.tick(4, 4, -72).state, "near")
        self.assertEqual(self.policy.tick(5, 5, -76).state, "away")
        self.assertEqual(self.policy.tick(6, 6, -72).state, "away")
        self.assertEqual(self.policy.tick(7, 7, -68).state, "near")
        self.assertFalse(self.policy.tick(25, 25, -55).lock)

    def test_missing_signal_gets_silence_plus_grace(self):
        self.arm()
        self.assertEqual(self.policy.tick(18, 3, -55).state, "near")
        self.assertEqual(self.policy.tick(19, 3, -55).remaining, 20)
        self.assertTrue(self.policy.tick(39, 3, -55).lock)

    def test_disabled_and_no_target_never_lock(self):
        self.arm()
        self.settings.enabled = False
        self.assertEqual(self.policy.tick(500, None, None).state, "paused")
        self.settings.address = ""
        self.assertEqual(self.policy.tick(1000, None, None).state, "setup")

    def test_classic_requires_live_presence_not_rssi(self):
        self.settings.mode = "classic"
        self.policy.tick(0, 0, None)
        self.assertEqual(self.policy.tick(8, 8, None).state, "near")
        self.assertEqual(self.policy.tick(24, 8, None).state, "away")
        self.assertTrue(self.policy.tick(44, 8, None).lock)

    def test_return_detected_once_without_unlock_action(self):
        self.arm()
        self.policy.session(True)
        self.assertFalse(self.policy.tick(50, None, None).returned)
        decision = self.policy.tick(51, 51, -55)
        self.assertTrue(decision.returned)
        self.assertEqual(decision.state, "locked")
        self.assertFalse(self.policy.tick(52, 52, -55).returned)
        self.assertTrue(self.policy.locked)
        self.policy.session(False)
        self.assertEqual(self.policy.tick(60, None, None).state, "waiting")

    def test_settings_roundtrip_and_validation(self):
        with test_directory() as tmp:
            path = Path(tmp) / "settings.json"
            self.settings.aliases["AA:BB:CC:DD:EE:FF"] = "My phone"
            self.settings.save(path)
            self.assertEqual(Settings.load(path), self.settings)
            for data in ({"threshold": -1000}, {"enabled": "false"}, {"address": "garbage"}, {"mode": "typo"}, [], {"aliases": {"a": 1}}):
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    Settings.load(path)


class WindowsAndUIChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from app import STYLE
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyle("Fusion")
        cls.qt.styleHints().setColorScheme(Qt.ColorScheme.Light)
        cls.qt.setStyleSheet(STYLE)
        cls.qt.setQuitOnLastWindowClosed(False)

    def test_native_structure_layout_and_startup_scope(self):
        from bluetooth_windows import DeviceInfo, SearchParams, clean_name, address_text
        from windows_integration import RUN_KEY, startup_command
        self.assertEqual(ctypes.sizeof(DeviceInfo), 560)
        self.assertEqual(ctypes.sizeof(SearchParams), 40)
        self.assertEqual(DeviceInfo.name.offset, 64)
        self.assertEqual(clean_name("Unknown device"), "")
        self.assertEqual(clean_name(" My\x00 phone "), "My phone")
        self.assertEqual(address_text(0xAABBCCDDEEFF), "AA:BB:CC:DD:EE:FF")
        self.assertTrue(RUN_KEY.startswith("Software\\Microsoft\\Windows\\CurrentVersion"))
        self.assertIn("pythonw.exe", startup_command())
        self.assertTrue(startup_command().endswith("--background"))

    def test_end_to_end_ui_selection_settings_calibration_and_lock_retries(self):
        from app import Window
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        with test_directory() as tmp:
            window = Window(Path(tmp), demo=True, start_worker=False)
            window.show()
            self.qt.processEvents()
            now = time.monotonic()
            address = "AA:BB:CC:DD:EE:01"
            def observation(transport="ble", live=True, name="My phone", rssi=-55):
                return {"kind": "device", "address": address, "transport": transport, "live": live,
                        "name": name, "rssi": rssi, "time": now, "source": "Bluetooth LE advertisement"}
            window.on_event(observation(live=False))
            self.assertIsNone(window.devices[address].ble_seen)
            window.on_event(observation())
            window.navigate(1)
            window.table.selectRow(0)
            self.assertTrue(window.use_button.isEnabled())
            QTest.mouseClick(window.use_button, Qt.MouseButton.LeftButton)
            self.assertEqual(window.settings.address, address)
            self.assertFalse(window.settings.enabled)
            QTest.mouseClick(window.protect_button, Qt.MouseButton.LeftButton)
            self.assertTrue(window.settings.enabled)
            window.engine.armed = True
            window.tick()
            self.assertEqual(window.last_state, "near")
            window.navigate(2)
            window.threshold_slider.setValue(-82)
            window.grace_spin.setValue(12)
            window.save()
            saved = Settings.load(window.settings_path)
            self.assertEqual((saved.threshold, saved.grace), (-82, 12))
            window.start_calibration()
            window.calibration[1].extend([-55, -57, -53, -55, -56])
            window.finish_calibration()
            self.assertEqual(window.settings.threshold, -67)
            # Failed lock requests are retried without ever using the actual OS lock.
            window.demo = False
            window.settings.missing = 5
            window.settings.grace = 5
            window.engine.armed = True
            window.engine.away_since = time.monotonic() - 50
            window.devices[address].ble_seen = time.monotonic() - 50
            window.lock_retry_at = time.monotonic() + 10
            with patch("app.windows.lock_workstation", side_effect=OSError("test failure")) as locking:
                window.tick()
                self.assertFalse(window.engine.lock_requested)
                self.assertEqual(locking.call_count, 0)
                window.lock_retry_at = 0
                with self.assertLogs(level="ERROR"):
                    window.tick()
                self.assertEqual(locking.call_count, 1)
                self.assertFalse(window.engine.lock_requested)
            window.demo = True
            window.close()
            window.quit_app()

    def test_cached_records_do_not_refresh_presence_or_replace_resolved_name(self):
        from app import Window
        with test_directory() as tmp:
            window = Window(Path(tmp), demo=True, start_worker=False)
            address = "AA:BB:CC:DD:EE:02"
            window.on_event({"kind": "device", "address": address, "transport": "classic", "live": False,
                             "time": time.monotonic(), "name": "My phone", "paired": True, "source": "Windows Bluetooth name"})
            self.assertIsNone(window.devices[address].classic_seen)
            window.on_event({"kind": "device", "address": address, "transport": "ble", "live": True,
                             "time": time.monotonic(), "name": "Unknown", "rssi": -62, "source": "Bluetooth LE advertisement"})
            self.assertEqual(window.devices[address].name, "My phone")
            window.quit_app()


if __name__ == "__main__":
    unittest.main(verbosity=2)
