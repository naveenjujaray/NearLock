"""Local build/verification helpers. Hardware mode discovers; it never locks or pairs."""
import argparse
import json
from pathlib import Path


def icon():
    from PySide6.QtWidgets import QApplication
    from app import make_icon
    app = QApplication([])
    Path("assets").mkdir(exist_ok=True)
    image = make_icon(background=True).pixmap(256, 256)
    if not image.save("assets/nearlock.ico"):
        raise RuntimeError("Qt could not create the Windows icon")
    image.save("assets/nearlock.png")
    print("Application icon created")


def hardware():
    from bluetooth_windows import diagnose_radios
    result = diagnose_radios()
    Path("verification").mkdir(exist_ok=True)
    Path("verification/hardware.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not any(row["ok"] for row in result["health"].values()) or not result["worker_stopped_cleanly"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("icon", "hardware"))
    args = parser.parse_args()
    icon() if args.mode == "icon" else hardware()
