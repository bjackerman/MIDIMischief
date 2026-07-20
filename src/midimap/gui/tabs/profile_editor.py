"""Profile Editor tab — view + edit the loaded profile's bindings.

M5 adds:

- Double-click a row to edit the binding (re-opens the
  :class:`BindControlDialog` pre-filled).
- A toolbar with New, Delete, and Reload actions.
- Layer management controls for adding, renaming, deleting, selecting,
  and configuring layers.

A future milestone can add: per-mapping search, per-layer drag-reorder,
"duplicate" action, and the full device-render visualisation.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
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
        self._add_layer_btn = QPushButton("Add layer…", self)
        self._rename_layer_btn = QPushButton("Rename layer…", self)
        self._delete_layer_btn = QPushButton("Delete layer", self)
        self._default_layer_btn = QPushButton("Set default", self)
        self._hold_to_activate_check = QCheckBox("Hold to activate", self)
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
        self._add_layer_btn.clicked.connect(self._on_add_layer)
        self._rename_layer_btn.clicked.connect(self._on_rename_layer)
        self._delete_layer_btn.clicked.connect(self._on_delete_layer)
        self._default_layer_btn.clicked.connect(self._on_set_default_layer)
        self._hold_to_activate_check.toggled.connect(self._on_hold_to_activate_changed)

        toolbar = QToolBar(self)
        toolbar.setMovable(False)
        toolbar.addWidget(self._new_btn)
        toolbar.addWidget(self._delete_btn)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Layer:"))
        toolbar.addWidget(self._layer_combo)
        toolbar.addWidget(self._add_layer_btn)
        toolbar.addWidget(self._rename_layer_btn)
        toolbar.addWidget(self._delete_layer_btn)
        toolbar.addWidget(self._default_layer_btn)
        toolbar.addWidget(self._hold_to_activate_check)
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
        self._binding_list._table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

    # ---- public API ----

    def profile(self) -> Profile:
        return self._profile

    def set_profile(self, profile: Profile) -> None:
        self._profile = profile
        self._binding_list.set_profile(profile)
        self._refresh_layer_combo(self.selected_layer_idx())
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
        if idx < 0:
            return
        layer_idx = self._layer_combo.itemData(idx)
        if layer_idx is None:
            return
        self._binding_list._model.set_layer(layer_idx)
        self._binding_list._table.resizeColumnsToContents()
        layer = self._profile.layers[layer_idx]
        self._hold_to_activate_check.blockSignals(True)
        self._hold_to_activate_check.setChecked(layer.hold_to_activate)
        self._hold_to_activate_check.blockSignals(False)
        self._delete_layer_btn.setEnabled(layer_idx != 0)

    def _on_add_layer(self) -> None:
        name, accepted = QInputDialog.getText(self, "Add layer", "Layer name:")
        if accepted:
            self.add_layer(name)

    def _on_rename_layer(self) -> None:
        layer_idx = self.selected_layer_idx()
        if layer_idx is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename layer", "Layer name:", text=self._profile.layers[layer_idx].name
        )
        if accepted:
            self.rename_layer(layer_idx, name)

    def _on_delete_layer(self) -> None:
        layer_idx = self.selected_layer_idx()
        if layer_idx is None or layer_idx == 0:
            return
        if (
            QMessageBox.question(
                self,
                "Delete layer?",
                f"Delete layer {self._profile.layers[layer_idx].name!r} and its mappings?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.delete_layer(layer_idx)

    def _on_set_default_layer(self) -> None:
        layer_idx = self.selected_layer_idx()
        if layer_idx is not None:
            self.set_default_layer(layer_idx)

    def _on_hold_to_activate_changed(self, checked: bool) -> None:
        layer_idx = self.selected_layer_idx()
        if layer_idx is not None:
            self.set_hold_to_activate(layer_idx, checked)

    def _refresh_layer_combo(self, selected_layer: int | None = None) -> None:
        if selected_layer is None:
            selected_layer = self.selected_layer_idx()
        self._layer_combo.blockSignals(True)
        self._layer_combo.clear()
        for idx, layer in sorted(self._profile.layers.items()):
            label = f"[{idx}] {layer.name}"
            if idx == self._profile.default_layer:
                label += " (default)"
            self._layer_combo.addItem(label, idx)
        combo_index = self._layer_combo.findData(selected_layer)
        self._layer_combo.setCurrentIndex(combo_index if combo_index >= 0 else 0)
        self._layer_combo.blockSignals(False)
        self._on_layer_changed(self._layer_combo.currentIndex())

    def _refresh_name_label(self) -> None:
        n = sum(len(layer.mappings) for layer in self._profile.layers.values())
        layer_count = len(self._profile.layers)
        self._name_label.setText(
            f"Profile: <b>{self._profile.name}</b>  -  {n} mapping(s) across {layer_count} layer(s)"
        )

    # ---- convenience mutators (used by the wizard) ----

    def selected_layer_idx(self) -> int | None:
        """Return the layer currently selected in the editor."""
        value = self._layer_combo.currentData()
        return int(value) if value is not None else None

    def add_layer(self, name: str = "") -> int:
        """Add a layer and select it, returning its stable numeric index."""
        layer_idx = max(self._profile.layers, default=-1) + 1
        self._profile.layers[layer_idx] = Layer(name=name.strip() or f"Layer {layer_idx}")
        self._profile_changed(layer_idx)
        return layer_idx

    def rename_layer(self, layer_idx: int, name: str) -> bool:
        layer = self._profile.layers.get(layer_idx)
        if layer is None:
            return False
        layer.name = name.strip() or f"Layer {layer_idx}"
        self._profile_changed(layer_idx)
        return True

    def delete_layer(self, layer_idx: int) -> bool:
        """Delete a non-default-base layer and all mappings it contains."""
        if layer_idx == 0 or layer_idx not in self._profile.layers:
            return False
        del self._profile.layers[layer_idx]
        # A profile may have designated this layer as its default.  Keep
        # the profile valid and leave the editor on an existing layer.
        if self._profile.default_layer == layer_idx:
            self._profile.default_layer = 0
        self._profile_changed(0)
        return True

    def set_default_layer(self, layer_idx: int) -> bool:
        if layer_idx not in self._profile.layers:
            return False
        self._profile.default_layer = layer_idx
        self._profile_changed(layer_idx)
        return True

    def set_hold_to_activate(self, layer_idx: int, enabled: bool) -> bool:
        layer = self._profile.layers.get(layer_idx)
        if layer is None:
            return False
        layer.hold_to_activate = enabled
        self._profile_changed(layer_idx)
        return True

    def _profile_changed(self, selected_layer: int | None = None) -> None:
        self.set_profile(self._profile)
        if selected_layer is not None:
            combo_index = self._layer_combo.findData(selected_layer)
            if combo_index >= 0:
                self._layer_combo.setCurrentIndex(combo_index)
        self._sync_to_runtime()

    def add_mapping(self, mapping: Mapping, layer_idx: int | None = None) -> None:
        if layer_idx is None:
            layer_idx = self.selected_layer_idx()
        if layer_idx is None:
            layer_idx = 0
        layer = self._profile.layers.get(layer_idx)
        if layer is None:
            layer = Layer(name=f"Layer {layer_idx}")
            self._profile.layers[layer_idx] = layer
        layer.mappings.append(mapping)
        self._profile_changed(layer_idx)

    def replace_mapping(self, mapping: Mapping) -> None:
        for layer in self._profile.layers.values():
            for i, m in enumerate(layer.mappings):
                if m.id == mapping.id:
                    layer.mappings[i] = mapping
                    self._profile_changed(self.selected_layer_idx())
                    return
        # Not found — treat as add
        self.add_mapping(mapping)

    def remove_mapping(self, mapping_id: str) -> None:
        for layer in self._profile.layers.values():
            layer.mappings = [m for m in layer.mappings if m.id != mapping_id]
        self._profile_changed(self.selected_layer_idx())

    def _sync_to_runtime(self) -> None:
        """If a parent MainWindow installed a runtime, push the new
        profile into the MappingEngine so save_profile() picks up
        the latest state."""
        win = self.window()
        runtime = getattr(win, "_app", None)
        if runtime is not None and getattr(runtime, "engine", None) is not None:
            runtime.engine.profile = self._profile
            # A removed held layer must not remain active in the live engine.
            runtime.engine._active_layers.intersection_update(self._profile.layers)
            runtime.engine._active_layers.add(0)
            runtime.engine._layer_holders = {
                idx: holders
                for idx, holders in runtime.engine._layer_holders.items()
                if idx in self._profile.layers
            }


__all__ = ["ProfileEditorTab"]
