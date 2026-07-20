"""Focused tests for the descriptor-driven device monitor widget."""

from __future__ import annotations

from midimap.events import EventType, NormalizedEvent, Value
from midimap.gui.widgets.device_render import DeviceRenderWidget


def _layout() -> dict[str, object]:
    return {
        "controls": [
            {"type": "pad", "control_id": "note:36", "x": 0, "y": 0, "label": "Kick"},
            {"type": "knob", "control_id": "cc:10", "x": 1, "y": 0, "max": 127},
            {"type": "slider", "control_id": "axis:0", "x": 2, "y": 0, "maximum": 32767},
            {"type": "button", "control_id": "button:1", "x": 3, "y": 0},
        ]
    }


def test_descriptor_layout_creates_each_supported_control(qapp):  # type: ignore[no-untyped-def]
    widget = DeviceRenderWidget(_layout())
    widget.resize(480, 200)
    widget.show()
    qapp.processEvents()

    assert [(control.control_id, control.kind) for control in widget.controls] == [
        ("note:36", "pad"),
        ("cc:10", "knob"),
        ("axis:0", "slider"),
        ("button:1", "button"),
    ]
    # Exercise the QPainter path, not only descriptor parsing.
    assert not widget.grab().isNull()
    widget.close()


def test_normalized_events_update_only_known_control_state(qapp):  # type: ignore[no-untyped-def]
    widget = DeviceRenderWidget(_layout())
    widget.update_event(NormalizedEvent("midi:test", "cc:10", EventType.CHANGE, Value(73)))
    widget.update_event(NormalizedEvent("midi:test", "unknown", EventType.CHANGE, Value(99)))
    widget.update_event(NormalizedEvent("midi:test", "button:1", EventType.PRESS, Value(1)))
    qapp.processEvents()

    assert widget.values == {"cc:10": 73, "button:1": 1}
    assert "button:1" in widget._pressed
    widget.update_event(NormalizedEvent("midi:test", "button:1", EventType.RELEASE, Value(0)))
    assert widget.values["button:1"] == 0
    assert "button:1" not in widget._pressed


def test_missing_descriptor_shows_graceful_fallback(qapp):  # type: ignore[no-untyped-def]
    widget = DeviceRenderWidget()
    widget.resize(300, 120)
    widget.show()
    qapp.processEvents()

    assert widget.controls == ()
    assert "no descriptor" in widget._message.lower()
    assert not widget.grab().isNull()
    widget.close()


def test_devices_tab_forwards_selected_device_events_to_render(qapp):  # type: ignore[no-untyped-def]
    from midimap.gui.qt_bridge import EventBusQtBridge
    from midimap.gui.tabs.devices import DevicesTab

    class Manager:
        def list_devices(self):  # type: ignore[no-untyped-def]
            return [{"id": "hid:demo", "name": "Demo", "descriptor": True, "layout": _layout()}]

        def connect(self, _device_id):  # type: ignore[no-untyped-def]
            pass

        def disconnect(self, _device_id):  # type: ignore[no-untyped-def]
            pass

    bridge = EventBusQtBridge()
    tab = DevicesTab(Manager(), bridge)
    tab._device_list.setCurrentRow(0)
    bridge.push(NormalizedEvent("hid:demo", "cc:10", EventType.CHANGE, Value(42)))
    qapp.processEvents()

    assert tab._device_render.values["cc:10"] == 42
    tab.close()
