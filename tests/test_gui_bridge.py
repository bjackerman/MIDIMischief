"""Tests for the Qt cross-thread bridge and the QApplication single-instance lock."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from midimap.events import EventType, NormalizedEvent, Value
from midimap.gui.app import SingleInstance, make_application
from midimap.gui.qt_bridge import EventBusQtBridge


def _ev() -> NormalizedEvent:
    return NormalizedEvent(
        device_id="midi:t",
        control_id="note:60",
        event_type=EventType.PRESS,
        value=Value(100),
    )


def test_qapp_constructs(qapp):  # type: ignore[no-untyped-def]
    a = make_application([])
    assert a is not None
    assert a.applicationName() == "midimap"


def test_single_instance_acquired(qapp):  # type: ignore[no-untyped-def]
    inst = SingleInstance.try_acquire()
    assert inst is not None
    assert inst.name.startswith("midimap-single-instance-")


def test_bridge_emits_signal_on_emit(qapp, qtbot=None):  # type: ignore[no-untyped-def]
    bridge = EventBusQtBridge()
    received: list[NormalizedEvent] = []
    bridge.event_received.connect(lambda ev: received.append(ev))
    bridge.push(_ev())
    qapp.processEvents()
    assert len(received) == 1
    assert received[0].control_id == "note:60"


def test_bridge_signal_carries_event_object(qapp):  # type: ignore[no-untyped-def]
    bridge = EventBusQtBridge()
    seen: list[NormalizedEvent] = []
    bridge.event_received.connect(seen.append)
    ev = _ev()
    bridge.push(ev)
    qapp.processEvents()
    assert seen == [ev]
