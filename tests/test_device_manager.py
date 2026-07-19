"""Tests for ``DeviceManager.filter_devices`` and the per-port callback
factory. The full manager loop needs real MIDI hardware; that is exercised
by the ``monitor`` CLI command, not by these unit tests.
"""

from __future__ import annotations

import time

import mido
import pytest

from midimap.devices.manager import (
    DeviceManager,
    _device_id,
    _port_name_from_id,
    filter_devices,
)
from midimap.events import EventType, NormalizedEvent


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
