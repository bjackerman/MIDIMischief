"""Event Log tab — application-level log lines (actions, script runs, errors)."""

from __future__ import annotations

import contextlib
import logging
from collections import deque
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QHeaderView, QLineEdit, QTableView, QVBoxLayout, QWidget

DEFAULT_MAX_ROWS = 5000


class EventLogModel(QAbstractTableModel):
    """Plain text log lines in a small table.

    Columns: ``Time``, ``Level``, ``Logger``, ``Message``.
    """

    HEADERS = ("Time", "Level", "Logger", "Message")

    def __init__(self, max_rows: int = DEFAULT_MAX_ROWS) -> None:
        super().__init__()
        self._rows: deque[tuple[str, str, str, str]] = deque(maxlen=max_rows)

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
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self._rows[index.row()][index.column()]

    def append(self, level: str, logger_name: str, message: str) -> None:
        import time

        ts = time.strftime("%H:%M:%S")
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._rows.appendleft((ts, level, logger_name, message))
        self.endInsertRows()


class QtLogHandler(logging.Handler):
    """A stdlib logging.Handler that forwards records to the EventLogModel."""

    def __init__(self, model: EventLogModel) -> None:
        super().__init__()
        self._model = model

    def emit(self, record: logging.LogRecord) -> None:
        with contextlib.suppress(Exception):  # pragma: no cover
            self._model.append(record.levelname, record.name, record.getMessage())


class EventLogTab(QWidget):
    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._model = EventLogModel()
        self._view = QTableView(self)
        self._view.setModel(self._model)
        self._view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._view.setAlternatingRowColors(True)
        self._view.verticalHeader().setVisible(False)
        hh = self._view.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("Filter by logger or message…")
        self._filter.textChanged.connect(self._apply_filter)

        layout = QVBoxLayout(self)
        layout.addWidget(self._filter)
        layout.addWidget(self._view, 1)

        # Attach the handler
        self._handler = QtLogHandler(self._model)
        self._handler.setLevel(logging.INFO)
        root = logging.getLogger()
        root.addHandler(self._handler)

    def _apply_filter(self, text: str) -> None:
        # Simple substring filter: hide rows that don't match.
        needle = text.strip().lower()
        for i in range(self._model.rowCount()):
            row = [self._model._rows[i][c] for c in range(self._model.columnCount())]
            self._view.setRowHidden(i, bool(needle) and not any(needle in cell.lower() for cell in row))


__all__ = ["EventLogModel", "EventLogTab", "QtLogHandler"]
