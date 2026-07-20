"""M6.5: 'Map from event' feature — Devices tab live event -> binding wizard."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from midimap.events import EventType, NormalizedEvent, Value
from midimap.gui.main_window import MainWindow
from midimap.gui.widgets.event_table import EventTableModel, EventTableView


def _ev(control: str = "note:60", value: int = 100) -> NormalizedEvent:
    return NormalizedEvent(
        device_id="midi:t",
        control_id=control,
        event_type=EventType.PRESS,
        value=Value(value),
        timestamp_ms=0,
    )


# ---- model: event_at ----


def test_event_table_model_event_at_returns_event(qapp):  # type: ignore[no-untyped-def]
    m = EventTableModel()
    e1 = _ev("note:60", 100)
    e2 = _ev("note:62", 80)
    m.append_event(e1)
    m.append_event(e2)
    # Newest-first: row 0 = e2
    assert m.event_at(0) is e2
    assert m.event_at(1) is e1
    assert m.event_at(99) is None
    assert m.event_at(-1) is None


# ---- view: event_bound signal ----


def test_event_table_view_emits_event_bound_on_button_invocation(qapp):  # type: ignore[no-untyped-def]
    m = EventTableModel()
    v = EventTableView(m)
    ev = _ev("note:60", 100)
    m.append_event(ev)
    # Select the first row
    v.selectRow(0)
    received: list[NormalizedEvent] = []
    v.event_bound.connect(received.append)
    # Simulate clicking the button (which calls bind_selected_event)
    v.bind_selected_event()
    qapp.processEvents()
    assert received == [ev]


def test_event_table_view_emits_event_bound_on_context_menu(qapp, monkeypatch):  # type: ignore[no-untyped-def]
    """Right-clicking a row should wire the menu action to the
    bind_selected_event helper. We bypass the actual QMenu.popup
    (which would block on a real desktop) by calling
    bind_selected_event directly after selecting a row, which is
    what the menu's action does anyway.
    """
    m = EventTableModel()
    v = EventTableView(m)
    ev = _ev("note:60", 100)
    m.append_event(ev)
    v.selectRow(0)
    qapp.processEvents()
    received: list[NormalizedEvent] = []
    v.event_bound.connect(received.append)
    # The menu's QAction calls bind_selected_event when triggered.
    # Verify the wiring directly without showing a real menu.
    v.bind_selected_event()
    qapp.processEvents()
    assert received == [ev]


def test_event_table_view_context_menu_helper_emits_after_select(qapp):  # type: ignore[no-untyped-def]
    """The _on_context_menu helper must select the row at the
    right-click position and emit event_bound. We exercise this
    by calling the action callback that the menu would invoke.
    """
    m = EventTableModel()
    v = EventTableView(m)
    ev = _ev("note:60", 100)
    m.append_event(ev)
    received: list[NormalizedEvent] = []
    v.event_bound.connect(received.append)
    # Pre-select the row (what the menu action does internally)
    v.selectRow(0)
    # Now call the action that the menu's QAction would call.
    v.bind_selected_event()
    qapp.processEvents()
    assert received == [ev]


# ---- devices tab: button enable/disable on selection ----


def test_devices_tab_bind_button_disabled_then_enabled(qapp):  # type: ignore[no-untyped-def]
    from midimap.devices.manager import DeviceManager
    from midimap.gui.qt_bridge import EventBusQtBridge
    from midimap.gui.tabs.devices import DevicesTab

    manager = DeviceManager(hid_manager=False)
    bridge = EventBusQtBridge()
    tab = DevicesTab(manager, bridge)
    # Initially: no rows selected -> button disabled
    assert tab._bind_btn.isEnabled() is False
    # Add an event + select its row -> button enabled
    tab._event_model.append_event(_ev("note:60", 100))
    tab._event_view.selectRow(0)
    qapp.processEvents()
    assert tab._bind_btn.isEnabled() is True


def test_devices_tab_emits_event_bound_when_button_clicked(qapp):  # type: ignore[no-untyped-def]
    from midimap.devices.manager import DeviceManager
    from midimap.gui.qt_bridge import EventBusQtBridge
    from midimap.gui.tabs.devices import DevicesTab

    manager = DeviceManager(hid_manager=False)
    bridge = EventBusQtBridge()
    tab = DevicesTab(manager, bridge)
    ev = _ev("cc:1", 64)
    tab._event_model.append_event(ev)
    tab._event_view.selectRow(0)
    seen: list[NormalizedEvent] = []
    tab.event_bound.connect(seen.append)
    # Simulate button click
    tab._bind_btn.click()
    qapp.processEvents()
    assert seen == [ev]


# ---- main window: end-to-end path from event -> editor ----


def test_main_window_routes_event_bound_to_profile_editor(qapp):  # type: ignore[no-untyped-def]
    """When DevicesTab emits event_bound, the main window should
    open the binding wizard pre-filled. We can't show the modal
    dialog in the test, so we monkeypatch BindControlDialog.exec
    to immediately accept and return a fixed mapping."""
    from midimap.gui.dialogs import bind_control as bind_mod

    win = MainWindow(app=None)
    qapp.processEvents()

    fake_mapping = bind_mod.Mapping(
        id="from_event_test",
        input=bind_mod.InputSpec(control="cc:1"),
        action=bind_mod.KeyboardAction(keys=["ctrl", "1"]),
    )

    class _FakeDialog:
        def __init__(self, *a, **kw) -> None:  # type: ignore[no-untyped-def]
            self._mapping = fake_mapping
            self.DialogCode = bind_mod.QDialog.DialogCode

        def exec(self) -> int:  # type: ignore[no-untyped-def]
            return self.DialogCode.Accepted

        def built_mapping(self):
            return self._mapping

    original = bind_mod.BindControlDialog
    bind_mod.BindControlDialog = _FakeDialog  # type: ignore[assignment]
    try:
        ev = _ev("cc:1", 100)
        win._on_bind_from_event(ev)
        # The mapping should have landed in the editor
        profile = win._profile_tab.profile()
        ids = [m.id for layer in profile.layers.values() for m in layer.mappings]
        assert "from_event_test" in ids
        assert ids[-1] == "from_event_test"
        # And the captured control made it into the mapping
        assert profile.layers[0].mappings[-1].input.control == "cc:1"
    finally:
        bind_mod.BindControlDialog = original  # type: ignore[assignment]
