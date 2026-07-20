"""Descriptor-driven visual monitor for MIDI and HID control surfaces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Slot
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ...events import EventType, NormalizedEvent


@dataclass(frozen=True)
class RenderControl:
    """One drawable control described by device layout metadata."""

    control_id: str
    kind: str
    x: float
    y: float
    width: float = 1.0
    height: float = 1.0
    label: str = ""
    maximum: int = 127


class DeviceRenderWidget(QWidget):
    """Paint a device layout and reflect incoming :class:`NormalizedEvent` values.

    Layouts may use a ``controls`` list (each item has ``type``/``kind``,
    ``control_id``, ``x``, and ``y``), or category lists named ``pads``,
    ``knobs``, ``sliders``, and ``buttons``. Coordinates are logical layout
    units, so descriptors remain independent of the widget's pixel size.
    """

    _SUPPORTED_KINDS = frozenset({"pad", "knob", "slider", "button"})

    def __init__(self, descriptor: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controls: list[RenderControl] = []
        self._values: dict[str, int] = {}
        self._pressed: set[str] = set()
        self._message = "Select a device to view its control layout."
        self.setMinimumHeight(180)
        self.set_descriptor(descriptor)

    @property
    def controls(self) -> tuple[RenderControl, ...]:
        """The normalized descriptor controls, exposed for inspection and tests."""
        return tuple(self._controls)

    @property
    def values(self) -> dict[str, int]:
        """Current control values keyed by descriptor control ID."""
        return dict(self._values)

    def set_descriptor(self, descriptor: Any | None) -> None:
        """Load a descriptor object, a layout mapping, or clear the display.

        ``DeviceDescriptor`` is deliberately duck-typed here so this reusable
        GUI widget does not require HID support at import time.
        """
        layout = getattr(descriptor, "layout", descriptor)
        if not isinstance(layout, Mapping):
            self._controls = []
            self._message = "This device has no descriptor layout to display."
        else:
            self._controls = self._parse_controls(layout)
            self._message = (
                "This descriptor does not include visual control layout metadata."
                if not self._controls
                else ""
            )
        self._values.clear()
        self._pressed.clear()
        self.update()

    def set_layout(self, layout: Mapping[str, Any] | None) -> None:
        """Convenience alias for callers that retain layout metadata directly."""
        self.set_descriptor(layout)

    @Slot(object)
    def update_event(self, event: NormalizedEvent) -> None:
        """Update one control's value and pressed highlight from a live event."""
        control_id = str(event.control_id)
        if not any(control.control_id == control_id for control in self._controls):
            return
        self._values[control_id] = int(event.value)
        if event.event_type == EventType.PRESS:
            self._pressed.add(control_id)
        elif event.event_type in {EventType.RELEASE, EventType.TAP}:
            self._pressed.discard(control_id)
        self.update()

    # Compatibility-friendly slot name for direct signal connections.
    on_event = update_event

    def paintEvent(self, _event: object) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        if not self._controls:
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._message)
            return

        bounds = self._layout_bounds()
        margin = 18.0
        available = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        scale = min(available.width() / bounds.width(), available.height() / bounds.height())
        offset = QPointF(
            available.left() + (available.width() - bounds.width() * scale) / 2 - bounds.left() * scale,
            available.top() + (available.height() - bounds.height() * scale) / 2 - bounds.top() * scale,
        )
        for control in self._controls:
            rect = QRectF(control.x * scale + offset.x(), control.y * scale + offset.y(),
                          control.width * scale, control.height * scale).adjusted(3, 3, -3, -3)
            self._paint_control(painter, control, rect)

    def _paint_control(self, painter: QPainter, control: RenderControl, rect: QRectF) -> None:
        active = control.control_id in self._pressed
        value = self._values.get(control.control_id, 0)
        fraction = max(0.0, min(1.0, value / max(1, control.maximum)))
        outline = QColor("#4da3ff") if active else self.palette().mid().color()
        fill = QColor("#2676c8") if active else self.palette().alternateBase().color()
        painter.setPen(QPen(outline, 2))

        if control.kind == "knob":
            diameter = min(rect.width(), rect.height())
            circle = QRectF(rect.left() + (rect.width() - diameter) / 2, rect.top(), diameter, diameter)
            painter.setBrush(fill)
            painter.drawEllipse(circle)
            painter.setPen(QPen(self.palette().text().color(), 2))
            center = circle.center()
            painter.drawLine(center, QPointF(center.x(), circle.bottom() - diameter * fraction))
        elif control.kind == "slider":
            track = QRectF(rect.center().x() - rect.width() * 0.12, rect.top(), rect.width() * 0.24, rect.height())
            painter.setBrush(self.palette().alternateBase())
            painter.drawRoundedRect(track, 3, 3)
            handle_y = track.bottom() - track.height() * fraction
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(rect.left(), handle_y - 4, rect.width(), 8), 3, 3)
        else:
            painter.setBrush(fill)
            if control.kind == "pad":
                painter.drawRoundedRect(rect, 8, 8)
            else:
                painter.drawRoundedRect(rect, 4, 4)

        text = control.label or control.control_id
        if control.control_id in self._values:
            text = f"{text}\n{value}"
        painter.setPen(self.palette().text().color())
        font = painter.font()
        font.setPointSize(max(7, min(10, int(rect.height() / 5))))
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

    def _layout_bounds(self) -> QRectF:
        right = max(control.x + control.width for control in self._controls)
        bottom = max(control.y + control.height for control in self._controls)
        return QRectF(0, 0, max(1.0, right), max(1.0, bottom))

    @classmethod
    def _parse_controls(cls, layout: Mapping[str, Any]) -> list[RenderControl]:
        raw_controls: list[tuple[str, Any]] = []
        controls = layout.get("controls")
        if isinstance(controls, Mapping):
            raw_controls.extend((str(key), value) for key, value in controls.items())
        elif isinstance(controls, list):
            raw_controls.extend(("", value) for value in controls)
        for plural, kind in (
            ("pads", "pad"),
            ("knobs", "knob"),
            ("sliders", "slider"),
            ("buttons", "button"),
            # Generic HID descriptors already use these normalizer-facing
            # names, so they get a useful visual without duplicate metadata.
            ("axes", "slider"),
        ):
            entries = layout.get(plural)
            if isinstance(entries, list):
                raw_controls.extend((kind, value) for value in entries)

        parsed: list[RenderControl] = []
        kind_counts: dict[str, int] = {}
        for index, (default_kind, item) in enumerate(raw_controls):
            if isinstance(item, str):
                item = {"control_id": item}
            if not isinstance(item, Mapping):
                continue
            kind = str(item.get("type", item.get("kind", default_kind))).lower().rstrip("s")
            if kind not in cls._SUPPORTED_KINDS:
                continue
            kind_index = kind_counts.get(kind, 0)
            kind_counts[kind] = kind_index + 1
            control_id = item.get(
                "control_id", item.get("id", item.get("control", item.get("name")))
            )
            if control_id is None and default_kind:
                control_id = f"{'axis' if kind == 'slider' and default_kind == 'slider' else kind}:{kind_index}"
            if control_id is None:
                continue
            x = float(item.get("x", index % 8))
            y = float(item.get("y", index // 8))
            width = float(item.get("width", item.get("w", 1)))
            height = float(item.get("height", item.get("h", 1)))
            parsed.append(RenderControl(str(control_id), kind, x, y, width, height,
                                        str(item.get("label", "")), int(item.get("max", item.get("maximum", 127)))))
        return parsed


__all__ = ["DeviceRenderWidget", "RenderControl"]
