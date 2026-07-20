"""Built-in HID device descriptors.

The catalog is split into YAML files by device family so users can browse
and copy a focused template for their own overrides
(``~/.config/midimap/devices/*.yaml``).

This ``__init__`` exists so the directory is a Python package; the
descriptors are loaded by :mod:`midimap.devices.descriptors` directly
from the YAML file.
"""

from __future__ import annotations
