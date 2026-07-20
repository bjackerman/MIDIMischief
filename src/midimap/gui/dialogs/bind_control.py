"""Bind-control dialog (3-page wizard skeleton).

M4 ships a working skeleton: a QDialog with a stacked widget holding
three pages (Input / Action / Save). The Input page shows the captured
control; the Action page lets the user pick keyboard/media/builtin/
script/plugin and fill in the right form; the Save page asks for a
mapping id and optional description.

The full key-capture widget (which uses pynput.keyboard.Listener to
record a physical key combo) lands in M5; for M4 the keyboard form
accepts a string like ``ctrl+shift+k`` and parses it on save.

What the dialog returns
-----------------------
The dialog returns a :class:`Mapping`-shaped dict when the user
clicks Save. The caller (profile editor) decides how to merge it
into the live :class:`Profile`.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...events import NormalizedEvent
from ...plugins.registry import get_registry
from ...profile.schema import (
    BuiltinAction,
    InputSpec,
    KeyboardAction,
    Mapping,
    MediaAction,
    PluginAction,
    ScriptAction,
)

log = logging.getLogger(__name__)


# (display, builtin_name, param_widget_factory_or_None)
_BUILTIN_CHOICES = [
    ("(none)", None, None),
    ("Volume set (0-100)", "volume_set", "volume_set_params"),
    ("Volume up", "volume_up", None),
    ("Volume down", "volume_down", None),
    ("Volume mute toggle", "volume_mute", None),
    ("Open URL…", "open_url", "url_params"),
    ("Launch app…", "launch_app", "path_params"),
    ("No-op (testing)", "noop", None),
]

_MEDIA_KEYS = ["play_pause", "next", "prev", "stop", "volume_up", "volume_down", "mute"]


class BindControlDialog(QDialog):
    """Capture a (control, action) pair and return it as a Mapping."""

    def __init__(
        self,
        initial_event: NormalizedEvent | None = None,
        parent=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bind this control")
        self.setModal(True)
        self.resize(560, 480)

        self._event = initial_event
        self._pages = QStackedWidget(self)
        self._input_page = self._build_input_page()
        self._action_page = self._build_action_page()
        self._save_page = self._build_save_page()
        self._pages.addWidget(self._input_page)  # 0
        self._pages.addWidget(self._action_page)  # 1
        self._pages.addWidget(self._save_page)    # 2

        nav = QDialogButtonBox(self)
        self._back_btn = nav.addButton("Back", QDialogButtonBox.ButtonRole.ActionRole)
        self._next_btn = nav.addButton("Next", QDialogButtonBox.ButtonRole.ActionRole)
        self._save_btn = nav.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
        nav.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn.clicked.connect(self._go_next)
        self._save_btn.clicked.connect(self._save)
        nav.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._pages)
        layout.addWidget(nav)
        self._refresh_nav()

    # ---- pages ----

    def _build_input_page(self) -> QWidget:
        w = QWidget(self)
        layout = QFormLayout(w)
        self._device_label = QLabel("", w)
        self._control_label = QLabel("", w)
        self._event_label = QLabel("", w)
        layout.addRow("Device:", self._device_label)
        layout.addRow("Control:", self._control_label)
        layout.addRow("Last event:", self._event_label)
        self._event_filter_combo = QComboBox(w)
        self._event_filter_combo.addItems(["any", "press", "release", "change"])
        layout.addRow("Trigger on:", self._event_filter_combo)
        self._value_min = QSpinBox(w)
        self._value_min.setRange(0, 16383)
        self._value_max = QSpinBox(w)
        self._value_max.setRange(0, 16383)
        self._value_max.setValue(16383)
        layout.addRow("Value min (>=):", self._value_min)
        layout.addRow("Value max (<=):", self._value_max)
        if self._event is not None:
            self._apply_event(self._event)
        return w

    def _build_action_page(self) -> QWidget:
        w = QWidget(self)
        outer = QVBoxLayout(w)
        outer.addWidget(QLabel("Action type:"))
        self._action_type = QListWidget(w)
        for label, _kind, _params in [
            ("Keyboard chord", "keyboard", None),
            ("Media key", "media", None),
            ("Built-in action", "builtin", None),
            ("Run a script", "script", None),
            ("Plugin action", "plugin", None),
        ]:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, _kind)
            self._action_type.addItem(item)
        self._action_type.setCurrentRow(0)
        self._action_type.currentItemChanged.connect(self._on_action_type_changed)
        outer.addWidget(self._action_type)

        # Per-type form area
        self._action_form_host = QWidget(w)
        self._action_form_layout = QVBoxLayout(self._action_form_host)
        self._action_form_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._action_form_host)

        self._build_keyboard_form()
        self._build_media_form()
        self._build_builtin_form()
        self._build_script_form()
        self._build_plugin_form()
        self._show_action_form("keyboard")
        return w

    def _build_keyboard_form(self) -> None:
        w = QWidget(self._action_form_host)
        layout = QFormLayout(w)
        self._keys_edit = QLineEdit(w)
        self._keys_edit.setPlaceholderText("e.g. ctrl+shift+k, ctrl+1, F5, a")
        layout.addRow("Keys (comma-separated):", self._keys_edit)
        self._keyboard_page = w
    def _build_media_form(self) -> None:
        w = QWidget(self._action_form_host)
        layout = QFormLayout(w)
        self._media_combo = QComboBox(w)
        self._media_combo.addItems(_MEDIA_KEYS)
        layout.addRow("Media key:", self._media_combo)
        self._media_page = w

    def _build_builtin_form(self) -> None:
        w = QWidget(self._action_form_host)
        layout = QFormLayout(w)
        self._builtin_combo = QComboBox(w)
        for label, name, params_hint in _BUILTIN_CHOICES:
            self._builtin_combo.addItem(label, (name, params_hint))
        self._builtin_combo.currentIndexChanged.connect(self._on_builtin_changed)
        layout.addRow("Built-in:", self._builtin_combo)
        self._builtin_params_label = QLabel("Params:", w)
        self._builtin_params_edit = QLineEdit(w)
        self._builtin_params_edit.setPlaceholderText("JSON object, e.g. {\"value\": 50}")
        layout.addRow(self._builtin_params_label, self._builtin_params_edit)
        self._builtin_page = w

    def _build_script_form(self) -> None:
        w = QWidget(self._action_form_host)
        layout = QFormLayout(w)
        self._script_cmd_edit = QLineEdit(w)
        self._script_cmd_edit.setPlaceholderText("e.g. python,C:\\path\\to\\script.py,$value")
        layout.addRow("Command (comma-separated):", self._script_cmd_edit)
        self._script_timeout = QSpinBox(w)
        self._script_timeout.setRange(1, 600)
        self._script_timeout.setValue(30)
        layout.addRow("Timeout (s):", self._script_timeout)
        self._script_risky = QComboBox(w)
        self._script_risky.addItems(["safe", "risky (asks confirmation)"])
        layout.addRow("Safety:", self._script_risky)
        self._script_cwd_edit = QLineEdit(w)
        self._script_cwd_edit.setPlaceholderText("(optional, defaults to home)")
        layout.addRow("Working dir:", self._script_cwd_edit)
        self._script_page = w

    def _build_plugin_form(self) -> None:
        w = QWidget(self._action_form_host)
        layout = QFormLayout(w)
        self._plugin_combo = QComboBox(w)
        registry = get_registry()
        names = registry.names()
        if names:
            for name in names:
                self._plugin_combo.addItem(name, name)
        else:
            self._plugin_combo.addItem("(no plugins registered)", None)
            self._plugin_combo.setEnabled(False)
        layout.addRow("Plugin:", self._plugin_combo)
        self._plugin_params_edit = QLineEdit(w)
        self._plugin_params_edit.setPlaceholderText('JSON object, e.g. {"text": "hello"}')
        layout.addRow("Parameters:", self._plugin_params_edit)
        self._plugin_page = w

    def _build_save_page(self) -> QWidget:
        w = QWidget(self)
        layout = QFormLayout(w)
        self._mapping_id_edit = QLineEdit(w)
        self._mapping_id_edit.setPlaceholderText("auto-generated if empty")
        layout.addRow("Mapping id:", self._mapping_id_edit)
        self._description_edit = QLineEdit(w)
        layout.addRow("Description:", self._description_edit)
        self._summary_label = QLabel("", w)
        self._summary_label.setWordWrap(True)
        layout.addRow("Summary:", self._summary_label)
        return w

    # ---- navigation ----

    def _refresh_nav(self) -> None:
        idx = self._pages.currentIndex()
        self._back_btn.setEnabled(idx > 0)
        self._next_btn.setEnabled(idx < 2)
        self._save_btn.setEnabled(idx == 2)
        if idx == 2:
            self._refresh_summary()

    def _go_back(self) -> None:
        self._pages.setCurrentIndex(self._pages.currentIndex() - 1)
        self._refresh_nav()

    def _go_next(self) -> None:
        self._pages.setCurrentIndex(self._pages.currentIndex() + 1)
        self._refresh_nav()

    def _save(self) -> None:
        try:
            mapping = self._build_mapping()
        except Exception as e:
            log.exception("failed to build mapping")
            # Don't show a modal in headless / test contexts — the
            # caller (or test) can inspect built_mapping() / result().
            self._built_mapping = None
            self._last_error = str(e)
            self.reject()
            return
        self._built_mapping = mapping
        self._last_error = None
        self.accept()

    def _on_action_type_changed(self) -> None:
        item = self._action_type.currentItem()
        if item is None:
            return
        kind = item.data(Qt.UserRole)
        self._show_action_form(kind)

    def _show_action_form(self, kind: str) -> None:
        # Hide all, show one
        for page in (
            self._keyboard_page,
            self._media_page,
            self._builtin_page,
            self._script_page,
            self._plugin_page,
        ):
            page.setParent(None)  # remove from layout
        target = {
            "keyboard": self._keyboard_page,
            "media": self._media_page,
            "builtin": self._builtin_page,
            "script": self._script_page,
            "plugin": self._plugin_page,
        }[kind]
        self._action_form_layout.addWidget(target)

    def _on_builtin_changed(self) -> None:
        data = self._builtin_combo.currentData()
        if not data:
            return
        _name, params_hint = data
        if params_hint == "volume_set_params":
            self._builtin_params_edit.setText('{"value": $value}')
        elif params_hint == "url_params":
            self._builtin_params_edit.setText('{"url": "https://example.com"}')
        elif params_hint == "path_params":
            self._builtin_params_edit.setText('{"path": "C:/Windows/notepad.exe"}')
        else:
            self._builtin_params_edit.clear()

    def _apply_event(self, ev: NormalizedEvent) -> None:
        self._device_label.setText(ev.device_id)
        self._control_label.setText(ev.control_id)
        self._event_label.setText(f"{ev.event_type.value} value={int(ev.value)} ts={ev.timestamp_ms}")
        # Default the event-type filter to the captured event
        idx = self._event_filter_combo.findText(ev.event_type.value)
        if idx >= 0:
            self._event_filter_combo.setCurrentIndex(idx)

    def set_event(self, ev: NormalizedEvent) -> None:
        self._event = ev
        self._apply_event(ev)

    def _build_action_obj(
        self,
    ) -> KeyboardAction | MediaAction | BuiltinAction | ScriptAction | PluginAction:
        kind = self._action_type.currentItem().data(Qt.UserRole)
        if kind == "keyboard":
            raw = self._keys_edit.text()
            # Accept both "ctrl,shift,k" and "ctrl+shift+k" as a single
            # chord. Per-chord split on ',', per-combo split on '+'.
            keys: list[str] = []
            for chunk in raw.split(","):
                parts = [p.strip().lower() for p in chunk.split("+") if p.strip()]
                keys.extend(parts)
            if not keys:
                raise ValueError("at least one key is required")
            return KeyboardAction(keys=keys)
        if kind == "media":
            return MediaAction(key=self._media_combo.currentText())
        if kind == "builtin":
            name, _ = self._builtin_combo.currentData()
            params_text = self._builtin_params_edit.text().strip()
            params: dict[str, Any] = {}
            if params_text:
                import json

                try:
                    params = json.loads(params_text)
                except json.JSONDecodeError as e:
                    raise ValueError(f"params must be valid JSON: {e}") from e
            return BuiltinAction(name=name, params=params)
        if kind == "script":
            cmd = [c.strip() for c in self._script_cmd_edit.text().split(",") if c.strip()]
            if not cmd:
                raise ValueError("script command is required")
            return ScriptAction(
                command=cmd,
                timeout_s=float(self._script_timeout.value()),
                risky=self._script_risky.currentIndex() == 1,
                cwd=self._script_cwd_edit.text().strip() or None,
            )
        if kind == "plugin":
            name = self._plugin_combo.currentData()
            if not name:
                raise ValueError("no plugins are registered; install a 'midimap.plugins' entry point")
            params_text = self._plugin_params_edit.text().strip()
            params: dict[str, Any] = {}
            if params_text:
                import json

                try:
                    params = json.loads(params_text)
                except json.JSONDecodeError as e:
                    raise ValueError(f"plugin parameters must be valid JSON: {e}") from e
                if not isinstance(params, dict):
                    raise ValueError("plugin parameters must be a JSON object")
            return PluginAction(name=name, params=params)
        raise ValueError(f"unsupported action type: {kind}")

    def _build_mapping(self) -> Mapping:
        spec = InputSpec(
            control=self._control_label.text() or "",
            event=self._event_filter_combo.currentText() if self._event_filter_combo.currentText() != "any" else None,
            value_min=self._value_min.value() or None,
            value_max=self._value_max.value() if self._value_max.value() < 16383 else None,
        )
        action = self._build_action_obj()
        import uuid

        mid = self._mapping_id_edit.text().strip() or f"m_{uuid.uuid4().hex[:8]}"
        return Mapping(
            id=mid,
            input=spec,
            action=action,
            description=self._description_edit.text().strip() or None,
        )

    def _refresh_summary(self) -> None:
        try:
            m = self._build_mapping()
        except Exception as e:
            self._summary_label.setText(f"<i>Error: {e}</i>")
            return
        self._summary_label.setText(f"<code>{m.id}</code> on <b>{m.input.control}</b> → {m.action.type}")

    def built_mapping(self) -> Mapping | None:
        return getattr(self, "_built_mapping", None)


__all__ = ["BindControlDialog"]
