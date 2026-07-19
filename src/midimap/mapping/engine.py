"""MappingEngine — turns NormalizedEvents into Actions using a Profile."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..events import EventType, NormalizedEvent

if TYPE_CHECKING:
    from ..actions import Action
    from ..profile.schema import Profile

log = logging.getLogger(__name__)


class MappingEngine:
    """Holds the active Profile, tracks per-control press state and active
    hold-to-activate layers, and turns every incoming :class:`NormalizedEvent`
    into an :class:`Action` (or ``None`` if no mapping matches).

    The engine is **stateful** because:

    - It remembers when each button was pressed (to evaluate release
      mappings with ``min_press_ms`` / ``max_press_ms``).
    - It tracks which hold-to-activate layers are currently held down
      (shift-style behaviour).

    It is **not** thread-safe; the GUI/CLI is expected to feed events
    from a single dispatcher thread (the EventBus's worker thread is
    fine).
    """

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        # (device_id, control_id) -> monotonic ms when press started
        self._press_starts: dict[tuple[str, str], int] = {}
        # set of currently-active layer indices (0 is always present)
        self._active_layers: set[int] = {0}
        # layer_idx -> set of (device_id, control_id) currently holding it
        self._layer_holders: dict[int, set[tuple[str, str]]] = {}

    # ---- public ----

    @property
    def active_layers(self) -> frozenset[int]:
        return frozenset(self._active_layers)

    def process(self, event: NormalizedEvent) -> Action | None:
        # Update layer state first so the matching pass sees the current set.
        self._update_layers(event)

        # Always track press start time, regardless of whether any
        # mapping is currently listening for a press. A later release
        # may be filtered by a mapping that needs the duration.
        key = (event.device_id, event.control_id)
        if event.event_type == EventType.PRESS:
            self._press_starts[key] = event.timestamp_ms

        # Collect candidates from all active layers, in layer order. Last
        # mapping in a layer wins; if multiple layers match, the higher-
        # numbered layer wins.
        candidates: list = []
        for layer_idx in sorted(self._active_layers):
            layer = self.profile.layers.get(layer_idx)
            if layer is None:
                continue
            for mapping in layer.mappings:
                if self._matches(mapping, event):
                    candidates.append(mapping)

        if not candidates:
            return None

        chosen = candidates[-1]
        # Lazy import to avoid a circular dep at module load.
        from ..actions import Action

        return Action.from_mapping(chosen, event)

    # ---- internals ----

    def _matches(self, mapping, event: NormalizedEvent) -> bool:  # type: ignore[no-untyped-def]
        spec = mapping.input
        if spec.control != event.control_id:
            return False
        if spec.event is not None and spec.event != event.event_type:
            return False
        if spec.channel is not None and spec.channel != event.channel:
            return False
        if spec.value_min is not None and event.value < spec.value_min:
            return False
        if spec.value_max is not None and event.value > spec.value_max:
            return False

        # Press-duration filtering: only checked on release, and only if
        # we have a recorded start time.
        if event.event_type == EventType.RELEASE:
            key = (event.device_id, event.control_id)
            started = self._press_starts.get(key)
            if (
                started is not None
                and (spec.min_press_ms is not None or spec.max_press_ms is not None)
            ):
                dur = event.timestamp_ms - started
                if spec.min_press_ms is not None and dur < spec.min_press_ms:
                    return False
                if spec.max_press_ms is not None and dur > spec.max_press_ms:
                    return False
            return True

        # CHANGE matches unconditionally (value range already filtered above).
        if event.event_type == EventType.CHANGE:
            return True

        # PRESS already passed the spec.event check; if we got here, it matches.
        return event.event_type == EventType.PRESS

    def _update_layers(self, event: NormalizedEvent) -> None:
        """Track hold-to-activate layers.

        A hold-to-activate layer is "active" while **any** of its mappings
        has a pressed-and-not-released control that matches that mapping's
        input. (Simple heuristic: the first mapping in the layer is the
        "shift" key. M3 will let users pick explicitly.)
        """
        for layer_idx, layer in self.profile.layers.items():
            if not layer.hold_to_activate:
                continue
            if not layer.mappings:
                continue
            shift = layer.mappings[0].input.control
            key = (event.device_id, event.control_id)
            if event.event_type == EventType.PRESS and event.control_id == shift:
                self._active_layers.add(layer_idx)
                self._layer_holders.setdefault(layer_idx, set()).add(key)
            elif event.event_type == EventType.RELEASE:
                holders = self._layer_holders.get(layer_idx, set())
                if key in holders:
                    holders.discard(key)
                    if not holders:
                        self._active_layers.discard(layer_idx)

    def forget_press(self, device_id: str, control_id: str) -> None:
        """Drop any recorded press start for a control. Useful when a
        device is disconnected mid-press to avoid stale state."""
        self._press_starts.pop((device_id, control_id), None)
