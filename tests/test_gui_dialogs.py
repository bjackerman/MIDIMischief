"""Tests for the binding wizard + learn-mode dialog."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from midimap.events import EventType, NormalizedEvent, Value
from midimap.gui.dialogs.bind_control import _BUILTIN_CHOICES, BindControlDialog
from midimap.gui.dialogs.learn_mode import LearnModeDialog
from midimap.gui.qt_bridge import EventBusQtBridge
from midimap.profile.schema import (
    BuiltinAction,
    InputSpec,
    Mapping,
    PluginAction,
    ScriptAction,
)


def _ev() -> NormalizedEvent:
    return NormalizedEvent(
        device_id="midi:t",
        control_id="note:60",
        event_type=EventType.PRESS,
        value=Value(100),
        timestamp_ms=0,
    )


def test_bind_dialog_keyboard_walkthrough(qapp):  # type: ignore[no-untyped-def]
    dlg = BindControlDialog(initial_event=_ev())
    qapp.processEvents()
    dlg._keys_edit.setText("ctrl+shift+k")
    # Advance to action page (already there on construct)
    dlg._go_next()  # type: ignore[no-untyped-def]
    # Already on action page now; next -> save
    dlg._go_next()  # type: ignore[no-untyped-def]
    dlg._mapping_id_edit.setText("test_kbd")
    dlg._save()  # type: ignore[no-untyped-def]
    assert dlg.result() == dlg.DialogCode.Accepted
    m = dlg.built_mapping()
    assert m is not None
    assert m.id == "test_kbd"
    assert m.input.control == "note:60"
    assert m.action.type == "keyboard"
    assert m.action.keys == ["ctrl", "shift", "k"]


def test_bind_dialog_script_walkthrough(qapp):  # type: ignore[no-untyped-def]
    dlg = BindControlDialog(initial_event=_ev())
    qapp.processEvents()
    # Action type index 3 = "Run a script"
    dlg._action_type.setCurrentRow(3)
    dlg._script_cmd_edit.setText("echo,hello")
    dlg._script_risky.setCurrentIndex(1)
    dlg._go_next()  # type: ignore[no-untyped-def]
    dlg._mapping_id_edit.setText("script_test")
    dlg._save()  # type: ignore[no-untyped-def]
    m = dlg.built_mapping()
    assert m is not None
    assert m.action.type == "script"
    assert m.action.command == ["echo", "hello"]
    assert m.action.risky is True


def test_builtin_choices_exclude_unsupported_process_termination():
    names = {name for _label, name, _params_hint in _BUILTIN_CHOICES}
    assert "quit_app" not in names


def test_bind_dialog_missing_keys_fails_gracefully(qapp):  # type: ignore[no-untyped-def]
    dlg = BindControlDialog(initial_event=_ev())
    qapp.processEvents()
    dlg._keys_edit.setText("")
    dlg._go_next()  # type: ignore[no-untyped-def]
    dlg._go_next()  # type: ignore[no-untyped-def]
    dlg._save()  # type: ignore[no-untyped-def]
    # Build failed; result is still Rejected (default), built_mapping is None
    assert dlg.built_mapping() is None
    assert dlg.result() != dlg.DialogCode.Accepted


@pytest.mark.parametrize(
    "action",
    [
        BuiltinAction(name="volume_set", params={"value": "$value", "step": 3}),
        ScriptAction(
            command=["python", "-c", "print('hello, world')"],
            timeout_s=12.5,
            risky=True,
            cwd="/tmp/midimap",
            env={"MODE": "test", "COUNT": "2"},
        ),
        PluginAction(name="switch_workspace", params={"workspace": 2, "silent": True}),
    ],
    ids=["builtin", "script", "plugin"],
)
def test_bind_dialog_edit_and_save_preserves_action_serialization(qapp, action):  # type: ignore[no-untyped-def]
    """Editing must not discard fields that only the action form exposes."""
    original = Mapping(
        id=f"{action.type}_mapping",
        input=InputSpec(
            control="note:60",
            event="release",
            channel=4,
            value_min=0,
            value_max=127,
            min_press_ms=25,
            max_press_ms=900,
        ),
        action=action,
        description="round trip",
    )
    dlg = BindControlDialog()
    dlg.set_mapping(original)
    dlg._save()  # type: ignore[no-untyped-def]

    assert dlg.result() == dlg.DialogCode.Accepted
    edited = dlg.built_mapping()
    assert edited is not None
    assert edited.model_dump(mode="json") == original.model_dump(mode="json")


def test_learn_mode_captures_event(qapp):  # type: ignore[no-untyped-def]
    bridge = EventBusQtBridge()
    captured: list[NormalizedEvent] = []
    dlg = LearnModeDialog(bridge, timeout_ms=2000)
    dlg.event_captured.connect(captured.append)
    dlg.start()
    qapp.processEvents()
    bridge.push(_ev())
    qapp.processEvents()
    assert len(captured) == 1
    assert captured[0].control_id == "note:60"


def test_learn_mode_timeout_fires(qapp):  # type: ignore[no-untyped-def]
    """Pump Qt's event loop until the LearnMode timer fires."""
    from PySide6.QtCore import QElapsedTimer

    bridge = EventBusQtBridge()
    timed_out: list[bool] = []
    dlg = LearnModeDialog(bridge, timeout_ms=150)
    dlg.timed_out.connect(lambda: timed_out.append(True))
    dlg.start()

    # Pump the event loop for up to 1.5 seconds, checking the signal each tick.
    elapsed = QElapsedTimer()
    elapsed.start()
    while not timed_out and elapsed.elapsed() < 1500:
        qapp.processEvents()
    assert timed_out == [True]
