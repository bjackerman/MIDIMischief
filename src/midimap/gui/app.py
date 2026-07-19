"""QApplication setup + single-instance lock.

The single-instance lock uses ``QLocalServer`` / ``QLocalSocket``:
the first instance creates a named server; subsequent instances fail
to bind and instead send their argv to the running instance (which
raises the window from the tray). For M4 we only need the lock
itself; the "raise existing window" half is M5 polish.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid

from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

_LOCK_NAME_PREFIX = "midimap-single-instance-"


def _lock_name() -> str:
    """Per-user lock name so different OS users don't collide."""
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "default"
    return f"{_LOCK_NAME_PREFIX}{user}"


class SingleInstance:
    """Acquire (or detect) a process-wide lock.

    Usage::

        inst = SingleInstance.try_acquire()
        if inst is None:
            # another instance owns the lock; we should either exit or
            # send our argv to the owner and exit.
            ...
        else:
            # we own the lock; keep the instance alive for the
            # lifetime of the process.
            ...
    """

    def __init__(self, server: QLocalServer) -> None:
        self._server = server

    @classmethod
    def try_acquire(cls) -> SingleInstance | None:
        name = _lock_name()
        # First probe: try to connect. If it succeeds, another
        # instance owns the lock.
        sock = QLocalSocket()
        sock.connectToServer(name)
        if sock.waitForConnected(200):
            log.info("another midimap instance already running")
            sock.disconnectFromServer()
            return None
        # Stale socket file (previous crash) — remove and retry.
        QLocalServer.removeServer(name)
        server = QLocalServer()
        if not server.listen(name):
            log.warning("could not listen on %s: %s", name, server.errorString())
            return None
        return cls(server)

    @property
    def name(self) -> str:
        return _lock_name()


def is_high_dpi() -> bool:
    """Best-effort detection. PySide6 enables high-DPI by default in Qt 6."""
    return True


def make_application(argv: list[str] | None = None) -> QApplication:  # type: ignore[name-defined, no-untyped-def]  # noqa: F821
    """Construct a QApplication with sensible defaults."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    if argv is None:
        argv = sys.argv
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("midimap")
    app.setApplicationDisplayName("midimap")
    app.setOrganizationName("midimap")
    # Use a per-process session id for state file scoping (M5+).
    app.setApplicationVersion("0.1.0")
    # A unique desktop file name so multiple dev sessions don't collide
    # in the OS task switcher.
    app.setDesktopFileName(f"midimap-{uuid.uuid4().hex[:8]}")
    return app
