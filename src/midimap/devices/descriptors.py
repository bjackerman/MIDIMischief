"""HID descriptor-based device metadata.

Many HID controllers (gamepads, custom macro pads) report raw bytes
through hidapi. To turn those bytes into meaningful ``control_id``
strings (``button:3``, ``axis:0``), we use a *device descriptor*
file in YAML/JSON that maps a vendor/product ID to:

- a friendly ``name`` and ``manufacturer`` override
- a ``layout`` describing which bytes / bits / axes correspond to
  which controls

The descriptor is loaded once at startup from
``~/.config/midimap/devices/*.yaml`` (per-user). The bundled
descriptors live in ``midimap/devices/builtin_descriptors/``.

A descriptor looks like::

    vendor_id: 0x046d      # Logitech
    product_id: 0xb38f    # POP Icon Keys
    name: "Logitech POP Icon Keys (Keys)"
    layout:
      type: "boot"        # 'boot' = boot-protocol keyboard reports
      # when type='boot', a report is 8 bytes:
      #   [modifier, reserved, key0..key5]
      keys_byte: 2        # offset where the key array starts
      modifier_byte: 0
      max_keys: 6

    # For gamepad-style descriptors (raw report), use type='report'
    # and specify the byte/bit mapping for buttons and axes.

The descriptor loader is lenient: missing fields fall back to
sensible defaults, and a descriptor can be overridden by a user-level
file with the same vid/pid.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


# ---- descriptor data classes (lightweight; we don't use pydantic
#      for these because they are user-edited and we want forgiving
#      parsing) ----


class DeviceDescriptor:
    """Static metadata + layout for a known HID device."""

    def __init__(
        self,
        vendor_id: int,
        product_id: int,
        name: str,
        layout: dict[str, Any],
        *,
        manufacturer: str | None = None,
        source: Path | None = None,
    ) -> None:
        self.vendor_id = int(vendor_id)
        self.product_id = int(product_id)
        self.name = name
        self.manufacturer = manufacturer
        self.layout = layout
        self.source = source

    @property
    def vid_pid(self) -> tuple[int, int]:
        return (self.vendor_id, self.product_id)

    def matches(self, vendor_id: int, product_id: int) -> bool:
        return self.vendor_id == vendor_id and self.product_id == product_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "layout": self.layout,
        }


# ---- loader ----


def _parse_one(raw: dict[str, Any], source: Path | None) -> DeviceDescriptor | None:
    try:
        vid = int(raw["vendor_id"])
        pid = int(raw["product_id"])
    except (KeyError, TypeError, ValueError):
        log.warning("descriptor missing/invalid vid/pid: %s", raw)
        return None
    name = str(raw.get("name", f"VID={vid:04x} PID={pid:04x}"))
    manufacturer = raw.get("manufacturer")
    layout = dict(raw.get("layout") or {})
    if "type" not in layout:
        layout["type"] = "generic"
    return DeviceDescriptor(
        vendor_id=vid,
        product_id=pid,
        name=name,
        manufacturer=manufacturer,
        layout=layout,
        source=source,
    )


def load_descriptors_from(path: Path) -> list[DeviceDescriptor]:
    """Load all descriptors from a single YAML/JSON file.

    A file may contain either a single mapping or a list of
    mappings. A list lets users group multiple devices.
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("could not read descriptor file %s: %s", path, e)
        return []
    try:
        data = yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else None
        if data is None:
            # Fall back to JSON
            import json

            data = json.loads(text)
    except Exception as e:
        log.warning("could not parse descriptor file %s: %s", path, e)
        return []
    out: list[DeviceDescriptor] = []
    if isinstance(data, dict):
        d = _parse_one(data, source=path)
        if d is not None:
            out.append(d)
    elif isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            d = _parse_one(entry, source=path)
            if d is not None:
                out.append(d)
    return out


def load_all_descriptors(search_paths: list[Path]) -> dict[tuple[int, int], DeviceDescriptor]:
    """Load every descriptor from a list of paths, last-wins on conflicts."""
    out: dict[tuple[int, int], DeviceDescriptor] = {}
    for path in search_paths:
        for desc in load_descriptors_from(path):
            existing = out.get(desc.vid_pid)
            if existing is not None and existing.source is not None:
                log.info(
                    "descriptor for %04x:%04x redefined by %s (was %s)",
                    desc.vendor_id,
                    desc.product_id,
                    path,
                    existing.source,
                )
            out[desc.vid_pid] = desc
    return out


def default_search_paths(user_config_dir: Path) -> list[Path]:
    """Compute the descriptor search path: builtin + user."""
    # Built-in descriptors ship with the package
    builtin = Path(__file__).parent / "builtin_descriptors"
    user = user_config_dir / "devices"
    return [builtin, user]


__all__ = [
    "DeviceDescriptor",
    "default_search_paths",
    "load_all_descriptors",
    "load_descriptors_from",
]
