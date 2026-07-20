"""Devices & Live Monitor tab.

Left: tree of available MIDI/HID devices with a Refresh button and
Connect/Disconnect actions.

Right: a descriptor-driven control-surface monitor and a live event table,
both fed by an :class:`EventBusQtBridge`.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer, Signal, Slot
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
from ...gui.widgets.device_render import DeviceRenderWidget
from ...gui.widgets.event_table import EventTableModel, EventTableView

log = logging.getLogger(__name__)


class DevicesTab(QWidget):
    """Devices + Live Monitor tab.

    Forwards a right-click "Bind this control…" request from the
    event table via :attr:`event_bound`. The main window listens
    for this signal and opens the binding wizard pre-filled.
    """

    event_bound = Signal(object)  # NormalizedEvent

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
        self._device_list.currentItemChanged.connect(self._on_device_selected)

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

        # ---- right: descriptor render + live event table ----
        self._device_render = DeviceRenderWidget(parent=self)
        self._event_model = EventTableModel()
        self._event_view = EventTableView(self._event_model, self)
        self._clear_btn = QPushButton("Clear", self)
        self._pause_btn = QPushButton("Pause", self)
        self._pause_btn.setCheckable(True)
        self._bind_btn = QPushButton("Map this event…", self)
        self._bind_btn.setToolTip(
            "Select a row in the event table, then click to open the\n"
            "binding wizard pre-filled with the captured control.\n"
            "(Right-click the row for the same action.)"
        )
        self._bind_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self._event_model.clear)
        self._pause_btn.toggled.connect(self._set_paused)
        self._bind_btn.clicked.connect(self._on_bind_clicked)
        self._event_view.event_bound.connect(self.event_bound.emit)
        self._event_view.selectionModel().selectionChanged.connect(
            self._on_event_selection_changed
        )

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Control surface"))
        right_layout.addWidget(self._device_render, 1)
        right_layout.addWidget(QLabel("Live event monitor (newest first)"))
        right_layout.addWidget(self._event_view, 2)
        controls = QHBoxLayout()
        controls.addWidget(self._pause_btn)
        controls.addWidget(self._clear_btn)
        controls.addWidget(self._bind_btn)
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
        item = self._device_list.currentItem()
        if item is not None and item.data(Qt.UserRole)["id"] == str(ev.device_id):
            self._device_render.update_event(ev)

    @Slot()
    def _refresh(self) -> None:
        selected_item = self._device_list.currentItem()
        selected_id = (
            selected_item.data(Qt.UserRole)["id"]
            if selected_item is not None
            else None
        )
        try:
            devices = self._manager.list_devices()
        except Exception as e:  # pragma: no cover — backend failure
            log.exception("device list failed")
            self._status_label.setText(f"error: {e}")
            return
        self._device_list.clear()
        selected_row: int | None = None
        for d in devices:
            label = f"{d['name']}  ({d['id']})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, d)
            self._device_list.addItem(item)
            if d["id"] == selected_id:
                selected_row = self._device_list.count() - 1
        if selected_row is not None:
            self._device_list.setCurrentRow(selected_row)
        self._status_label.setText(f"{len(devices)} device(s)")

    @Slot(object, object)
    def _on_device_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Show a selected HID device's descriptor, or a helpful fallback."""
        if current is None:
            self._device_render.set_descriptor(None)
            return
        device = current.data(Qt.UserRole)
        # MIDI discovery currently exposes no descriptor metadata; HID records
        # carry ``layout`` only when a matching descriptor was found.
        self._device_render.set_layout(device.get("layout") if device.get("descriptor") else None)

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

    @Slot()
    def _on_bind_clicked(self) -> None:
        self._event_view.bind_selected_event()

    @Slot()
    def _on_event_selection_changed(self, *_args: object) -> None:  # type: ignore[no-untyped-def]
        sel = self._event_view.selectionModel().selectedRows()
        self._bind_btn.setEnabled(bool(sel))

    @Slot(str)
    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self._device_list.count()):
            item = self._device_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())


# Re-export Qt so callers don't have to import it.
from PySide6.QtCore import Qt  # noqa: E402

__all__ = ["DevicesTab"]
