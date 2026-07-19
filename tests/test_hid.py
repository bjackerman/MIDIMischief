"""Tests for the HID normalizer + descriptor loader."""

from __future__ import annotations

import json
from pathlib import Path

from midimap.devices.descriptors import (
    DeviceDescriptor,
    load_all_descriptors,
    load_descriptors_from,
)
from midimap.devices.hid_normalizer import hid_report_to_events
from midimap.events import EventType

# ---- descriptors ----


def _desc(vid: int, pid: int, name: str = "Test", layout: dict | None = None) -> DeviceDescriptor:
    return DeviceDescriptor(
        vendor_id=vid,
        product_id=pid,
        name=name,
        layout=layout or {"type": "boot"},
    )


def test_load_descriptors_from_yaml(tmp_path: Path):
    p = tmp_path / "d.yaml"
    p.write_text(
        "vendor_id: 1133\n"
        "product_id: 45967\n"
        "name: 'Logitech POP Icon Keys'\n"
        "layout:\n"
        "  type: boot\n"
    )
    out = load_descriptors_from(p)
    assert len(out) == 1
    assert out[0].name == "Logitech POP Icon Keys"
    assert out[0].layout["type"] == "boot"


def test_load_descriptors_from_json_list(tmp_path: Path):
    p = tmp_path / "d.json"
    p.write_text(
        json.dumps(
            [
                {"vendor_id": 1, "product_id": 1, "name": "A", "layout": {"type": "boot"}},
                {"vendor_id": 2, "product_id": 2, "name": "B", "layout": {"type": "boot"}},
            ]
        )
    )
    out = load_descriptors_from(p)
    assert len(out) == 2
    assert {d.name for d in out} == {"A", "B"}


def test_load_descriptors_missing_file(tmp_path: Path):
    assert load_descriptors_from(tmp_path / "missing.yaml") == []


def test_load_all_descriptors_last_wins(tmp_path: Path):
    p1 = tmp_path / "a.yaml"
    p1.write_text("vendor_id: 1\nproduct_id: 1\nname: 'first'\nlayout: {type: boot}\n")
    p2 = tmp_path / "b.yaml"
    p2.write_text("vendor_id: 1\nproduct_id: 1\nname: 'second'\nlayout: {type: boot}\n")
    out = load_all_descriptors([p1, p2])
    assert out[(1, 1)].name == "second"


def test_load_descriptors_invalid_missing_vid(tmp_path: Path):
    p = tmp_path / "d.yaml"
    p.write_text("name: 'broken'\nlayout: {type: boot}\n")
    assert load_descriptors_from(p) == []


# ---- normalizer ----


def test_boot_keyboard_emits_modifier_presses():
    descriptor = _desc(0x046d, 0xB38F, "Test", {"type": "boot"})
    # Modifier byte: ctrl (bit0) + shift (bit1) = 0b00000011
    # Key code 'a' = 0x04 in USB HID usage table
    report = bytes([0b00000011, 0, 0x04, 0, 0, 0, 0, 0])
    events, _ = hid_report_to_events(
        report, device_id="hid:test", descriptor=descriptor, timestamp_ms=0
    )
    cids = {e.control_id: e.event_type for e in events}
    assert cids["mod:ctrl"] == EventType.PRESS
    assert cids["mod:shift"] == EventType.PRESS
    assert cids["key:4"] == EventType.PRESS
    assert all(e.device_id == "hid:test" for e in events)


def test_boot_keyboard_ignores_reserved_and_unset():
    descriptor = _desc(1, 1, "Test", {"type": "boot"})
    report = bytes([0, 0, 0, 0, 0, 0, 0, 0])
    events, _ = hid_report_to_events(
        report, device_id="hid:test", descriptor=descriptor, timestamp_ms=0
    )
    assert events == []


def test_boot_keyboard_short_report_is_ignored():
    descriptor = _desc(1, 1, "Test", {"type": "boot"})
    events, _ = hid_report_to_events(
        bytes([0, 0, 0]), device_id="hid:test", descriptor=descriptor, timestamp_ms=0
    )
    assert events == []


def test_generic_layout_button_press_and_release():
    descriptor = _desc(1, 1, "Test", {
        "type": "generic",
        "buttons": [{"byte": 0, "bit": 0, "name": "fire"}],
    })
    # press
    events_a, state_a = hid_report_to_events(
        bytes([0b00000001]), device_id="hid:t", descriptor=descriptor, timestamp_ms=0
    )
    assert any(e.event_type == EventType.PRESS and e.control_id == "fire" for e in events_a)
    # release
    events_b, _ = hid_report_to_events(
        bytes([0b00000000]), device_id="hid:t", descriptor=descriptor,
        timestamp_ms=0, prev_state=state_a,
    )
    assert any(e.event_type == EventType.RELEASE and e.control_id == "fire" for e in events_b)


def test_generic_layout_axis_change():
    descriptor = _desc(1, 1, "Test", {
        "type": "generic",
        "axes": [{"byte": 0, "size": 1, "signed": False, "name": "x"}],
    })
    events, _ = hid_report_to_events(
        bytes([0x55]), device_id="hid:t", descriptor=descriptor, timestamp_ms=0
    )
    assert len(events) == 1
    assert events[0].event_type == EventType.CHANGE
    assert int(events[0].value) == 0x55
    assert events[0].control_id == "x"


def test_unknown_layout_type_warns_and_returns_empty():
    descriptor = _desc(1, 1, "Test", {"type": "mystery"})
    events, _ = hid_report_to_events(
        bytes([0]), device_id="hid:t", descriptor=descriptor, timestamp_ms=0
    )
    assert events == []


def test_descriptor_matches():
    d = _desc(0x046D, 0xB38F)
    assert d.matches(0x046D, 0xB38F)
    assert not d.matches(0x046D, 0x1234)
