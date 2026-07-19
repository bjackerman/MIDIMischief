"""Devices & Live Monitor tab.

Left: tree of available MIDI/HID devices with a Refresh button and
Connect/Disconnect actions.

Right: live event table fed by an :class:`EventBusQtBridge`.

This is intentionally minimal in M4; the device render widget (visual
pads/knobs) is on the to-do list and lands in M5 polish. The live event
table is the most useful debug surface even without a render.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...devices.manager import DeviceManager
from ...events import NormalizedEvent
from ...gui.qt_bridge import EventBusQtBridge
from ...gui.widgets.event_table import EventTableModel, EventTableView

log = logging.getLogger(__name__)


class DevicesTab(QWidget):
    """Devices + Live Monitor tab."""

    def __init__(self, manager: DeviceManager, bridge: EventBusQtBridge, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._manager = manager
        self._bridge = bridge

        # ---- left: device list + controls ----
        self._device_list = QListWidget(self)
        self._device_list.setAlternatingRowColors(True)
        self._connect_btn = QPushButton("Connect", self)
        self._disconnect_btn = QPushButton("Disconnect", self)
        self._refresh_btn = QPushButton("Refresh", self)
        self._filter_edit = QLineEdit(self)
        self._filter_edit.setPlaceholderText("Filter by name…")
        self._status_label = QLabel("0 devices", self)

        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        self._refresh_btn.clicked.connect(self._refresh)
        self._filter_edit.textChanged.connect(self._apply_filter)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Devices"))
        left_layout.addWidget(self._filter_edit)
        left_layout.addWidget(self._device_list, 1)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._disconnect_btn)
        btn_row.addWidget(self._refresh_btn)
        left_layout.addLayout(btn_row)
        left_layout.addWidget(self._status_label)

        # ---- right: live event table ----
        self._event_model = EventTableModel()
        self._event_view = EventTableView(self._event_model, self)
        self._clear_btn = QPushButton("Clear", self)
        self._pause_btn = QPushButton("Pause", self)
        self._pause_btn.setCheckable(True)
        self._clear_btn.clicked.connect(self._event_model.clear)
        self._pause_btn.toggled.connect(self._set_paused)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Live event monitor (newest first)"))
        right_layout.addWidget(self._event_view, 1)
        controls = QHBoxLayout()
        controls.addWidget(self._pause_btn)
        controls.addWidget(self._clear_btn)
        controls.addStretch(1)
        right_layout.addLayout(controls)

        # ---- splitter ----
        splitter = QSplitter(self)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([300, 900])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(splitter)

        # ---- wiring ----
        self._bridge.event_received.connect(self._on_event)
        self._paused = False

        # ---- periodic refresh of the device list ----
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start()
        self._refresh()

    # ---- slots ----

    @Slot(object)
    def _on_event(self, ev: NormalizedEvent) -> None:
        if self._paused:
            return
        self._event_model.append_event(ev)

    @Slot()
    def _refresh(self) -> None:
        try:
            devices = self._manager.list_devices()
        except Exception as e:  # pragma: no cover — backend failure
            log.exception("device list failed")
            self._status_label.setText(f"error: {e}")
            return
        self._device_list.clear()
        for d in devices:
            label = f"{d['name']}  ({d['id']})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, d)
            self._device_list.addItem(item)
        self._status_label.setText(f"{len(devices)} device(s)")

    @Slot()
    def _on_connect(self) -> None:
        item = self._device_list.currentItem()
        if item is None:
            return
        d = item.data(Qt.UserRole)
        try:
            self._manager.connect(d["id"])
        except Exception as e:
            log.error("connect failed: %s", e)
            self._status_label.setText(f"connect failed: {e}")

    @Slot()
    def _on_disconnect(self) -> None:
        item = self._device_list.currentItem()
        if item is None:
            return
        d = item.data(Qt.UserRole)
        try:
            self._manager.disconnect(d["id"])
        except Exception as e:
            log.error("disconnect failed: %s", e)

    @Slot(bool)
    def _set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._pause_btn.setText("Resume" if paused else "Pause")

    @Slot(str)
    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self._device_list.count()):
            item = self._device_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())


# Re-export Qt so callers don't have to import it.
from PySide6.QtCore import Qt  # noqa: E402

__all__ = ["DevicesTab"]
