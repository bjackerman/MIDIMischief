"""Learn-mode dialog.

A small floating, borderless dialog with a countdown timer. When the
user activates Learn Mode, the next ``NormalizedEvent`` arriving on
the Qt bridge is captured and emitted via the ``event_captured``
signal; the parent (typically the profile editor) opens the
"Bind this control" wizard with the captured control pre-filled.

Learn Mode is a Qt-thread concept; we listen on the same
``EventBusQtBridge`` the rest of the GUI uses. When the timer
expires, the dialog self-destructs and emits ``timed_out``.

M4 ships a non-blocking ``QDialog`` (modal to the main window) with
a 8-second default timeout. The full "floating always-on-top
indicator" UX lands in M5.
"""

from __future__ import annotations

import contextlib
import logging

from PySide6.QtCore import QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ...events import NormalizedEvent
from ...gui.qt_bridge import EventBusQtBridge

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 8000


class LearnModeDialog(QDialog):
    """Listen for the next NormalizedEvent and emit it."""

    event_captured = Signal(object)  # NormalizedEvent
    timed_out = Signal()

    def __init__(
        self,
        bridge: EventBusQtBridge,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        parent=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Learn mode")
        self.setModal(True)
        self._bridge = bridge
        self._timeout_ms = timeout_ms

        self._label = QLabel("Press a control on your device…", self)
        self._progress = QProgressBar(self)
        self._progress.setRange(0, timeout_ms)
        self._progress.setValue(timeout_ms)
        self._cancel_btn = QPushButton("Cancel", self)

        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._progress)
        layout.addWidget(self._cancel_btn)

        self._timer = QTimer(self)
        self._timer.setInterval(50)  # 20 fps tick
        self._timer.timeout.connect(self._tick)
        self._cancel_btn.clicked.connect(self._cancel)

        # Subscribe to bridge
        self._bridge.event_received.connect(self._on_event)

    def start(self) -> None:
        self._timer.start()
        self.show()

    @Slot()
    def _tick(self) -> None:
        v = self._progress.value() - 50
        if v <= 0:
            self._time_out()
            return
        self._progress.setValue(v)

    @Slot(object)
    def _on_event(self, ev: NormalizedEvent) -> None:
        # First event wins.
        log.info("learn mode captured: %s", ev)
        self._teardown()
        self.event_captured.emit(ev)
        self.accept()

    def _time_out(self) -> None:
        log.info("learn mode timed out")
        self._teardown()
        self.timed_out.emit()
        self.reject()

    @Slot()
    def _cancel(self) -> None:
        self._time_out()

    def _teardown(self) -> None:
        with contextlib.suppress(RuntimeError, TypeError):  # pragma: no cover
            self._bridge.event_received.disconnect(self._on_event)
        self._timer.stop()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def, override]
        self._teardown()
        super().closeEvent(event)


__all__ = ["DEFAULT_TIMEOUT_MS", "LearnModeDialog"]
