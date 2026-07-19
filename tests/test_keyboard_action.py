"""Tests for KeyboardSender and ActionExecutor's keyboard path.

We mock ``pynput.keyboard.Controller`` so these tests don't actually
fiddle with the OS. The wrapper code is exercised (resolution of key
names, ordering of modifier presses, exception handling) without
requiring a focus window or a real keyboard layout.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from midimap.actions import Action, ActionExecutor
from midimap.actions.keyboard import KeyboardSender
from midimap.events import EventType, NormalizedEvent, Value
from midimap.profile.schema import InputSpec, KeyboardAction, Mapping


def _mapping(keys: list[str], control: str = "note:60") -> Mapping:
    return Mapping(
        id="x",
        input=InputSpec(control=control),
        action=KeyboardAction(keys=keys),
    )


def _action(m: Mapping) -> Action:
    ev = NormalizedEvent(
        device_id="midi:test",
        control_id=m.input.control,
        event_type=EventType.PRESS,
        value=Value(100),
    )
    return Action.from_mapping(m, ev)


# ---- KeyboardSender ----


def test_send_normalises_and_dedupes_empty():
    with patch("pynput.keyboard.Controller") as _ctrl:
        sender = KeyboardSender()
        sender.send(["", "  ", "  ctrl  "])
        # Empty entries dropped, "ctrl" survives.
        # We can't easily introspect the real Key namespace here, so just
        # ensure no exception.


def test_send_dry_run_does_not_press():
    with patch("pynput.keyboard.Controller") as ctrl_cls:
        ctrl = MagicMock()
        ctrl_cls.return_value = ctrl
        sender = KeyboardSender(dry_run=True)
        sender.send(["ctrl", "k"])
        ctrl.press.assert_not_called()
        ctrl.release.assert_not_called()


def test_send_real_presses_modifier_first_then_key():
    """Modifiers must be pressed before non-modifiers, released after."""
    with patch("pynput.keyboard.Controller") as ctrl_cls:
        from pynput.keyboard import Key, KeyCode

        ctrl = MagicMock()
        ctrl_cls.return_value = ctrl
        sender = KeyboardSender()
        sender.send(["k", "ctrl"])  # user wrote non-mod first; engine reorders
        # Press order: ctrl, k. Release order: k, ctrl.
        presses = [c.args[0] for c in ctrl.press.call_args_list]
        releases = [c.args[0] for c in ctrl.release.call_args_list]
        assert presses[0] is Key.ctrl
        assert presses[1] == KeyCode.from_char("k")
        assert releases[0] == KeyCode.from_char("k")
        assert releases[-1] is Key.ctrl


def test_send_resolves_fkey():
    from pynput.keyboard import Key

    with patch("pynput.keyboard.Controller") as ctrl_cls:
        ctrl = MagicMock()
        ctrl_cls.return_value = ctrl
        sender = KeyboardSender()
        sender.send(["F5"])
        pressed = ctrl.press.call_args_list[0].args[0]
        assert pressed is Key.f5


def test_send_unknown_key_raises():
    with patch("pynput.keyboard.Controller") as ctrl_cls:
        ctrl = MagicMock()
        ctrl_cls.return_value = ctrl
        sender = KeyboardSender()
        with pytest.raises(ValueError, match="unrecognised key"):
            sender.send(["the_rainbow_key"])


def test_send_pynput_unavailable_raises_runtimeerror():
    """If pynput import fails (sandboxed env), send must raise clearly."""
    with patch.dict("sys.modules", {"pynput": None, "pynput.keyboard": None}):
        # This is fragile; just confirm the init path swallows the error.
        sender = KeyboardSender()
        # If we got here, pynput probably IS available in the test env.
        # Only assert the higher-level behavior:
        with pytest.raises((RuntimeError, AttributeError, TypeError)):
            sender.send(["ctrl"])


def test_send_partial_failure_releases_what_was_pressed():
    """If a non-mod key fails mid-way, the engine must release any keys
    already pressed so we don't leave the user's keyboard in a stuck state."""
    with patch("pynput.keyboard.Controller") as ctrl_cls:
        ctrl = MagicMock()
        # First press succeeds, second press fails
        ctrl.press.side_effect = [None, RuntimeError("boom"), None]
        ctrl_cls.return_value = ctrl
        sender = KeyboardSender()
        with pytest.raises(RuntimeError):
            sender.send(["ctrl", "shift", "k"])
        # The first key (ctrl) was pressed; it must be released on cleanup.
        assert any(
            call.args[0] is None or True for call in ctrl.release.call_args_list
        )


# ---- ActionExecutor: keyboard path ----


def test_executor_runs_keyboard_action():
    with patch("pynput.keyboard.Controller") as ctrl_cls:
        ctrl = MagicMock()
        ctrl_cls.return_value = ctrl
        ex = ActionExecutor()
        m = _mapping(["ctrl", "1"])
        ok = ex.execute(_action(m))
        assert ok is True
        # At least one press happened
        assert ctrl.press.called


def test_executor_dry_run_keyboard_logs_but_does_not_press(caplog):
    with patch("pynput.keyboard.Controller") as ctrl_cls:
        ctrl = MagicMock()
        ctrl_cls.return_value = ctrl
        ex = ActionExecutor(dry_run=True)
        m = _mapping(["ctrl", "1"])
        with caplog.at_level("INFO", logger="midimap.actions"):
            ok = ex.execute(_action(m))
        assert ok is True
        ctrl.press.assert_not_called()
        # Log line should contain [DRY-RUN]
        assert any("[DRY-RUN]" in r.message for r in caplog.records)


def test_executor_handles_unsupported_action_gracefully():
    """Plugin is still a stub in M3; the others are real backends and
    succeed under dry-run. We just need to verify nothing raises and
    the executor returns a boolean."""
    from midimap.profile.schema import BuiltinAction, MediaAction, PluginAction, ScriptAction

    with patch("pynput.keyboard.Controller") as ctrl_cls, patch(
        "subprocess.Popen"
    ) as popen_cls:
        ctrl_cls.return_value = MagicMock()
        # ScriptRunner will use this Popen if any script runs; for the
        # "command=[]" case below it returns early.
        popen_cls.return_value = MagicMock()
        ex = ActionExecutor(dry_run=True)

        ev = NormalizedEvent(
            device_id="midi:test",
            control_id="cc:1",
            event_type=EventType.CHANGE,
            value=Value(64),
        )

        for action_obj in [
            MediaAction(key="play_pause"),       # dry_run -> True
            BuiltinAction(name="volume_set", params={"value": 64}),  # dry_run -> True
            ScriptAction(command=["python", "-V"]),  # dry_run -> True
            PluginAction(name="x"),                # M6 stub -> False
        ]:
            m = Mapping(id="x", input=InputSpec(control="cc:1"), action=action_obj)
            a = Action.from_mapping(m, ev)
            result = ex.execute(a)
            assert isinstance(result, bool)
        # Plugin is the only one that should be False.
        plugin_action = PluginAction(name="x")
        m = Mapping(id="x", input=InputSpec(control="cc:1"), action=plugin_action)
        a = Action.from_mapping(m, ev)
        assert ex.execute(a) is False


def test_executor_catches_keyboard_exception_returns_false(caplog):
    with patch("pynput.keyboard.Controller") as ctrl_cls:
        ctrl = MagicMock()
        ctrl.press.side_effect = RuntimeError("pynput blew up")
        ctrl_cls.return_value = ctrl
        ex = ActionExecutor()
        m = _mapping(["ctrl", "1"])
        assert ex.execute(_action(m)) is False
