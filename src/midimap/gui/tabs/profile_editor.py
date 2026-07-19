"""Profile Editor tab — view + edit the loaded profile's bindings.

M5 adds:

- Double-click a row to edit the binding (re-opens the
  :class:`BindControlDialog` pre-filled).
- A toolbar with New, Delete, and Reload actions.
- Layer selector (M5 minimal: a combo to switch which layer is
  shown in the binding list).

A future milestone can add: per-mapping search, per-layer drag-reorder,
"duplicate" action, and the full device-render visualisation.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ...gui.widgets.binding_list import BindingListView
from ...profile.schema import Layer, Mapping, Profile

log = logging.getLogger(__name__)


class ProfileEditorTab(QWidget):
    """Profile editor — list of bindings + 'New binding' / 'Delete' / 'Reload' buttons."""

    new_binding_requested = Signal()
    edit_binding_requested = Signal(str)  # mapping id
    delete_binding_requested = Signal(str)  # mapping id
    reload_profile_requested = Signal()
    profile_reloaded = Signal(object)  # Profile

    def __init__(self, profile: Profile, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._profile = profile
        self._name_label = QLabel(self)
        self._layer_combo = QComboBox(self)
        self._binding_list = BindingListView(profile, self)
        self._binding_list.new_binding_requested.connect(self.new_binding_requested.emit)
        self._binding_list.doubleClicked.connect(self._on_double_clicked)

        self._new_btn = QPushButton("New binding…", self)
        self._delete_btn = QPushButton("Delete", self)
        self._delete_btn.setEnabled(False)
        self._reload_btn = QPushButton("Reload", self)
        self._new_btn.clicked.connect(self.new_binding_requested.emit)
        self._delete_btn.clicked.connect(self._on_delete)
        self._reload_btn.clicked.connect(self.reload_profile_requested.emit)

        self._layer_combo.currentIndexChanged.connect(self._on_layer_changed)

        toolbar = QToolBar(self)
        toolbar.setMovable(False)
        toolbar.addWidget(self._new_btn)
        toolbar.addWidget(self._delete_btn)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Layer:"))
        toolbar.addWidget(self._layer_combo)
        toolbar.addSeparator()
        toolbar.addWidget(self._reload_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(self._name_label, 1)
        layout.addLayout(header)
        layout.addWidget(toolbar)
        layout.addWidget(self._binding_list, 1)

        self._refresh_layer_combo()
        self._refresh_name_label()
        self._binding_list._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    # ---- public API ----

    def profile(self) -> Profile:
        return self._profile

    def set_profile(self, profile: Profile) -> None:
        self._profile = profile
        self._binding_list.set_profile(profile)
        self._refresh_layer_combo()
        self._refresh_name_label()
        self.profile_reloaded.emit(profile)

    # ---- slots ----

    def _on_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        mid = index.siblingAtColumn(0).data(Qt.ItemDataRole.DisplayRole)
        if mid:
            self.edit_binding_requested.emit(str(mid))

    def _on_selection_changed(self, *_args: object) -> None:  # type: ignore[no-untyped-def]
        sel = self._binding_list._table.selectionModel()
        self._delete_btn.setEnabled(sel is not None and bool(sel.selectedRows()))

    def _on_delete(self) -> None:
        sel = self._binding_list._table.selectionModel()
        if sel is None:
            return
        rows = sel.selectedRows()
        if not rows:
            return
        mapping_id = rows[0].siblingAtColumn(0).data(Qt.ItemDataRole.DisplayRole)
        if not mapping_id:
            return
        confirm = QMessageBox.question(
            self,
            "Delete binding?",
            f"Delete mapping {mapping_id!r}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.delete_binding_requested.emit(str(mapping_id))

    def _on_layer_changed(self, idx: int) -> None:
        # In M5 the layer switch is a "view only" operation in the
        # binding list. Full layer management (add/remove/rename)
        # lands in a future milestone.
        if idx < 0:
            return
        layer_idx = list(self._profile.layers.keys())[idx]
        self._binding_list._model.set_layer(layer_idx)
        self._binding_list._table.resizeColumnsToContents()

    def _refresh_layer_combo(self) -> None:
        self._layer_combo.blockSignals(True)
        self._layer_combo.clear()
        for idx, layer in sorted(self._profile.layers.items()):
            label = f"[{idx}] {layer.name}"
            if idx == self._profile.default_layer:
                label += " (default)"
            self._layer_combo.addItem(label, idx)
        self._layer_combo.blockSignals(False)

    def _refresh_name_label(self) -> None:
        n = sum(len(layer.mappings) for layer in self._profile.layers.values())
        layer_count = len(self._profile.layers)
        self._name_label.setText(
            f"Profile: <b>{self._profile.name}</b>  -  {n} mapping(s) across {layer_count} layer(s)"
        )

    # ---- convenience mutators (used by the wizard) ----

    def add_mapping(self, mapping: Mapping, layer_idx: int = 0) -> None:
        layer = self._profile.layers.get(layer_idx)
        if layer is None:
            layer = Layer(name=f"Layer {layer_idx}")
            self._profile.layers[layer_idx] = layer
        layer.mappings.append(mapping)
        self.set_profile(self._profile)
        self._sync_to_runtime()

    def replace_mapping(self, mapping: Mapping) -> None:
        for layer in self._profile.layers.values():
            for i, m in enumerate(layer.mappings):
                if m.id == mapping.id:
                    layer.mappings[i] = mapping
                    self.set_profile(self._profile)
                    self._sync_to_runtime()
                    return
        # Not found — treat as add
        self.add_mapping(mapping)

    def remove_mapping(self, mapping_id: str) -> None:
        for layer in self._profile.layers.values():
            layer.mappings = [m for m in layer.mappings if m.id != mapping_id]
        self.set_profile(self._profile)
        self._sync_to_runtime()

    def _sync_to_runtime(self) -> None:
        """If a parent MainWindow installed a runtime, push the new
        profile into the MappingEngine so save_profile() picks up
        the latest state."""
        win = self.window()
        runtime = getattr(win, "_app", None)
        if runtime is not None and getattr(runtime, "engine", None) is not None:
            runtime.engine.profile = self._profile


__all__ = ["ProfileEditorTab"]
