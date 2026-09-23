"""Settings and the deterministic proximity policy. No Windows calls here."""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Settings:
    address: str = ""
    name: str = ""
    mode: str = "ble"
    enabled: bool = False
    threshold: int = -75
    grace: int = 20
    missing: int = 15
    reconnect: bool = True
    notify_return: bool = True
    aliases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Settings must be a JSON object.")
        settings = cls()
        for key in asdict(settings):
            if key in data:
                setattr(settings, key, data[key])
        if not isinstance(settings.address, str) or (settings.address and not re.fullmatch(
            r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", settings.address
        )):
            raise ValueError("Invalid Bluetooth address in settings.")
        settings.address = settings.address.upper()
        if settings.mode not in ("ble", "classic"):
            raise ValueError("Invalid tracking mode.")
        for key, low, high in (("threshold", -95, -40), ("grace", 5, 120), ("missing", 5, 90)):
            value = getattr(settings, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Invalid {key} in settings.")
        for key in ("enabled", "reconnect", "notify_return"):
            if type(getattr(settings, key)) is not bool:
                raise ValueError(f"Invalid {key} in settings.")
        if not isinstance(settings.name, str) or not isinstance(settings.aliases, dict):
            raise ValueError("Invalid device names in settings.")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in settings.aliases.items()):
            raise ValueError("Invalid aliases in settings.")
        return settings

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        temporary.replace(path)


@dataclass
class Decision:
    title: str
    detail: str
    state: str
    lock: bool = False
    returned: bool = False
    remaining: int | None = None


class Proximity:
    """Observe nearby first; hysteresis and a continuous grace period prevent flapping."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.reset()

    def reset(self) -> None:
        self.armed = False
        self.near_since = None
        self.away_since = None
        self.lock_requested = False
        self.locked = False
        self.return_notified = False

    def session(self, locked: bool) -> None:
        if locked:
            self.locked = True
            self.lock_requested = False
            self.return_notified = False
        else:
            self.reset()

    def tick(self, now: float, seen: float | None, rssi: float | None) -> Decision:
        s = self.settings
        if not s.address:
            return Decision("Your space. Secured.", "Choose the device you take with you.", "setup")
        if not s.enabled:
            return Decision("Protection is paused", "Discovery stays on. Automatic locking is off.", "paused")
        fresh = seen is not None and 0 <= now - seen <= s.missing
        strong = fresh and (s.mode == "classic" or (rssi is not None and rssi >= s.threshold + 6))
        weak = not fresh or (s.mode == "ble" and (rssi is None or rssi <= s.threshold))
        if self.locked:
            returned = strong and not self.return_notified
            self.return_notified |= strong
            return Decision(
                "Welcome back" if strong else "Windows is locked",
                "Use Windows Hello or your PIN to sign in." if strong else "Looking for your device to return.",
                "locked", returned=returned,
            )
        if self.lock_requested:
            return Decision("Lock requested", "Waiting for Windows to confirm the session is locked.", "locking")
        if not self.armed:
            if strong:
                if self.near_since is None:
                    self.near_since = now
                # Require another live observation, not repeated evaluation of one old packet.
                if now - self.near_since >= 3 and seen >= self.near_since:
                    self.armed = True
            else:
                self.near_since = None
            if not self.armed:
                return Decision("Waiting for your device", "Keep it nearby for a few seconds to arm protection.", "waiting")
        if self.away_since is not None:
            if strong:
                self.away_since = None
        elif weak:
            self.away_since = now
        if self.away_since is not None:
            remaining = max(0, math.ceil(s.grace - (now - self.away_since)))
            if remaining == 0:
                self.lock_requested = True
                return Decision("Lock requested", "Your device stayed outside the configured range.", "locking", lock=True)
            return Decision(f"Locking in {remaining}s", "Your device is away. Bring it closer to cancel.", "away", remaining=remaining)
        return Decision("You're in range", "We'll lock Windows when your device moves away.", "near")
