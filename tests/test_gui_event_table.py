"""Tests for the EventTableModel and EventTableView.

These tests do not need a running app; they just exercise the model
and view in isolation under the offscreen Qt platform.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from midimap.events import EventType, NormalizedEvent, Value
from midimap.gui.widgets.event_table import EventTableModel, EventTableView


def _ev(control: str = "note:60", value: int = 100, et: EventType = EventType.PRESS) -> NormalizedEvent:
    return NormalizedEvent(
        device_id="midi:test",
        control_id=control,
        event_type=et,
        value=Value(value),
        velocity=90,
        channel=1,
        timestamp_ms=42,
    )


def test_model_starts_empty(qapp):  # type: ignore[no-untyped-def]
    m = EventTableModel()
    assert m.rowCount() == 0
    assert m.columnCount() == 7


def test_model_appends_prepend(qapp):  # type: ignore[no-untyped-def]
    m = EventTableModel()
    m.append_event(_ev("note:60", 100))
    m.append_event(_ev("note:62", 80))
    assert m.rowCount() == 2
    # Newest first
    assert m.data(m.index(0, 2)) == "note:62"
    assert m.data(m.index(1, 2)) == "note:60"


def test_model_caps_at_max_rows(qapp):  # type: ignore[no-untyped-def]
    m = EventTableModel(max_rows=3)
    for i in range(5):
        m.append_event(_ev(f"note:{60 + i}"))
    assert m.rowCount() == 3
    # Newest is note:64, oldest is note:62
    assert m.data(m.index(0, 2)) == "note:64"
    assert m.data(m.index(2, 2)) == "note:62"


def test_model_clear(qapp):  # type: ignore[no-untyped-def]
    m = EventTableModel()
    m.append_event(_ev("note:60"))
    assert m.rowCount() == 1
    m.clear()
    assert m.rowCount() == 0


def test_model_headers(qapp):  # type: ignore[no-untyped-def]
    from PySide6.QtCore import Qt

    m = EventTableModel()
    for c, h in enumerate(EventTableModel.HEADERS):
        assert m.headerData(c, Qt.Orientation.Horizontal) == h


def test_model_display_columns(qapp):  # type: ignore[no-untyped-def]
    m = EventTableModel()
    m.append_event(_ev("note:60", 100))
    assert m.data(m.index(0, 0)) == "42"   # ts
    assert m.data(m.index(0, 1)) == "midi:test"
    assert m.data(m.index(0, 2)) == "note:60"
    assert m.data(m.index(0, 3)) == "press"
    assert m.data(m.index(0, 4)) == "100"
    assert m.data(m.index(0, 5)) == "1"  # channel
    assert m.data(m.index(0, 6)) == "90"  # velocity


def test_view_attaches_to_model(qapp):  # type: ignore[no-untyped-def]
    m = EventTableModel()
    v = EventTableView(m)
    v.show()
    qapp.processEvents()
    assert v.model() is m
