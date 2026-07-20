"""Tests for ``DeviceManager.filter_devices`` and the per-port callback
factory. The full manager loop needs real MIDI hardware; that is exercised
by the ``monitor`` CLI command, not by these unit tests.
"""

from __future__ import annotations

import time
from unittest.mock import Mock

import mido
import pytest

from midimap.devices.manager import (
    DeviceManager,
    _device_id,
    _port_name_from_id,
    filter_devices,
)
from midimap.events import EventType, NormalizedEvent


class _FakeHIDManager:
    def __init__(self) -> None:
        self.connected: set[str] = set()
        self.queried_ids: list[str] = []

    def set_emit(self, emit) -> None:
        self.emit = emit

    def is_connected(self, device_id: str) -> bool:
        self.queried_ids.append(device_id)
        return device_id in self.connected

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self.connected.clear()


@pytest.mark.parametrize(
    "port,expected",
    [
        ("Maschine Mikro MK3 MIDI 1", "midi:Maschine Mikro MK3 MIDI 1"),
        ("ATM SQ 0", "midi:ATM SQ 0"),
    ],
)
def test_device_id_roundtrip(port: str, expected: str) -> None:
    assert _device_id(port) == expected
    assert _port_name_from_id(expected) == port


def test_filter_devices_no_filter_returns_all():
    devices = [
        {"id": "midi:A", "name": "A", "kind": "midi"},
        {"id": "midi:B", "name": "B", "kind": "midi"},
    ]
    assert filter_devices(devices) == devices


def test_filter_devices_substring_case_insensitive():
    devices = [
        {"id": "midi:Maschine Mikro 1", "name": "Maschine Mikro 1", "kind": "midi"},
        {"id": "midi:ATM SQ 0", "name": "ATM SQ 0", "kind": "midi"},
    ]
    out = filter_devices(devices, name_contains="maschine")
    assert len(out) == 1
    assert out[0]["name"] == "Maschine Mikro 1"


def test_filter_devices_no_match_returns_empty():
    devices = [{"id": "midi:ATM SQ 0", "name": "ATM SQ 0", "kind": "midi"}]
    assert filter_devices(devices, name_contains="NonexistentDevice") == []


def test_make_callback_tags_event_with_device_id():
    """The per-port closure must stamp each event with the right device_id."""
    mgr = DeviceManager()
    received: list[NormalizedEvent] = []
    mgr.subscribe(lambda e: received.append(e))
    cb = mgr._make_callback("midi:Test Device 7")

    cb(mido.Message("note_on", channel=0, note=60, velocity=100))
    cb(mido.Message("control_change", channel=0, control=7, value=64))
    time.sleep(0.05)

    assert len(received) == 2
    assert received[0].device_id == "midi:Test Device 7"
    assert received[0].control_id == "note:60"
    assert received[0].event_type == EventType.PRESS
    assert received[1].device_id == "midi:Test Device 7"
    assert received[1].control_id == "cc:7"
    assert received[1].event_type == EventType.CHANGE


def test_callback_after_stop_is_noop():
    """Callbacks may still be invoked by rtmidi after stop() — must be safe."""
    mgr = DeviceManager()
    received: list[NormalizedEvent] = []
    mgr.subscribe(lambda e: received.append(e))
    cb = mgr._make_callback("midi:Test")

    mgr.start()
    cb(mido.Message("note_on", channel=0, note=60, velocity=100))
    mgr.stop()
    # This simulates a late rtmidi callback after stop()
    cb(mido.Message("note_on", channel=0, note=62, velocity=80))
    time.sleep(0.05)

    # Only the first event should have made it through
    assert len(received) == 1
    assert received[0].control_id == "note:60"


def test_is_connected_delegates_to_hid_manager():
    hid = _FakeHIDManager()
    device_id = "hid:0001:0001:abc"
    hid.connected.add(device_id)
    mgr = DeviceManager(hid_manager=hid)

    assert mgr.is_connected(device_id)
    assert hid.queried_ids == [device_id]


def test_is_connected_returns_false_when_hid_is_disabled():
    mgr = DeviceManager(hid_manager=False)

    assert not mgr.is_connected("hid:0001:0001:abc")


def test_hid_is_connected_returns_false_after_stop():
    hid = _FakeHIDManager()
    device_id = "hid:0001:0001:abc"
    hid.connected.add(device_id)
    mgr = DeviceManager(hid_manager=hid)

    mgr.stop()

    assert not mgr.is_connected(device_id)
class _PollingStop:
    """Deterministic stand-in for Event used to run the polling loop inline."""

    def __init__(self, stop_after_waits: int) -> None:
        self._stop_after_waits = stop_after_waits
        self._waits = 0
        self._set = False

    def is_set(self) -> bool:
        return self._set

    def wait(self, _timeout: float) -> bool:
        self._waits += 1
        if self._waits >= self._stop_after_waits:
            self._set = True
        return self._set


def test_hotplug_loop_closes_disappeared_port_and_reconnects_it(monkeypatch):
    """A manually connected port remains intended after unplug/replug."""
    ports = iter([["Controller"], [], ["Controller"]])
    monkeypatch.setattr(mido, "get_input_names", lambda: next(ports))
    first_port = Mock()
    reconnected_port = Mock()
    open_input = Mock(side_effect=[first_port, reconnected_port])
    monkeypatch.setattr(mido, "open_input", open_input)
    events: list[dict[str, str]] = []
    mgr = DeviceManager(hid_manager=False, hotplug_callback=events.append)

    mgr.connect("midi:Controller")
    mgr._stop = _PollingStop(stop_after_waits=3)  # type: ignore[assignment]
    mgr._hotplug_loop()

    assert open_input.call_args_list[0].args == ("Controller",)
    assert open_input.call_args_list[1].args == ("Controller",)
    first_port.close.assert_called_once()
    assert [event["event"] for event in events] == [
        "connected",
        "disconnected",
        "reconnected",
    ]
    assert "midi:Controller" in mgr._open_ports


def test_hotplug_loop_only_auto_connects_ports_selected_by_hook(monkeypatch):
    ports = iter([[], ["Wanted Controller", "Unrelated Controller"]])
    monkeypatch.setattr(mido, "get_input_names", lambda: next(ports))
    open_input = Mock(return_value=Mock())
    monkeypatch.setattr(mido, "open_input", open_input)
    selected: list[str] = []

    def select_wanted(device: dict[str, str]) -> bool:
        selected.append(device["name"])
        return device["name"] == "Wanted Controller"

    mgr = DeviceManager(hid_manager=False, device_selector=select_wanted)
    mgr._stop = _PollingStop(stop_after_waits=2)  # type: ignore[assignment]
    mgr._hotplug_loop()

    open_input.assert_called_once()
    assert open_input.call_args.args == ("Wanted Controller",)
    assert set(selected) == {"Wanted Controller", "Unrelated Controller"}
