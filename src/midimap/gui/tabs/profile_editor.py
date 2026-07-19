"""Profile Editor tab — view the loaded profile's bindings.

M4 ships a binding list + a "New binding" button. Editing existing
bindings and the full "Bind this control" wizard land in M5.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...gui.widgets.binding_list import BindingListView
from ...profile.schema import Profile

log = logging.getLogger(__name__)


class ProfileEditorTab(QWidget):
    """Profile editor — list of bindings + 'New binding' button."""

    new_binding_requested = Signal()

    def __init__(self, profile: Profile, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._profile = profile
        self._name_label = QLabel(self)
        self._refresh_name_label()
        self._binding_list = BindingListView(profile, self)
        self._binding_list.new_binding_requested.connect(self.new_binding_requested.emit)

        layout = QVBoxLayout(self)
        layout.addWidget(self._name_label)
        layout.addWidget(self._binding_list, 1)

    def _refresh_name_label(self) -> None:
        n = len(self._profile.all_mappings(0))
        layer_count = len(self._profile.layers)
        self._name_label.setText(
            f"Profile: <b>{self._profile.name}</b>  —  {n} mapping(s)  —  {layer_count} layer(s)"
        )

    def set_profile(self, profile: Profile) -> None:
        self._profile = profile
        self._binding_list.set_profile(profile)
        self._refresh_name_label()


__all__ = ["ProfileEditorTab"]
