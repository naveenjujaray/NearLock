"""Nearlock — a current-user Windows Bluetooth proximity companion."""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import statistics
import sys
import time

from PySide6.QtCore import Qt, QTimer, QSize, QRectF, QPointF, QLockFile
from PySide6.QtGui import QColor, QPainter, QPen, QIcon, QPixmap, QPainterPath, QLinearGradient, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QStackedWidget, QScrollArea, QCheckBox, QSlider, QSpinBox, QComboBox, QAbstractSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QLineEdit,
    QSystemTrayIcon, QMenu, QMessageBox, QInputDialog,
)

from bluetooth_windows import BluetoothWorker, clean_name
from proximity import Settings, Proximity
import windows_integration as windows

VERSION = "1.0.0"
BLUE = "#0067DA"
INK = "#172134"
MUTED = "#596579"

STYLE = f"""
QWidget {{ font-family: 'Segoe UI Variable Text', 'Segoe UI'; font-size: 14px; color: {INK}; }}
QMainWindow, QWidget#Root {{ background: #F5F6F8; }}
QWidget#PageBody {{ background: #F5F6F8; }}
QFrame#Sidebar {{ background: #ECEEF2; border-right: 1px solid #DBDFE6; }}
QFrame#Card {{ background: white; border: 1px solid #E1E5EB; border-radius: 18px; }}
QFrame#Hero {{ background: #EFF5FF; border: 1px solid #D9E7FC; border-radius: 22px; }}
QLabel {{ background: transparent; border: none; }}
QLabel#Eyebrow {{ color: #456180; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Title {{ font-size: 28px; font-weight: 650; }}
QLabel#HeroTitle {{ font-size: 32px; font-weight: 650; }}
QLabel#SectionTitle {{ font-size: 17px; font-weight: 650; }}
QLabel#Number {{ font-size: 30px; font-weight: 600; }}
QLabel#Badge {{ background: #E7F0FE; color: #24558B; border-radius: 10px; padding: 5px 10px; font-size: 11px; font-weight: 600; }}
QPushButton {{ background: white; border: 1px solid #CCD3DE; border-radius: 9px; padding: 9px 15px; font-weight: 600; min-height: 20px; }}
QPushButton:hover {{ background: #EDF3FC; border-color: #9BAEC9; }}
QPushButton:pressed {{ background: #DDE9FA; }}
QPushButton:disabled {{ color: #798393; background: #ECEFF3; border-color: #E0E4EA; }}
QPushButton#Primary {{ background: {BLUE}; border-color: {BLUE}; color: white; }}
QPushButton#Primary:hover {{ background: #005BC2; }}
QPushButton#Primary:disabled {{ background: #E3E8F0; color: #737F90; border-color: #D9DFE8; }}
QPushButton#Navigation {{ border: none; background: transparent; text-align: left; padding: 11px 14px; }}
QPushButton#Navigation:checked {{ background: #DCE7F8; color: #134C91; }}
QPushButton#Navigation:hover {{ background: #E1E5EC; }}
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {BLUE}; }}
QLineEdit, QComboBox, QSpinBox {{ background: white; border: 1px solid #BDC7D5; border-radius: 8px; padding: 8px 10px; min-height: 22px; }}
QComboBox::drop-down {{ width: 24px; border: none; }}
QComboBox::down-arrow {{ image: none; }}
QSpinBox {{ min-width: 68px; }}
QTableWidget {{ background: white; border: none; gridline-color: #EEF0F4; selection-background-color: #E3EEFF; selection-color: {INK}; outline: none; }}
QTableWidget::item {{ padding: 9px; border-bottom: 1px solid #EEF0F4; }}
QTableWidget::item:focus {{ border: 1px solid {BLUE}; }}
QHeaderView::section {{ background: #F8F9FB; color: {MUTED}; border: none; border-bottom: 1px solid #E4E8EF; padding: 12px 9px; font-size: 12px; font-weight: 600; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #BDC5D2; border-radius: 4px; min-height: 32px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 5px; background: #D8DFEB; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {BLUE}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 20px; margin: -8px 0; background: white; border: 2px solid {BLUE}; border-radius: 11px; }}
QSlider:focus {{ border: 1px solid {BLUE}; border-radius: 6px; }}
QMenu {{ background: white; border: 1px solid #D4DAE4; padding: 5px; }}
QMenu::item {{ padding: 8px 22px; border-radius: 5px; }}
QMenu::item:selected {{ background: #E5EEFC; }}
QToolTip {{ background: #172134; color: white; border: none; padding: 7px; }}
"""


