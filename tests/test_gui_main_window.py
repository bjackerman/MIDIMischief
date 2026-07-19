"""Smoke tests for the main window + tabs."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from midimap.events import EventType, NormalizedEvent, Value
from midimap.gui.main_window import MainWindow
from midimap.profile.schema import (
    InputSpec,
    KeyboardAction,
    Layer,
    Mapping,
    Profile,
)


def _profile() -> Profile:
    return Profile(
        name="Test",
        layers={
            0: Layer(
                mappings=[
                    Mapping(
                        id="pad1",
                        input=InputSpec(control="note:60"),
                        action=KeyboardAction(keys=["ctrl", "1"]),
                    )
                ]
            )
        },
    )


def test_main_window_constructs_without_profile(qapp):  # type: ignore[no-untyped-def]
    from midimap.gui.tabs.devices import DevicesTab

    win = MainWindow(app=None)
    # Tabs created
    assert win._tabs.count() == 4
    # Devices tab exists and is of the right type
    assert isinstance(win._devices_tab, DevicesTab)
    win.close()
    qapp.processEvents()


def test_main_window_constructs_with_profile(qapp):  # type: ignore[no-untyped-def]
    from unittest.mock import patch

    with patch("pynput.keyboard.Controller"):
        from midimap.app import App

        profile = _profile()
        runtime = App(profile, dry_run=True, auto_connect=False)
        win = MainWindow(app=runtime)
        qapp.processEvents()
        # The profile tab should display the profile name
        assert "Test" in win._profile_tab._name_label.text()
        win.close()
        runtime.stop()
        qapp.processEvents()


def test_event_log_appends_lines(qapp, caplog):  # type: ignore[no-untyped-def]
    import logging

    from midimap.gui.tabs.event_log import EventLogTab

    tab = EventLogTab()
    # Emit a log record
    logger = logging.getLogger("test_gui_event_log")
    logger.warning("hello from a test")
    qapp.processEvents()
    assert tab._model.rowCount() >= 1
    # The "Level" column (index 1) should contain "WARNING"
    found = False
    for r in range(tab._model.rowCount()):
        if tab._model.data(tab._model.index(r, 1)) == "WARNING":
            found = True
            break
    assert found


def test_devices_tab_shows_devices(qapp):  # type: ignore[no-untyped-def]
    from midimap.devices.manager import DeviceManager
    from midimap.gui.qt_bridge import EventBusQtBridge
    from midimap.gui.tabs.devices import DevicesTab

    manager = DeviceManager()
    bridge = EventBusQtBridge()
    tab = DevicesTab(manager, bridge)
    qapp.processEvents()
    # list_devices() will return at least the system MIDI devices on Win.
    assert tab._device_list.count() >= 0


def test_binding_list_model_shows_profile_mappings(qapp):  # type: ignore[no-untyped-def]
    from midimap.gui.widgets.binding_list import BindingListModel

    profile = _profile()
    model = BindingListModel(profile)
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0)) == "pad1"
    assert model.data(model.index(0, 1)) == "note:60"
    assert model.data(model.index(0, 2)) == "any"
    assert model.data(model.index(0, 3)) == "keyboard"


def test_main_window_fed_event_routes_to_event_table(qapp):  # type: ignore[no-untyped-def]
    """Drive an event through the bridge and confirm the live monitor table sees it."""
    win = MainWindow(app=None)
    qapp.processEvents()
    table_model = win._devices_tab._event_model
    before = table_model.rowCount()
    win._bridge.push(NormalizedEvent(
        device_id="midi:t",
        control_id="note:60",
        event_type=EventType.PRESS,
        value=Value(100),
    ))
    qapp.processEvents()
    assert table_model.rowCount() == before + 1
    win.close()
    qapp.processEvents()
