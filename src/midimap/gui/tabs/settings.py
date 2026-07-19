"""Settings tab — global toggles, device enable/disable, plugin list.

M4 ships a placeholder with the global toggles; the plugin list
arrives in M6.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ...profile.schema import Profile


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
        self._auto_start = QCheckBox("Start with the operating system (M5)", self)
        self._auto_start.setEnabled(False)
        self._start_minimised = QCheckBox("Start minimised to tray (M5)", self)
        self._start_minimised.setEnabled(False)

        global_group = QGroupBox("Global", self)
        global_layout = QFormLayout(global_group)
        global_layout.addRow(self._dry_run)
        global_layout.addRow(self._disable_scripts)
        global_layout.addRow(self._confirm_risky)
        global_layout.addRow(self._auto_start)
        global_layout.addRow(self._start_minimised)

        # ---- Device list (placeholder) ----
        device_group = QGroupBox("Connected devices (M5)", self)
        device_layout = QVBoxLayout(device_group)
        device_layout.addWidget(QLabel("Per-device enable/disable and nicknames land in M5."))

        # ---- Plugins placeholder ----
        plugin_group = QGroupBox("Plugins (M6)", self)
        plugin_layout = QVBoxLayout(plugin_group)
        plugin_layout.addWidget(QLabel("Custom action plugins (entry-points) will appear here in M6."))

        layout = QVBoxLayout(self)
        layout.addWidget(global_group)
        layout.addWidget(device_group)
        layout.addWidget(plugin_group)
        layout.addStretch(1)

    def is_dry_run(self) -> bool:
        return self._dry_run.isChecked()

    def is_disable_scripts(self) -> bool:
        return self._disable_scripts.isChecked()

    def is_confirm_risky(self) -> bool:
        return self._confirm_risky.isChecked()


__all__ = ["SettingsTab"]
