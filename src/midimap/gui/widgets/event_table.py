"""Model/view widget for the live NormalizedEvent stream.

The table is intentionally simple: one row per event, columns for the
common fields (time, device, control, event_type, value, channel,
velocity). New events prepend to the top and we cap the row count so
a long-running session doesn't OOM the GUI.

The model is fed by a single ``append_event`` call from the Qt thread;
callers from other threads must marshal through a signal (see
``qt_bridge.EventBusQtBridge``).
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QHeaderView, QMenu, QTableView

from ...events import EventType, NormalizedEvent

log = logging.getLogger(__name__)

DEFAULT_MAX_ROWS = 5000


class EventTableModel(QAbstractTableModel):
    """A table model backed by a bounded deque of NormalizedEvents.

    Newest events appear at the top (row 0). The internal deque is
    capped at ``max_rows``; oldest events are dropped on overflow.
    """

    HEADERS = ("Time", "Device", "Control", "Event", "Value", "Ch", "Vel")

    def __init__(self, max_rows: int = DEFAULT_MAX_ROWS) -> None:
        super().__init__()
        self._rows: deque[NormalizedEvent] = deque(maxlen=max_rows)

    # ---- Qt model interface ----

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        ev = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(ev, col)
        if role == Qt.ItemDataRole.ForegroundRole and col == 3:
            return self._event_color(ev.event_type)
        return None

    @staticmethod
    def _display(ev: NormalizedEvent, col: int) -> str:
        if col == 0:
            return f"{ev.timestamp_ms}"
        if col == 1:
            return ev.device_id
        if col == 2:
            return ev.control_id
        if col == 3:
            return ev.event_type.value
        if col == 4:
            return str(int(ev.value))
        if col == 5:
            return "" if ev.channel is None else str(ev.channel)
        if col == 6:
            return "" if ev.velocity is None else str(ev.velocity)
        return ""

    @staticmethod
    def _event_color(et: EventType) -> QColor:
        if et == EventType.PRESS:
            return QColor(80, 170, 80)    # green
        if et == EventType.RELEASE:
            return QColor(170, 170, 170)  # grey
        if et == EventType.CHANGE:
            return QColor(80, 140, 200)   # blue
        if et == EventType.TAP:
            return QColor(200, 170, 80)   # amber
        return QColor(0, 0, 0)

    # ---- public API ----

    def append_event(self, ev: NormalizedEvent) -> None:
        """Append a new event at the top of the table.

        Must be called from the Qt thread. The model emits the right
        beginInsertRows/endInsertRows signals so the view updates.
        """
        # If the deque is at capacity, the oldest item is silently
        # dropped by deque.maxlen; we must inform the view so it can
        # re-bind its persistent indexes.
        was_full = len(self._rows) == self._rows.maxlen
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._rows.appendleft(ev)
        self.endInsertRows()
        if was_full:
            # The bottom row fell off. Notify the view.
            bottom = self.index(self._rows.maxlen - 1, 0)
            self.dataChanged.emit(bottom, bottom)
            # Emit a full row removal for clarity; the view will trim.
            self.beginRemoveRows(QModelIndex(), self._rows.maxlen, self._rows.maxlen)
            self.endRemoveRows()

    def clear(self) -> None:
        if not self._rows:
            return
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()

    def event_at(self, row: int) -> NormalizedEvent | None:
        """Return the :class:`NormalizedEvent` at ``row`` (newest-first)."""
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class EventTableView(QTableView):
    """QTableView wired up with sensible defaults for the live monitor.

    Right-clicking a row opens a context menu with a
    "Bind this control…" action that emits :attr:`event_bound` with
    the captured :class:`NormalizedEvent`. The host (typically the
    main window) opens the binding wizard pre-filled.
    """

    event_bound = Signal(object)  # NormalizedEvent

    def __init__(self, model: EventTableModel | None = None, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setModel(model if model is not None else EventTableModel())
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        # Right-click context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def bind_selected_event(self) -> None:
        """Public API: bind the currently selected row (if any).

        Returns the NormalizedEvent that the wizard should be opened
        for, or None if no row is selected.
        """
        ev = self._selected_event()
        if ev is not None:
            self.event_bound.emit(ev)
        return None  # signal-based; no return value meaningful

    def _on_context_menu(self, pos: QPoint) -> None:  # type: ignore[no-untyped-def]
        idx = self.indexAt(pos)
        if not idx.isValid():
            return
        self.selectRow(idx.row())
        menu = QMenu(self)
        act = QAction("Bind this control…", self)
        act.triggered.connect(self.bind_selected_event)
        menu.addAction(act)
        menu.exec(self.viewport().mapToGlobal(pos))

    def _selected_event(self) -> NormalizedEvent | None:
        rows = self.selectionModel().selectedRows()
        if not rows:
            return None
        m = self.model()
        if not isinstance(m, EventTableModel):
            return None
        row = rows[0].row()
        return m.event_at(row)


__all__ = ["DEFAULT_MAX_ROWS", "EventTableModel", "EventTableView"]
