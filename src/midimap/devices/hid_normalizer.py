"""HID normalizer — turn hidapi reports into NormalizedEvent.

HID devices don't speak a single protocol. The most common layouts
on consumer HID controllers are:

- **Boot keyboard** (8-byte reports): [mod, reserved, key0..key5]
  Emits PRESS on a key going from absent -> present, RELEASE when
  the key disappears from the array.
- **Generic report** (variable length): a custom byte/bit layout
  specified in a :class:`DeviceDescriptor`.

The normalizer does not know the layout itself — the descriptor
provides it. The result is the same ``NormalizedEvent`` used by the
MIDI backend so the rest of the pipeline is identical.
"""

from __future__ import annotations

import logging

from ..events import EventType, NormalizedEvent, Value
from .descriptors import DeviceDescriptor

log = logging.getLogger(__name__)


def _boot_keyboard_to_events(
    report: bytes,
    *,
    device_id: str,
    descriptor: DeviceDescriptor,
    timestamp_ms: int,
) -> list[NormalizedEvent]:
    """Decode a boot-protocol keyboard report."""
    if len(report) < 8:
        return []
    modifier = report[0]
    # report[1] is reserved/oem
    keys = list(report[2:8])
    events: list[NormalizedEvent] = []
    # Modifiers
    for bit, name in enumerate(("ctrl", "shift", "alt", "meta_l", "meta_r", "alt_gr", "?", "?")):
        if modifier & (1 << bit):
            events.append(
                NormalizedEvent(
                    device_id=device_id,
                    control_id=f"mod:{name}",
                    event_type=EventType.PRESS,
                    value=Value(1),
                    timestamp_ms=timestamp_ms,
                )
            )
    # Each key
    for k in keys:
        if k == 0:
            continue
        events.append(
            NormalizedEvent(
                device_id=device_id,
                control_id=f"key:{k}",
                event_type=EventType.PRESS,
                value=Value(1),
                timestamp_ms=timestamp_ms,
            )
        )
    return events


def hid_report_to_events(
    report: bytes,
    *,
    device_id: str,
    descriptor: DeviceDescriptor | None = None,
    timestamp_ms: int = 0,
    prev_state: dict[str, int] | None = None,
) -> tuple[list[NormalizedEvent], dict[str, int]]:
    """Decode a raw HID report.

    Returns a tuple of ``(events, new_state)``. ``new_state`` is the
    per-control state observed in this report; the caller can pass
    it back in as ``prev_state`` on the next call to compute
    press/release deltas for non-boot protocols.

    For boot-keyboard devices the prev_state is not needed: the
    protocol is stateless (the report always lists all currently
    pressed keys). For generic layouts we track per-bit state.
    """
    if descriptor is None:
        descriptor = _generic_descriptor()
    layout_type = descriptor.layout.get("type", "generic")
    if layout_type == "boot":
        events = _boot_keyboard_to_events(
            report,
            device_id=device_id,
            descriptor=descriptor,
            timestamp_ms=timestamp_ms,
        )
        return events, {}

    if layout_type == "generic":
        return _generic_to_events(
            report,
            device_id=device_id,
            descriptor=descriptor,
            timestamp_ms=timestamp_ms,
            prev_state=dict(prev_state or {}),
        )

    log.warning("unknown HID layout type %r for %s", layout_type, device_id)
    return [], {}


def _generic_to_events(
    report: bytes,
    *,
    device_id: str,
    descriptor: DeviceDescriptor,
    timestamp_ms: int,
    prev_state: dict[str, int],
) -> tuple[list[NormalizedEvent], dict[str, int]]:
    """Decode a generic report using buttons[] + axes[] from the layout.

    The layout looks like::

        layout:
          type: generic
          buttons:
            - byte: 1     # offset
              bit: 0      # bit within the byte
              name: "A"   # optional friendly name
          axes:
            - byte: 2
              size: 1     # 1, 2, or 4 bytes
              signed: false
              name: "x"

    For each button we emit PRESS / RELEASE based on prev_state
    diff. For each axis we always emit CHANGE.
    """
    events: list[NormalizedEvent] = []
    new_state: dict[str, int] = {}
    for i, btn in enumerate(descriptor.layout.get("buttons") or []):
        byte = int(btn.get("byte", 0))
        bit = int(btn.get("bit", 0))
        if byte >= len(report):
            continue
        value = 1 if (report[byte] & (1 << bit)) else 0
        cid = btn.get("name") or f"button:{i}"
        new_state[cid] = value
        prev = prev_state.get(cid, 0)
        if value != prev:
            events.append(
                NormalizedEvent(
                    device_id=device_id,
                    control_id=cid,
                    event_type=EventType.PRESS if value else EventType.RELEASE,
                    value=Value(value),
                    timestamp_ms=timestamp_ms,
                )
            )
    for i, ax in enumerate(descriptor.layout.get("axes") or []):
        byte = int(ax.get("byte", 0))
        size = int(ax.get("size", 1))
        signed = bool(ax.get("signed", False))
        if byte + size > len(report):
            continue
        raw = int.from_bytes(report[byte : byte + size], "little", signed=signed)
        cid = ax.get("name") or f"axis:{i}"
        events.append(
            NormalizedEvent(
                device_id=device_id,
                control_id=cid,
                event_type=EventType.CHANGE,
                value=Value(raw),
                timestamp_ms=timestamp_ms,
            )
        )
        new_state[cid] = raw
    return events, new_state


def _generic_descriptor() -> DeviceDescriptor:
    """Fallback descriptor for devices we don't know about.

    Treats byte 0 as a button bitmask (8 buttons) and bytes 1..N as
    8-bit unsigned axes. This is a common convention for
    do-it-yourself macro pads and breakout boards.
    """
    return DeviceDescriptor(
        vendor_id=0,
        product_id=0,
        name="Generic HID",
        layout={
            "type": "generic",
            "buttons": [{"byte": b, "bit": 0, "name": f"button:{b}"} for b in range(8)],
            "axes": [{"byte": 1 + i, "size": 1, "signed": False, "name": f"axis:{i}"} for i in range(8)],
        },
    )


__all__ = ["_generic_descriptor", "hid_report_to_events"]
