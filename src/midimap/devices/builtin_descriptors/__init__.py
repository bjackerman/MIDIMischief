"""Built-in HID device descriptors.

The actual descriptors live in ``descriptors.yaml`` in this directory
so users can browse them as a template for their own overrides
(``~/.config/midimap/devices/*.yaml``).

This ``__init__`` exists so the directory is a Python package; the
descriptors are loaded by :mod:`midimap.devices.descriptors` directly
from the YAML file.
"""

from __future__ import annotations
