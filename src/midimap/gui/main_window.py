"""Main window: tabs, menubar, statusbar, system tray.

The M4 main window is intentionally thin:

- It owns the App runtime (DeviceManager + EventBus + MappingEngine +
  ActionExecutor) and wires the EventBus to the GUI via the
  ``EventBusQtBridge``.
- It hosts 4 tabs: Devices, Profile Editor, Event Log, Settings.
- The system tray is added but does nothing yet (M5 will add a
  "hide on close" option).

A profile can be loaded via ``load_profile(path)``; the Profile Editor
tab updates accordingly. Without a profile, the editor shows an empty
state.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
)

from ..app import App
from ..devices.manager import DeviceManager
from ..profile.schema import Profile
from ..profile.store import ProfileLoadError, load_profile, save_profile
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
            # Subscribe the bridge to the bus.
            app.bus.subscribe(self._bridge.push, name="qt-bridge")
            # Also subscribe the engine if the App didn't already.
            # (App.__init__ already wires this; we just need the
            # bus to know about the bridge.)
        else:
            # No App — create a minimal bus so the bridge has something
            # to subscribe to (useful for headless tests that poke
            # events via bus.publish).
            from ..event_bus import EventBus

            self._bus = EventBus()
            self._manager.subscribe(self._bus.publish)
            self._bus.subscribe(self._bridge.push, name="qt-bridge")
            self._app: App | None = None
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
        self.setStatusBar(QStatusBar(self))
        self.statusBar().addPermanentWidget(self._status_label)

        # ---- System tray (M5 will wire hide-to-tray; for now it's a stub) ----
        self._tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(self.windowIcon(), self)
            self._tray.setToolTip("midimap")
            self._tray.show()

        # ---- Profile state ----
        self._profile_path: Path | None = None

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
        quit_act = QAction("&Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
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
        try:
            profile = load_profile(path)
        except ProfileLoadError as e:
            QMessageBox.warning(self, "Profile error", str(e))
            return
        self._set_profile(profile, Path(path))
        self._status_label.setText(f"loaded {Path(path).name}")

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
        self._status_label.setText(f"saved {p.name}")

    def _set_profile(self, profile: Profile, path: Path | None) -> None:
        self._profile_path = path
        self._profile_tab.set_profile(profile)
        self._settings_tab._profile = profile
        self._status_label.setText(
            f"profile: {profile.name} ({len(profile.layers)} layer(s))"
        )

    # ---- misc ----

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About midimap",
            "<b>midimap</b><br>"
            "Cross-platform MIDI/HID controller mapper.<br><br>"
            "M1-M3: headless pipeline (MIDI input, mapping, keyboard, scripts, "
            "builtins, media keys, template substitution).<br>"
            "M4: GUI prototype (this build).<br>"
            "M5: profile import/export, polish, packaging.<br>"
            "M6: HID + plugins.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._runtime is not None:
            self._runtime.stop()
        if self._tray is not None:
            self._tray.hide()
        super().closeEvent(event)


__all__ = ["MainWindow"]


# Qt needs this import at the bottom because some attributes are looked
# up lazily. (Keeps ruff happy.)
_ = Qt
