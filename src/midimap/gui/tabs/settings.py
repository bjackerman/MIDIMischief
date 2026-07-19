"""Settings tab — global toggles, auto-start, plugin list.

M6 makes the previously-disabled checkboxes real:
- "Start with the OS" calls :mod:`midimap.autostart`.
- The Plugins section shows the registered plugins from the
  :class:`PluginRegistry`, refreshed when the tab is shown.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import autostart
from ...plugins import get_registry
from ...profile.schema import Profile

log = logging.getLogger(__name__)


class SettingsTab(QWidget):
    def __init__(self, profile: Profile, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._profile = profile

        # ---- Global toggles ----
        self._dry_run = QCheckBox("Dry-run (log actions, do not send keys or run scripts)", self)
        self._dry_run.setChecked(bool(profile.global_settings.get("dry_run", False)))
        self._disable_scripts = QCheckBox("Hard-disable all script actions", self)
        self._disable_scripts.setChecked(profile.disable_scripts)
        self._confirm_risky = QCheckBox("Confirm risky scripts the first time", self)
        self._confirm_risky.setChecked(profile.confirm_risky)
        self._auto_start = QCheckBox("Start with the operating system", self)
        self._auto_start.setChecked(_safe_is_enabled())
        self._auto_start.toggled.connect(self._on_auto_start_toggled)
        self._start_minimised = QCheckBox("Start minimised to tray (M5)", self)
        self._start_minimised.setEnabled(False)

        global_group = QGroupBox("Global", self)
        global_layout = QFormLayout(global_group)
        global_layout.addRow(self._dry_run)
        global_layout.addRow(self._disable_scripts)
        global_layout.addRow(self._confirm_risky)
        global_layout.addRow(self._auto_start)
        global_layout.addRow(self._start_minimised)

        # ---- Plugins ----
        self._plugin_list = QListWidget(self)
        self._plugin_refresh_btn = QPushButton("Refresh plugin list", self)
        self._plugin_refresh_btn.clicked.connect(self._refresh_plugins)
        self._refresh_plugins()

        plugin_group = QGroupBox("Plugins (M6)", self)
        plugin_layout = QVBoxLayout(plugin_group)
        plugin_layout.addWidget(QLabel("Callables registered via the 'midimap.plugins' entry-point group:"))
        plugin_layout.addWidget(self._plugin_list, 1)
        plugin_layout.addWidget(self._plugin_refresh_btn)

        # ---- About ----
        about_group = QGroupBox("About", self)
        about_layout = QVBoxLayout(about_group)
        about_layout.addWidget(QLabel(
            "<b>midimap</b> v0.1.0<br>"
            "Cross-platform MIDI/HID controller mapper.<br>"
            "M1-M6 complete. See README for setup notes."
        ))

        layout = QVBoxLayout(self)
        layout.addWidget(global_group)
        layout.addWidget(plugin_group)
        layout.addWidget(about_group)
        layout.addStretch(1)

    def is_dry_run(self) -> bool:
        return self._dry_run.isChecked()

    def is_disable_scripts(self) -> bool:
        return self._disable_scripts.isChecked()

    def is_confirm_risky(self) -> bool:
        return self._confirm_risky.isChecked()

    # ---- slots ----

    def _on_auto_start_toggled(self, checked: bool) -> None:
        try:
            ok = autostart.enable() if checked else autostart.disable()
        except Exception as e:  # pragma: no cover
            QMessageBox.warning(self, "Auto-start failed", str(e))
            self._auto_start.blockSignals(True)
            self._auto_start.setChecked(not checked)
            self._auto_start.blockSignals(False)
            return
        if not ok:
            QMessageBox.warning(
                self,
                "Auto-start",
                "Could not update auto-start. Check the application log for details.",
            )
            self._auto_start.blockSignals(True)
            self._auto_start.setChecked(not checked)
            self._auto_start.blockSignals(False)

    def _refresh_plugins(self) -> None:
        self._plugin_list.clear()
        registry = get_registry()
        names = registry.names()
        if not names:
            placeholder = QListWidgetItem("(no plugins registered — install a 'midimap.plugins' entry-point)")
            placeholder.setFlags(placeholder.flags() & ~placeholder.flags().__class__.ItemIsEnabled)
            self._plugin_list.addItem(placeholder)
            return
        for name in names:
            spec = registry.get(name)
            if spec is None:
                continue
            params = list(spec.signature.parameters.keys())
            item = QListWidgetItem(f"{name}  ({', '.join(params)})")
            self._plugin_list.addItem(item)


def _safe_is_enabled() -> bool:
    """Wrap autostart.is_enabled in case of platform errors."""
    try:
        return autostart.is_enabled()
    except Exception:
        return False


__all__ = ["SettingsTab"]
