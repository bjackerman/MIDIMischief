"""Cross-thread signal helpers.

The runtime is a multi-threaded beast:

- rtmidi callbacks run on its own thread
- each EventBus subscriber runs on its own thread
- the Qt main loop is single-threaded (the GUI thread)

We need to forward data from any of those threads to the GUI thread
without blocking. Qt's signal/slot system handles the cross-thread
plumbing when the connection type is ``Qt.QueuedConnection`` (the
default for cross-thread signals on ``QObject`` subclasses).

This module provides two small utilities:

- ``EventBusQtBridge`` — a small QObject that turns each incoming
  NormalizedEvent into a Qt signal emission. The EventBus subscriber
  calls ``bridge.push(event)`` from any thread; the signal arrives
  on the GUI thread.
- ``from_worker`` — a decorator that wraps a callable in
  ``QMetaObject.invokeMethod`` on the receiver's thread, so you can
  post a function call into the GUI thread without using a signal.

The decorator is intentionally simple; we use it for the
"re-emit on GUI thread" pattern.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QMetaObject, QObject, Qt, Signal, Slot

from ..events import NormalizedEvent

log = logging.getLogger(__name__)


class EventBusQtBridge(QObject):
    """Adapt an EventBus (any-thread publisher) to a Qt signal.

    Usage::

        bridge = EventBusQtBridge()
        bus.subscribe(bridge.push, name="qt-bridge")
        bridge.event_received.connect(my_widget.on_event)

    The signal fires on the thread the bridge lives on (i.e. the
    receiver's thread, because of Qt.QueuedConnection by default).
    """

    event_received = Signal(object)  # NormalizedEvent

    @Slot(object)
    def push(self, event: NormalizedEvent) -> None:
        self.event_received.emit(event)


def from_worker(receiver: QObject, slot_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: invoke the wrapped callable on the receiver's GUI thread.

    Use this to forward a background-thread call into the Qt main
    thread without going through a signal::

        class MyWidget(QWidget):
            @from_worker(self, "_on_event")
            def _on_event(self, ev):
                self.text_label.setText(str(ev))
    """

    def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            return QMetaObject.invokeMethod(
                receiver,
                slot_name,
                Qt.ConnectionType.QueuedConnection,
            )

        return _wrapper

    return _decorator