def label(text="", role="", wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(role)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("Primary")
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(callback)
    return widget


def card(title=None):
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    if title:
        layout.addWidget(label(title, "SectionTitle"))
    return frame, layout


def make_icon(kind="lock", color=BLUE, background=False):
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(2, 2)
    if background:
        gradient = QLinearGradient(0, 0, 64, 64)
        gradient.setColorAt(0, QColor("#0073EA"))
        gradient.setColorAt(1, QColor("#3D94F8"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawRoundedRect(QRectF(1, 1, 62, 62), 17, 17)
        color = "white"
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(color), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "bluetooth":
        path = QPainterPath(QPointF(31, 10))
        for x, y in ((45, 22), (19, 44), (31, 54), (31, 10), (19, 21), (45, 43), (31, 54)):
            path.lineTo(x, y)
        p.drawPath(path)
    elif kind == "settings":
        for y, x in ((19, 25), (32, 40), (45, 22)):
            p.drawLine(14, y, 50, y)
            p.setBrush(QColor("#ECEEF2"))
            p.drawEllipse(QPointF(x, y), 4, 4)
    elif kind == "overview":
        for x, y in ((14, 14), (36, 14), (14, 36), (36, 36)):
            p.drawRoundedRect(QRectF(x, y, 14, 14), 3, 3)
    else:
        p.drawArc(QRectF(22, 13, 20, 25), 0, 180 * 16)
        p.setBrush(QColor(color) if not background else QColor("white"))
        p.drawRoundedRect(QRectF(17, 28, 30, 25), 6, 6)
        p.setPen(QPen(QColor(BLUE if background else "white"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(32, 38, 32, 44)
    p.end()
    return QIcon(pixmap)


class Toggle(QCheckBox):
    def __init__(self, name, checked=False):
        super().__init__()
        self.setAccessibleName(name)
        self.setToolTip(name)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(50, 34)

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(BLUE if self.isChecked() else "#818C9D"))
        p.drawRoundedRect(QRectF(4, 5, 42, 24), 12, 12)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(26 if self.isChecked() else 7, 8, 18, 18))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(BLUE), 2, Qt.PenStyle.DotLine))
            p.drawRoundedRect(QRectF(1, 2, 48, 30), 14, 14)


class TrackingCombo(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(MUTED), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        x, y = self.width() - 17, self.height() / 2
        p.drawLine(QPointF(x - 4, y - 2), QPointF(x, y + 2))
        p.drawLine(QPointF(x, y + 2), QPointF(x + 4, y - 2))


class Orbit(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(210, 182)
        self.setAccessibleName("Bluetooth proximity illustration")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(105, 91)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for radius, alpha in ((78, 35), (58, 50), (38, 65)):
            p.setPen(QPen(QColor(40, 113, 221, alpha), 1.3))
            p.drawEllipse(center, radius, radius)
        make_icon(background=True).paint(p, 74, 60, 62, 62)
        p.setPen(QPen(QColor("#BFD5F4"), 1))
        p.setBrush(QColor("white"))
        p.drawRoundedRect(QRectF(161, 43, 29, 43), 7, 7)
        p.setPen(QPen(QColor(BLUE), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(171, 49, 180, 49)
        p.drawLine(173, 79, 178, 79)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#66A4F2"))
        p.drawEllipse(QPointF(52, 137), 4, 4)


class SignalChart(QWidget):
    def __init__(self):
        super().__init__()
        self.samples = deque(maxlen=100)
        self.threshold = -75
        self.setMinimumHeight(100)
        self.setAccessibleName("Live Bluetooth LE signal history")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(0, 12, self.width() - 6, self.height() - 30)
        def y(value):
            return area.bottom() - (max(-100, min(-30, value)) + 100) / 70 * area.height()
        p.setPen(QPen(QColor("#E5EBF3"), 1))
        for value in (-90, -70, -50):
            p.drawLine(QPointF(area.left(), y(value)), QPointF(area.right(), y(value)))
        p.setPen(QPen(QColor("#9AACC2"), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(0, y(self.threshold)), QPointF(area.right(), y(self.threshold)))
        if len(self.samples) < 2:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for a live LE signal")
            return
        path = QPainterPath()
        for i, value in enumerate(self.samples):
            point = QPointF(area.width() * i / (len(self.samples) - 1), y(value))
            path.moveTo(point) if i == 0 else path.lineTo(point)
        p.setPen(QPen(QColor(BLUE), 2.5))
        p.drawPath(path)


@dataclass
class Device:
    address: str
    name: str = ""
    source: str = "Name not advertised"
    paired: bool = False
    connected: bool = False
    transports: set = field(default_factory=set)
    ble_seen: float | None = None
    classic_seen: float | None = None
    samples: deque = field(default_factory=lambda: deque(maxlen=7))
    updated: float = 0

    def display_name(self, settings):
        return settings.aliases.get(self.address) or self.name or f"Bluetooth {'LE' if 'ble' in self.transports else 'Classic'} · {self.address[-8:]}"

    def rssi(self, now, max_age=15):
        samples = [value for at, value in self.samples if now - at <= max_age]
        return statistics.median(samples) if samples else None


class Window(QMainWindow):
    def __init__(self, data_dir: Path, *, demo=False, start_worker=True):
        super().__init__()
        self.demo = demo
        self.data_dir = data_dir
        self.settings_path = data_dir / "settings.json"
        self.load_error = ""
        try:
            self.settings = Settings.load(self.settings_path)
        except (OSError, ValueError, TypeError) as exc:
            self.settings = Settings()
            self.load_error = f"Saved settings could not be loaded. Protection is paused. {exc}"
        self.engine = Proximity(self.settings)
        self.devices = {}
        self.health = {"ble": (False, "Starting Bluetooth LE…"), "classic": (False, "Starting Classic inquiry…")}
        self.worker = BluetoothWorker()
        self.worker.event.connect(self.on_event)
        self.last_state = ""
        self.lock_request_at = None
        self.lock_retry_at = 0
        self.closing = False
        self.calibration = None
        self.setWindowTitle("Nearlock")
        self.setWindowIcon(make_icon(background=True))
        self.resize(1120, 800)
        self.setMinimumSize(920, 650)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save)
        self.build_ui()
        self.build_tray()
        self.session_registered = False
        if not demo:
            try:
                windows.register_session(int(self.winId()))
                self.session_registered = True
            except OSError as exc:
                self.load_error = f"Session tracking is unavailable; protection is paused. {exc}"
                self.settings.enabled = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)
        self.table_timer = QTimer(self)
        self.table_timer.timeout.connect(self.update_table)
        self.table_timer.start(2000)
        if self.settings.address:
            self.devices[self.settings.address] = Device(self.settings.address, self.settings.name,
                                                        transports={self.settings.mode})
        self.worker.configure(self.settings.address, self.settings.reconnect)
        if start_worker:
            self.worker.start()
        self.sync_controls()
        self.tick()
        if self.load_error:
            QTimer.singleShot(500, lambda: self.error(self.load_error))

    def build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        base = QHBoxLayout(root)
        base.setContentsMargins(0, 0, 0, 0)
        base.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(206)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 30, 20, 24)
        side.setSpacing(8)
        logo = label()
        logo.setPixmap(make_icon(background=True).pixmap(48, 48))
        side.addWidget(logo)
        brand = label("Nearlock")
        brand.setStyleSheet("font-size: 25px; font-weight: 650;")
        side.addWidget(brand)
        side.addWidget(label("A little peace of mind.", "Muted"))
        side.addSpacing(30)
        self.nav_buttons = []
        for index, (text, kind) in enumerate((("Overview", "overview"), ("Devices", "bluetooth"), ("Preferences", "settings"))):
            nav = button(text, lambda checked=False, i=index: self.navigate(i))
            nav.setObjectName("Navigation")
            nav.setCheckable(True)
            nav.setIcon(make_icon(kind, MUTED))
            nav.setIconSize(QSize(21, 21))
            side.addWidget(nav)
            self.nav_buttons.append(nav)
        side.addStretch()
        self.sidebar_status = label("Getting ready", "Muted", True)
        side.addWidget(self.sidebar_status)
        side.addSpacing(8)
        side.addWidget(label("PRIVATE BY DESIGN", "Eyebrow"))
        side.addWidget(label("Lives on your PC.\nNo account needed.", "Muted", True))
        side.addSpacing(16)
        side.addWidget(label(f"Nearlock  {VERSION}", "Muted"))
        base.addWidget(sidebar)
        self.pages = QStackedWidget()
        base.addWidget(self.pages, 1)
        self.overview_page()
        self.devices_page()
        self.preferences_page()
        self.navigate(0)

    def page(self, title, subtitle):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("PageBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(30, 28, 30, 24)
        layout.setSpacing(18)
        top = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label(title, "Title"))
        titles.addWidget(label(subtitle, "Muted", True))
        top.addLayout(titles, 1)
        top.addWidget(label("WINDOWS 11", "Badge"), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)
        scroll.setWidget(body)
        self.pages.addWidget(scroll)
        return layout

    def overview_page(self):
        layout = self.page("Overview", "A quieter way to keep your workspace secure.")
        hero = QFrame()
        hero.setObjectName("Hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(26, 22, 14, 22)
        content = QVBoxLayout()
        content.setSpacing(12)
        self.hero_badge = label("READY WHEN YOU ARE", "Eyebrow")
        self.hero_title = label("Your space. Secured.", "HeroTitle", True)
        self.hero_detail = label("Choose the device you take with you.", "Muted", True)
        content.addWidget(self.hero_badge)
        content.addWidget(self.hero_title)
        content.addWidget(self.hero_detail)
        content.addSpacing(5)
        actions = QHBoxLayout()
        self.protect_button = button("Choose a device", self.toggle_protection, True)
        actions.addWidget(self.protect_button)
        actions.addStretch()
        content.addLayout(actions)
        hero_layout.addLayout(content, 1)
        hero_layout.addWidget(Orbit())
        layout.addWidget(hero)
        row = QHBoxLayout()
        row.setSpacing(16)
        device_card, device_layout = card()
        device_layout.addWidget(label("YOUR COMPANION", "Eyebrow"))
        self.companion_name = label("No device selected", "SectionTitle", True)
        self.companion_detail = label("A phone, watch, or Bluetooth tag.", "Muted", True)
        device_layout.addWidget(self.companion_name)
        device_layout.addWidget(self.companion_detail)
        device_layout.addStretch()
        device_layout.addWidget(button("Manage devices", lambda: self.navigate(1)))
        row.addWidget(device_card, 1)
        range_card, range_layout = card()
        range_layout.addWidget(label("LIVE SIGNAL", "Eyebrow"))
        self.signal_value = label("—", "Number")
        self.signal_caption = label("BLE signal appears here.", "Muted", True)
        range_layout.addWidget(self.signal_value)
        range_layout.addWidget(self.signal_caption)
        self.chart = SignalChart()
        range_layout.addWidget(self.chart)
        row.addWidget(range_card, 1)
        layout.addLayout(row)
        flow, flow_layout = card("Made for stepping away")
        steps = QHBoxLayout()
        for title, text in (("01  Stay nearby", "Your chosen device keeps protection armed."),
                            ("02  Step away", "Windows locks after your configured delay."),
                            ("03  Come back", "Sign in with Windows Hello or your PIN.")):
            column = QVBoxLayout()
            column.addWidget(label(title, "SectionTitle"))
            column.addWidget(label(text, "Muted", True))
            steps.addLayout(column, 1)
        flow_layout.addLayout(steps)
        layout.addWidget(flow)
        self.status_line = label("Looking for Bluetooth devices…", "Muted", True)
        layout.addWidget(self.status_line)
        layout.addStretch()

    def devices_page(self):
        layout = self.page("Devices", "Find the companion that goes where you go.")
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name or Bluetooth address")
        self.search.setAccessibleName("Search discovered devices")
        self.search.textChanged.connect(self.update_table)
        controls.addWidget(self.search, 1)
        controls.addWidget(button("Refresh", self.worker.refresh))
        controls.addWidget(button("Pair in Windows", lambda: self.open_settings("ms-settings:bluetooth")))
        layout.addLayout(controls)
        self.discovery_status = label("Listening for Bluetooth Classic and LE…", "Muted", True)
        layout.addWidget(self.discovery_status)
        table_card, table_layout = card()
        table_layout.setContentsMargins(8, 10, 8, 12)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["DEVICE", "BLUETOOTH", "SIGNAL", "STATUS"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index, width in ((1, 124), (2, 86), (3, 128)):
            self.table.setColumnWidth(index, width)
        self.table.setMinimumHeight(250)
        self.table.setAccessibleName("Nearby and remembered Bluetooth devices")
        self.table.itemSelectionChanged.connect(self.selection_changed)
        table_layout.addWidget(self.table)
        layout.addWidget(table_card, 1)
        self.device_detail = label("Select a device to inspect its name and choose how to track it.", "Muted", True)
        layout.addWidget(self.device_detail)
        actions = QHBoxLayout()
        self.track_mode = TrackingCombo()
        self.track_mode.setAccessibleName("Tracking method for the selected device")
        self.track_mode.addItem("Bluetooth LE · signal range", "ble")
        self.track_mode.addItem("Bluetooth Classic · presence", "classic")
        actions.addWidget(self.track_mode, 1)
        self.name_button = button("Read name", self.read_device_name)
        self.alias_button = button("Nickname", self.nickname)
        self.use_button = button("Use this device", self.use_device, True)
        for widget in (self.name_button, self.alias_button, self.use_button):
            widget.setEnabled(False)
            actions.addWidget(widget)
        layout.addLayout(actions)
        layout.addWidget(label("Some devices hide their name or rotate their LE address. Pairing can help; a nickname is always available. Classic presence requires a discoverable or connected device.", "Muted", True))

    def preference_row(self, layout, title, description, control):
        row = QHBoxLayout()
        words = QVBoxLayout()
        words.setSpacing(4)
        words.addWidget(label(title, "SectionTitle"))
        words.addWidget(label(description, "Muted", True))
        row.addLayout(words, 1)
        row.addSpacing(20)
        row.addWidget(control)
        layout.addLayout(row)

    def preferences_page(self):
        layout = self.page("Preferences", "Make proximity feel right for your space.")
        proximity_card, proximity_layout = card("Lock range")
        self.range_description = label("BLE signal strength is a guide to proximity, not a distance in metres.", "Muted", True)
        proximity_layout.addWidget(self.range_description)
        self.threshold_label = label(f"Lock below {self.settings.threshold} dBm · return above {self.settings.threshold + 6} dBm", "SectionTitle")
        proximity_layout.addWidget(self.threshold_label)
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(-95, -40)
        self.threshold_slider.setValue(self.settings.threshold)
        self.threshold_slider.setAccessibleName("Bluetooth LE lock signal threshold in dBm")
        self.threshold_slider.valueChanged.connect(self.change_threshold)
        proximity_layout.addWidget(self.threshold_slider)
        scale = QHBoxLayout()
        scale.addWidget(label("Farther away", "Muted"))
        scale.addStretch()
        scale.addWidget(label("Closer to your PC", "Muted"))
        proximity_layout.addLayout(scale)
        self.calibrate_button = button("Calibrate at my desk", self.start_calibration)
        self.preference_row(proximity_layout, "Find a comfortable range", "Keep your device beside you for an 8-second reading.", self.calibrate_button)
        layout.addWidget(proximity_card)
        timing_card, timing_layout = card()
        self.grace_spin = QSpinBox()
        self.grace_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.grace_spin.setRange(5, 120)
        self.grace_spin.setSuffix(" s")
        self.grace_spin.setValue(self.settings.grace)
        self.grace_spin.setAccessibleName("Delay before locking when device is away")
        self.grace_spin.valueChanged.connect(lambda value: self.setting_changed("grace", value))
        self.preference_row(timing_layout, "Wait before locking", "A continuous delay gives brief signal dips time to recover.", self.grace_spin)
        self.missing_spin = QSpinBox()
        self.missing_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.missing_spin.setRange(5, 90)
        self.missing_spin.setSuffix(" s")
        self.missing_spin.setValue(self.settings.missing)
        self.missing_spin.setAccessibleName("Seconds without a signal before device is considered missing")
        self.missing_spin.valueChanged.connect(lambda value: self.setting_changed("missing", value))
        self.preference_row(timing_layout, "Allow signal silence", "After this time without a sighting, the lock delay begins.", self.missing_spin)
        layout.addWidget(timing_card)
        behavior, behavior_layout = card()
        self.startup_toggle = Toggle("Launch at Windows sign-in", False if self.demo else windows.startup_enabled())
        self.startup_toggle.toggled.connect(self.change_startup)
        self.preference_row(behavior_layout, "Launch at sign-in", "Start quietly in the tray for your Windows account.", self.startup_toggle)
        self.reconnect_toggle = Toggle("Automatically reconnect to read selected LE device name", self.settings.reconnect)
        self.reconnect_toggle.toggled.connect(lambda value: self.setting_changed("reconnect", value))
        self.preference_row(behavior_layout, "Reconnect to read the LE name", "Briefly connect to your chosen device when it returns, then resume signal scanning.", self.reconnect_toggle)
        self.return_toggle = Toggle("Notify when the selected device returns", self.settings.notify_return)
        self.return_toggle.toggled.connect(lambda value: self.setting_changed("notify_return", value))
        self.preference_row(behavior_layout, "Welcome-back notification", "Detect your return while Windows stays securely locked.", self.return_toggle)
        layout.addWidget(behavior)
        signin, signin_layout = card("Returning to your PC")
        signin_layout.addWidget(label("Windows requires Windows Hello, a PIN, or a password to unlock. Bluetooth-only automatic unlock is not available to a standard-user app. Nearlock never stores your credentials.", "Muted", True))
        links = QHBoxLayout()
        links.addWidget(button("Set up Windows Hello", lambda: self.open_settings("ms-settings:signinoptions")))
        links.addWidget(button("Open local logs", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data_dir)))))
        links.addStretch()
        signin_layout.addLayout(links)
        layout.addWidget(signin)
        layout.addWidget(label("Changes save automatically. Closing the window keeps protection in the tray. Choose Quit from the tray menu to stop it.", "Muted", True))
        layout.addStretch()

    def build_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Nearlock · choose a device to get started")
        menu = QMenu()
        menu.addAction("Open Nearlock", self.show_window)
        self.tray_toggle = menu.addAction("Resume protection", self.toggle_protection)
        menu.addAction("Lock Windows now", self.manual_lock)
        menu.addSeparator()
        menu.addAction("Preferences", lambda: (self.show_window(), self.navigate(2)))
        menu.addAction("Quit Nearlock", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window() if reason in (
            QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self.tray.messageClicked.connect(self.show_window)
        if not self.demo:
            self.tray.show()

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav_buttons):
            nav.setChecked(i == index)
        if index == 1:
            self.update_table()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_settings(self, url):
        if not self.demo and not QDesktopServices.openUrl(QUrl(url)):
            self.error("Windows Settings could not be opened. Open it from the Start menu.")

    def error(self, text):
        logging.warning(text)
        QMessageBox.warning(self, "Nearlock", text)

    def save(self):
        try:
            self.settings.save(self.settings_path)
        except OSError as exc:
            self.error(f"Settings could not be saved. {exc}")

    def setting_changed(self, key, value):
        setattr(self.settings, key, value)
        self.save_timer.start(400)
        if key == "reconnect":
            self.worker.configure(self.settings.address, self.settings.reconnect)

    def change_threshold(self, value):
        self.setting_changed("threshold", value)
        self.threshold_label.setText(f"Lock below {value} dBm · return above {value + 6} dBm")
        self.chart.threshold = value
        self.chart.update()

    def change_startup(self, enabled):
        if self.demo:
            return
        try:
            windows.set_startup(enabled)
        except OSError as exc:
            self.startup_toggle.blockSignals(True)
            self.startup_toggle.setChecked(not enabled)
            self.startup_toggle.blockSignals(False)
            self.error(f"Windows did not allow the sign-in preference to change. {exc}")

    def toggle_protection(self):
        if not self.settings.address:
            self.show_window()
            self.navigate(1)
            return
        if not self.demo and not self.session_registered:
            self.error("Session tracking is unavailable. Restart Nearlock before enabling protection.")
            return
        self.settings.enabled = not self.settings.enabled
        self.engine.reset()
        self.save()
        self.sync_controls()
        self.tick()

    def sync_controls(self):
        has_target = bool(self.settings.address)
        self.protect_button.setText("Pause protection" if self.settings.enabled else "Enable protection" if has_target else "Choose a device")
        self.tray_toggle.setText("Pause protection" if self.settings.enabled else "Resume protection")
        self.tray_toggle.setEnabled(has_target)
        le_mode = self.settings.mode == "ble"
        self.threshold_slider.setEnabled(le_mode)
        self.calibrate_button.setEnabled(le_mode and has_target and self.calibration is None)
        self.range_description.setText("BLE signal strength is a guide to proximity, not a distance in metres." if le_mode else
                                       "Classic tracks presence and disconnection. Signal-based range needs an advertising LE device.")
        self.chart.threshold = self.settings.threshold

    def on_event(self, event):
        kind = event["kind"]
        if kind == "health":
            previous = self.health[event["transport"]]
            self.health[event["transport"]] = (event["ok"], event["message"])
            if not event["ok"] and previous != self.health[event["transport"]]:
                logging.warning("%s: %s", event["transport"], event["message"])
            return
        if kind in ("connection", "name_result"):
            self.device_detail.setText(event["message"])
            if kind == "name_result":
                self.name_button.setEnabled(bool(self.selected_device() and "ble" in self.selected_device().transports))
            return
        if kind != "device":
            return
        address = event["address"]
        device = self.devices.setdefault(address, Device(address))
        device.transports.add(event["transport"])
        device.updated = event["time"]
        name = clean_name(event.get("name"))
        if name and (not device.name or event["source"] != "Bluetooth LE advertisement" or device.source == "Bluetooth LE advertisement"):
            device.name = name
            device.source = event["source"]
            if address == self.settings.address and self.settings.name != name:
                self.settings.name = name
                self.save_timer.start(400)
        device.paired |= event.get("paired", False)
        if event["transport"] == "classic":
            device.connected = event.get("connected", False)
        if event.get("live"):
            if event["transport"] == "ble":
                value = event.get("rssi")
                if value is not None:
                    device.ble_seen = event["time"]
                    device.samples.append((event["time"], value))
                    if address == self.settings.address:
                        self.chart.samples.append(value)
                        self.chart.update()
                        if self.calibration is not None:
                            self.calibration[1].append(value)
            else:
                device.classic_seen = event["time"]
        if len(self.devices) > 400:
            cutoff = time.monotonic() - 180
            self.devices = {key: item for key, item in self.devices.items()
                            if key == self.settings.address or item.paired or item.updated >= cutoff}

    def selected_device(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return self.devices.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def selection_changed(self):
        device = self.selected_device()
        for widget in (self.use_button, self.alias_button):
            widget.setEnabled(device is not None)
        self.name_button.setEnabled(device is not None and "ble" in device.transports)
        if not device:
            return
        self.device_detail.setText(f"{device.address}  ·  {device.source}" + ("  ·  Paired with Windows" if device.paired else ""))
        for index, transport in enumerate(("ble", "classic")):
            self.track_mode.model().item(index).setEnabled(transport in device.transports)
        self.track_mode.setCurrentIndex(0 if "ble" in device.transports else 1)

    def update_table(self):
        if not hasattr(self, "table"):
            return
        selected = self.selected_device()
        chosen = selected.address if selected else None
        now = time.monotonic()
        query = self.search.text().strip().lower()
        def live(device):
            return any(seen is not None and now - seen <= self.settings.missing for seen in (device.ble_seen, device.classic_seen))
        devices = [d for d in self.devices.values() if query in f"{d.display_name(self.settings)} {d.address}".lower()]
        devices.sort(key=lambda d: (d.address != self.settings.address, not live(d), not d.paired, not bool(d.name), d.display_name(self.settings).lower()))
        self.table.blockSignals(True)
        self.table.setRowCount(len(devices))
        selected_row = None
        for row, device in enumerate(devices):
            signal = device.rssi(now, self.settings.missing)
            name = device.display_name(self.settings)
            status = "Selected" if device.address == self.settings.address else "Connected" if device.connected and live(device) else "Nearby" if live(device) else "Paired" if device.paired else "Not seen"
            values = (name, "Classic + LE" if len(device.transports) == 2 else "LE" if "ble" in device.transports else "Classic",
                      f"{round(signal)} dBm" if signal is not None else "—", status)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(f"{name}\n{device.address}\n{device.source}")
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, device.address)
                self.table.setItem(row, col, item)
            if device.address == chosen:
                selected_row = row
        if selected_row is not None:
            self.table.selectRow(selected_row)
        else:
            self.table.clearSelection()
            self.table.setCurrentItem(None)
        self.table.blockSignals(False)
        if selected_row is None:
            self.selection_changed()
        statuses = ["LE active" if self.health["ble"][0] else "LE unavailable", "Classic active" if self.health["classic"][0] else "Classic unavailable"]
        self.discovery_status.setText(f"{len(devices)} devices  ·  " + "  ·  ".join(statuses))

    def read_device_name(self):
        device = self.selected_device()
        if device:
            self.name_button.setEnabled(False)
            self.device_detail.setText("Connecting to read the advertised device's name…")
            self.worker.read_name(device.address)

    def nickname(self):
        device = self.selected_device()
        if device:
            text, ok = QInputDialog.getText(self, "Name your companion", "Device nickname", text=self.settings.aliases.get(device.address, device.name))
            if ok:
                if text.strip():
                    self.settings.aliases[device.address] = clean_name(text) or text.strip()[:120]
                else:
                    self.settings.aliases.pop(device.address, None)
                self.save()
                self.update_table()

    def use_device(self):
        device = self.selected_device()
        if not device:
            return
        self.settings.address = device.address
        self.settings.name = device.name
        self.settings.mode = self.track_mode.currentData()
        # Choosing a target is separate from starting a security action.
        self.settings.enabled = False
        self.engine.reset()
        self.chart.samples.clear()
        self.calibration = None
        self.calibrate_button.setText("Calibrate at my desk")
        self.worker.configure(self.settings.address, self.settings.reconnect)
        self.save()
        self.sync_controls()
        self.tick()
        self.navigate(0)

    def start_calibration(self):
        device = self.devices.get(self.settings.address)
        if not device or device.rssi(time.monotonic()) is None:
            self.error("Wait for a live LE signal, then keep the selected device beside your PC.")
            return
        self.calibration = (time.monotonic() + 8, [])
        self.calibrate_button.setEnabled(False)

    def finish_calibration(self):
        readings = self.calibration[1]
        self.calibration = None
        self.calibrate_button.setText("Calibrate at my desk")
        self.sync_controls()
        if len(readings) < 4:
            self.error("Not enough fresh signal readings. Keep the device advertising and try again.")
            return
        self.threshold_slider.setValue(max(-95, min(-40, round(statistics.median(readings) - 12))))
        self.status_line.setText("Desk calibration saved. Test your range before relying on automatic locking.")

    def tick(self):
        now = time.monotonic()
        device = self.devices.get(self.settings.address)
        seen = None
        rssi = None
        if device:
            seen = device.ble_seen if self.settings.mode == "ble" else device.classic_seen
            rssi = device.rssi(now, self.settings.missing)
            self.companion_name.setText(device.display_name(self.settings))
            self.companion_detail.setText(("Bluetooth LE · signal range" if self.settings.mode == "ble" else "Bluetooth Classic · presence") + "\n" + device.address)
        decision = self.engine.tick(now, seen, rssi)
        self.hero_title.setText(decision.title)
        self.hero_detail.setText(decision.detail)
        badges = {"setup": "READY WHEN YOU ARE", "paused": "PROTECTION PAUSED", "waiting": "GETTING READY", "near": "PROTECTION ACTIVE", "away": "DEVICE OUT OF RANGE", "locking": "LOCK REQUESTED", "locked": "WINDOWS SESSION LOCKED"}
        self.hero_badge.setText(badges[decision.state])
        self.sidebar_status.setText(decision.title)
        if self.settings.mode == "classic" and device:
            self.signal_value.setText("Present" if seen is not None and now - seen <= self.settings.missing else "Not seen")
            self.signal_caption.setText("Classic uses presence, without RSSI.")
        else:
            self.signal_value.setText(f"{round(rssi)} dBm" if rssi is not None else "—")
            self.signal_caption.setText(f"Lock threshold {self.settings.threshold} dBm" if device else "Choose an LE device to see its signal.")
        errors = [message for ok, message in self.health.values() if not ok]
        self.status_line.setText(" · ".join(errors) if errors else "Bluetooth Classic + LE active  ·  Everything stays on this PC")
        if decision.state != self.last_state:
            logging.info("Proximity state: %s", decision.state)
            self.tray.setToolTip(f"Nearlock · {decision.title}")
            self.last_state = decision.state
        if decision.lock:
            if now >= self.lock_retry_at:
                self.request_lock()
            else:
                self.engine.lock_requested = False
        if self.lock_request_at is not None and now - self.lock_request_at > 8:
            # LockWorkStation is asynchronous; only WTS can confirm success.
            self.lock_request_at = None
            self.engine.lock_requested = False
            self.engine.away_since = now
            self.lock_retry_at = now + 10
            self.status_line.setText("Windows did not confirm the lock. Retrying after the delay.")
            self.notify("Lock not confirmed", "Windows did not confirm the lock. Use Win+L and check your Windows policy.")
        if decision.returned and self.settings.notify_return:
            self.notify("Welcome back", "Your device is nearby. Sign in with Windows Hello or your PIN.")
        if self.calibration:
            remaining = max(0, int(self.calibration[0] - now) + 1)
            self.calibrate_button.setText(f"Measuring… {remaining}s")
            if now >= self.calibration[0]:
                self.finish_calibration()

    def request_lock(self):
        if self.demo:
            self.engine.session(True)
            return
        try:
            windows.lock_workstation()
            self.lock_request_at = time.monotonic()
        except OSError as exc:
            self.engine.lock_requested = False
            self.engine.away_since = time.monotonic()
            self.lock_retry_at = time.monotonic() + 10
            self.notify("Windows could not lock", str(exc))
            logging.exception("LockWorkStation failed")

    def manual_lock(self):
        self.request_lock()

    def notify(self, title, message):
        if not self.demo and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def nativeEvent(self, event_type, message):
        event = windows.native_event(message)
        if event:
            kind, value = event
            if kind == "session":
                self.engine.session(value)
                self.lock_request_at = None
                logging.info("Windows session %s", "locked" if value else "unlocked")
            elif kind == "resume":
                self.engine.reset()
                for device in self.devices.values():
                    device.ble_seen = device.classic_seen = None
                    device.samples.clear()
                self.worker.refresh()
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event):
        if self.closing:
            event.accept()
        elif QSystemTrayIcon.isSystemTrayAvailable() and not self.demo:
            self.hide()
            event.ignore()
            self.notify("Nearlock is in your tray", "Protection keeps running. Open the tray icon to return or quit.")
        else:
            self.quit_app()
            event.accept()

    def quit_app(self):
        self.closing = True
        self.timer.stop()
        self.table_timer.stop()
        self.worker.stop()
        if self.save_timer.isActive():
            self.save_timer.stop()
            self.save()
        if self.session_registered:
            windows.unregister_session(int(self.winId()))
        self.tray.hide()
        QApplication.instance().quit()


def main():
    parser = argparse.ArgumentParser(description="Nearlock Bluetooth dynamic lock for Windows")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--install-startup", action="store_true")
    parser.add_argument("--remove-startup", action="store_true")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--smoke-test", action="store_true", help="Render the real interface with isolated example data; never lock Windows")
    parser.add_argument("--diagnose", action="store_true", help="Check live Bluetooth discovery for 20 seconds without connecting or locking")
    args = parser.parse_args()
    if (args.smoke_test or args.diagnose) and not args.data_dir:
        parser.error("Verification requires --data-dir pointing to a separate output folder.")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Nearlock")
    app.setOrganizationName("Nearlock")
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    if args.install_startup or args.remove_startup:
        windows.set_startup(args.install_startup)
        return 0
    data_dir = args.data_dir or (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Nearlock")
    data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(data_dir / "nearlock.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=[handler])
    if args.diagnose:
        from bluetooth_windows import diagnose_radios
        report = diagnose_radios()
        report["packaged"] = bool(getattr(sys, "frozen", False))
        report["tray_supported"] = QSystemTrayIcon.isSystemTrayAvailable()
        (data_dir / "hardware.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0 if report["worker_stopped_cleanly"] and any(v["ok"] for v in report["health"].values()) else 1
    lockfile = QLockFile(str(data_dir / "instance.lock"))
    lockfile.setStaleLockTime(0)
    if not args.smoke_test and not lockfile.tryLock(0):
        if not args.background:
            QMessageBox.information(None, "Nearlock is running", "Open Nearlock from the Bluetooth lock icon in the Windows system tray.")
        return 0
    window = Window(data_dir, demo=args.smoke_test, start_worker=not args.smoke_test)
    if args.smoke_test:
        now = time.monotonic()
        for address, name, transport, rssi in (
            ("AA:BB:CC:DD:EE:01", "My phone", "ble", -57),
            ("AA:BB:CC:DD:EE:02", "Wireless headphones", "classic", None),
            ("AA:BB:CC:DD:EE:03", "Desk keyboard", "classic", None),
        ):
            for n in range(8):
                window.on_event({"kind": "device", "address": address, "name": name,
                    "transport": transport, "source": "Example data for UI verification", "live": True,
                    "time": now, "rssi": rssi + n % 3 if rssi else None, "paired": True})
        window.settings.address = "AA:BB:CC:DD:EE:01"
        window.settings.enabled = True
        window.settings.name = "My phone"
        window.engine.armed = True
        window.health = {"ble": (True, "Example"), "classic": (True, "Example")}
        window.chart.samples.extend([-61, -59, -60, -58, -59, -57, -56, -58, -57, -56, -57, -55, -57, -58, -56])
        window.sync_controls()
        window.tick()
        window.show()
        def capture():
            for index, name in enumerate(("overview", "devices", "preferences")):
                window.navigate(index)
                app.processEvents()
                window.grab().save(str(data_dir / f"{name}.png"))
            (data_dir / "smoke-result.json").write_text(json.dumps({"ok": True, "version": VERSION,
                "pages": 3, "example_data": True, "tray_supported": QSystemTrayIcon.isSystemTrayAvailable()}), encoding="utf-8")
            window.quit_app()
        QTimer.singleShot(500, capture)
    elif not args.background or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show()
    result = app.exec()
    window.worker.stop()
    if window.worker.thread:
        window.worker.thread.join(timeout=18)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
