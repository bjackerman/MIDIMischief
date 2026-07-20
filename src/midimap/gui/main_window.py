"""Main window: tabs, menubar, statusbar, system tray, profile hot-reload.

M5 adds:

- A :class:`ProfileWatcher` that reloads the profile when the file
  changes on disk. The status bar shows the last reload outcome
  (timestamp + error if any).
- A "Reload" toolbar action on the profile tab (and a corresponding
  menu item) so the user can force a reload.
- An "Edit binding" handler that re-opens the
  :class:`BindControlDialog` pre-filled with the clicked mapping.
- A "Save" action that writes the in-memory profile back to the
  file.
- "Hide to tray" on close: if the system tray is available, closing
  the window hides it instead of quitting. The tray menu has a
  "Show" and a "Quit" action.

The M5 main window is the integration point for everything M1-M4
built. The runtime, the watcher, the editor, and the dialogs all
cooperate through signals + the in-memory :class:`Profile` object.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
)

from ..app import App
from ..devices.manager import DeviceManager
from ..profile.schema import Profile
from ..profile.store import ProfileLoadError, load_profile, save_profile
from ..profile.watcher import ProfileWatcher, ReloadResult
from .qt_bridge import EventBusQtBridge
from .tabs.devices import DevicesTab
from .tabs.event_log import EventLogTab
from .tabs.profile_editor import ProfileEditorTab
from .tabs.settings import SettingsTab

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """The midimap main window."""

    def __init__(
        self,
        *,
        app: App | None = None,
        manager: DeviceManager | None = None,
        parent=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("midimap")
        self.resize(1280, 800)

        # The runtime. If the caller didn't pass one, build a bare-bones
        # one with no profile (the editor will show an empty state).
        self._runtime: App | None = app
        self._manager: DeviceManager = manager or (app.devices if app else DeviceManager())

        # The Qt bridge: receives events from the EventBus (any thread)
        # and emits a Qt signal that widgets connect to.
        self._bridge = EventBusQtBridge(self)
        if app is not None:
            app.bus.subscribe(self._bridge.push, name="qt-bridge")
        else:
            from ..event_bus import EventBus

            self._bus = EventBus()
            self._manager.subscribe(self._bus.publish)
            self._bus.subscribe(self._bridge.push, name="qt-bridge")
        self._app = app

        # ---- Tabs ----
        self._tabs = QTabWidget(self)
        self._devices_tab = DevicesTab(self._manager, self._bridge, self)
        self._profile_tab = ProfileEditorTab(profile=app.profile if app else Profile(), parent=self)
        self._event_log_tab = EventLogTab(self)
        self._settings_tab = SettingsTab(profile=app.profile if app else Profile(), parent=self)

        self._tabs.addTab(self._devices_tab, "Devices")
        self._tabs.addTab(self._profile_tab, "Profile")
        self._tabs.addTab(self._event_log_tab, "Event Log")
        self._tabs.addTab(self._settings_tab, "Settings")
        self.setCentralWidget(self._tabs)

        # ---- Menubar ----
        self._build_menubar()

        # ---- Status bar ----
        self._status_label = QLabel("ready", self)
        self._reload_label = QLabel("", self)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().addWidget(self._status_label, 1)
        self.statusBar().addPermanentWidget(self._reload_label)

        # ---- System tray ----
        self._tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(self.windowIcon(), self)
            self._tray.setToolTip("midimap")
            menu = QMenu(self)
            show_act = QAction("Show window", self)
            show_act.triggered.connect(self._show_from_tray)
            menu.addAction(show_act)
            menu.addSeparator()
            reload_act = QAction("Reload profile", self)
            reload_act.triggered.connect(self._on_reload_profile)
            menu.addAction(reload_act)
            menu.addSeparator()
            quit_act = QAction("Quit", self)
            quit_act.triggered.connect(self._quit_app)
            menu.addAction(quit_act)
            self._tray.setContextMenu(menu)
            self._tray.activated.connect(self._on_tray_activated)
            self._tray.show()

        # ---- Profile state ----
        self._profile_path: Path | None = None
        self._watcher: ProfileWatcher | None = None
        self._hide_to_tray = False

        # ---- Wire profile editor signals ----
        self._profile_tab.new_binding_requested.connect(self._on_new_binding)
        self._profile_tab.edit_binding_requested.connect(self._on_edit_binding)
        self._profile_tab.delete_binding_requested.connect(self._on_delete_binding)
        self._profile_tab.reload_profile_requested.connect(self._on_reload_profile)

        # ---- Wire Devices tab "Map this event" path ----
        # Right-click a row in the live monitor, or select a row and
        # click "Map this event…", to open the wizard pre-filled.
        self._devices_tab.event_bound.connect(self._on_bind_from_event)

    # ---- menubar ----

    def _build_menubar(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")
        open_act = QAction("&Open profile…", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._on_open_profile)
        file_menu.addAction(open_act)

        save_act = QAction("&Save profile", self)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self._on_save_profile)
        file_menu.addAction(save_act)

        save_as_act = QAction("Save profile &as…", self)
        save_as_act.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_act.triggered.connect(self._on_save_profile_as)
        file_menu.addAction(save_as_act)

        file_menu.addSeparator()
        reload_act = QAction("&Reload profile", self)
        reload_act.setShortcut(QKeySequence("F5"))
        reload_act.triggered.connect(self._on_reload_profile)
        file_menu.addAction(reload_act)

        file_menu.addSeparator()
        quit_act = QAction("&Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self._quit_app)
        file_menu.addAction(quit_act)

        device_menu = mb.addMenu("&Device")
        rescan_act = QAction("&Rescan", self)
        rescan_act.triggered.connect(self._devices_tab._refresh)
        device_menu.addAction(rescan_act)

        help_menu = mb.addMenu("&Help")
        about_act = QAction("&About midimap", self)
        about_act.triggered.connect(self._on_about)
        help_menu.addAction(about_act)

    # ---- profile I/O ----

    def _on_open_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open profile", "", "midimap profiles (*.json *.yaml *.yml);;All files (*)"
        )
        if not path:
            return
        self.load_profile_file(Path(path))

    def load_profile_file(self, path: Path) -> bool:
        """Load a profile from disk and start the watcher.

        Returns True on success, False on error (the user is shown a
        dialog with the error).
        """
        try:
            profile = load_profile(path)
        except ProfileLoadError as e:
            QMessageBox.warning(self, "Profile error", str(e))
            return False
        self._apply_loaded_profile(profile, path)
        return True

    def _apply_loaded_profile(self, profile: Profile, path: Path | None) -> None:
        if self._app is not None:
            # Swap the live profile in both the App (for save_profile)
            # and the engine (so it re-reads its mappings on the next
            # event). Use the same object so future mutations are
            # visible everywhere.
            self._app.profile = profile
            self._app.engine.profile = profile
        self._profile_path = path
        self._profile_tab.set_profile(profile)
        self._settings_tab._profile = profile
        self._status_label.setText(
            f"profile: {profile.name} ({len(profile.layers)} layer(s))"
        )
        if path is not None:
            self._start_watcher(path)

    def _start_watcher(self, path: Path) -> None:
        if self._watcher is not None:
            self._watcher.deleteLater()
            self._watcher = None
        self._watcher = ProfileWatcher(path, parent=self)
        self._watcher.profile_reloaded.connect(self._on_watcher_reload)
        self._update_reload_label("loaded", success=True)

    def _on_watcher_reload(self, result: ReloadResult) -> None:
        if result.error is not None:
            self._update_reload_label(f"reload error: {result.error}", success=False)
            return
        if result.changed and result.profile is not None:
            self._apply_loaded_profile(result.profile, result.path)
            self._update_reload_label(
                f"reloaded {Path(result.path).name} @ {time.strftime('%H:%M:%S')}", success=True
            )
        else:
            self._update_reload_label(
                f"no change @ {time.strftime('%H:%M:%S')}", success=True
            )

    def _update_reload_label(self, text: str, *, success: bool) -> None:
        self._reload_label.setText(text)
        # Subtle visual cue: errors in red, success in default.
        self._reload_label.setStyleSheet("" if success else "color: #c0392b;")

    def _on_reload_profile(self) -> None:
        if self._watcher is None:
            self._status_label.setText("no profile to reload")
            return
        self._watcher.force_reload()

    def _on_save_profile(self) -> None:
        if self._profile_path is None:
            self._on_save_profile_as()
            return
        if self._app is None:
            QMessageBox.information(self, "No profile", "No profile is loaded.")
            return
        try:
            save_profile(self._app.profile, self._profile_path)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        self._status_label.setText(f"saved {self._profile_path.name}")

    def _on_save_profile_as(self) -> None:
        if self._app is None:
            QMessageBox.information(self, "No profile", "No profile is loaded.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save profile as", "profile.json", "JSON (*.json);;YAML (*.yaml *.yml)"
        )
        if not path:
            return
        p = Path(path)
        try:
            save_profile(self._app.profile, p)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        self._profile_path = p
        self._start_watcher(p)
        self._status_label.setText(f"saved {p.name}")

    # ---- binding wizard glue ----

    def _on_new_binding(self) -> None:
        from .dialogs.bind_control import BindControlDialog

        dlg = BindControlDialog(parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            mapping = dlg.built_mapping()
            if mapping is not None:
                self._profile_tab.add_mapping(
                    mapping, layer_idx=self._profile_tab.selected_layer_idx()
                )
                self._status_label.setText(f"added mapping {mapping.id}")

    def _on_bind_from_event(self, event) -> None:  # type: ignore[no-untyped-def]
        """Open the binding wizard pre-filled with a captured event
        from the Devices tab live monitor.
        """
        from .dialogs.bind_control import BindControlDialog

        dlg = BindControlDialog(initial_event=event, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            mapping = dlg.built_mapping()
            if mapping is not None:
                self._profile_tab.add_mapping(
                    mapping, layer_idx=self._profile_tab.selected_layer_idx()
                )
                # Switch to the Profile tab so the user sees the new
                # mapping land in the list.
                self._tabs.setCurrentWidget(self._profile_tab)
                self._status_label.setText(
                    f"added mapping {mapping.id} from {event.control_id}"
                )

    def _on_edit_binding(self, mapping_id: str) -> None:
        profile = self._profile_tab.profile()
        existing = next(
            (
                m
                for layer in profile.layers.values()
                for m in layer.mappings
                if m.id == mapping_id
            ),
            None,
        )
        if existing is None:
            return
        from .dialogs.bind_control import BindControlDialog

        dlg = BindControlDialog(parent=self)
        dlg.set_mapping(existing)
        if dlg.exec() == dlg.DialogCode.Accepted:
            new_mapping = dlg.built_mapping()
            if new_mapping is not None:
                self._profile_tab.replace_mapping(new_mapping)
                self._status_label.setText(f"updated mapping {new_mapping.id}")

    def _on_delete_binding(self, mapping_id: str) -> None:
        self._profile_tab.remove_mapping(mapping_id)
        self._status_label.setText(f"removed mapping {mapping_id}")

    # ---- tray / close ----

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_app(self) -> None:
        self._hide_to_tray = False  # disable hide-on-close
        self.close()

    # ---- misc ----

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About midimap",
            "<b>midimap</b><br>"
            "Cross-platform MIDI/HID controller mapper.<br><br>"
            "M1-M3: headless pipeline (MIDI input, mapping, keyboard, scripts, "
            "builtins, media keys, template substitution).<br>"
            "M4: GUI prototype (Qt main window, 4 tabs, binding wizard, learn mode).<br>"
            "M5: profile hot-reload, diff/validate/export CLI, polish (this build).<br>"
            "M6: HID (raw reports) + plugin registry.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._hide_to_tray and self._tray is not None and self._tray.isVisible():
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "midimap",
                "Still running here — right-click the tray icon to quit.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return
        if self._runtime is not None:
            self._runtime.stop()
        if self._tray is not None:
            self._tray.hide()
        super().closeEvent(event)


__all__ = ["MainWindow"]


_ = Qt
