"""Binding list widget — sortable, editable table of :class:`Mapping`.

M5 adds per-layer view switching: the model keeps a ``layer_idx`` and
re-collects on change. The view forwards ``doubleClicked`` to its
parent so the wizard can pre-fill on edit.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...profile.schema import Mapping, Profile

log = logging.getLogger(__name__)


class BindingListModel(QAbstractTableModel):
    """Read-only model over a Profile's mappings for a chosen layer."""

    HEADERS = ("ID", "Input control", "Event", "Action", "Description")

    def __init__(self, profile: Profile, layer_idx: int = 0, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._profile = profile
        self._layer_idx = layer_idx
        self._mappings: list[Mapping] = self._collect(profile, layer_idx)

    @staticmethod
    def _collect(profile: Profile, layer_idx: int) -> list[Mapping]:
        return profile.all_mappings(layer_idx)

    def set_profile(self, profile: Profile) -> None:
        self.beginResetModel()
        self._profile = profile
        self._mappings = self._collect(profile, self._layer_idx)
        self.endResetModel()

    def set_layer(self, layer_idx: int) -> None:
        if layer_idx == self._layer_idx:
            return
        self.beginResetModel()
        self._layer_idx = layer_idx
        self._mappings = self._collect(self._profile, layer_idx)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._mappings)

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
        if not index.isValid() or index.row() >= len(self._mappings):
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        m = self._mappings[index.row()]
        col = index.column()
        if col == 0:
            return m.id
        if col == 1:
            return m.input.control
        if col == 2:
            return m.input.event or "any"
        if col == 3:
            return m.action.type
        if col == 4:
            return m.description or ""
        return ""


class BindingListView(QWidget):
    """A QTableView with a 'New binding' button above it.

    The view's ``doubleClicked`` signal is forwarded so the parent
    can re-open the binding wizard pre-filled.
    """

    new_binding_requested = Signal()
    doubleClicked = Signal(QModelIndex)

    def __init__(self, profile: Profile, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._model = BindingListModel(profile, parent=self)
        self._table = QTableView(self)
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self.doubleClicked.emit)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)

        self._new_btn = QPushButton("New binding…", self)
        self._new_btn.clicked.connect(self.new_binding_requested.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self._new_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        layout.addWidget(self._table)

    def model(self) -> BindingListModel:
        return self._model

    def set_profile(self, profile: Profile) -> None:
        self._model.set_profile(profile)


__all__ = ["BindingListModel", "BindingListView"]
