"""End-to-end smoke test of the M2 runtime.

Drive the real App instance with injected NormalizedEvents. Verify that
the executor fires the expected pynput calls. We mock pynput so no
keys are actually sent to the OS.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from midimap.app import App
from midimap.events import EventType, NormalizedEvent, Value
from midimap.profile.schema import (
    InputSpec,
    KeyboardAction,
    Layer,
    Mapping,
    Profile,
)


def _profile() -> Profile:
    return Profile(
        layers={
            0: Layer(
                mappings=[
                    Mapping(
                        id="pad1",
                        input=InputSpec(control="note:60", event="press"),
                        action=KeyboardAction(keys=["ctrl", "1"]),
                    ),
                    Mapping(
                        id="pad1_release",
                        input=InputSpec(control="note:60", event="release"),
                        action=KeyboardAction(keys=["enter"]),
                    ),
                ]
            )
        }
    )


def _ev(ctrl: str, et: EventType, val: int = 100, ts: int = 0) -> NormalizedEvent:
    return NormalizedEvent(
        device_id="midi:fake",
        control_id=ctrl,
        event_type=et,
        value=Value(val),
        timestamp_ms=ts,
    )


@patch("pynput.keyboard.Controller")
def test_app_dispatches_press_through_to_pynput(mock_cls):
    ctrl = MagicMock()
    mock_cls.return_value = ctrl
    app = App(_profile(), dry_run=False)
    app.feed(_ev("note:60", EventType.PRESS, ts=0))
    time.sleep(0.1)
    app.stop()
    assert ctrl.press.called


@patch("pynput.keyboard.Controller")
def test_app_dry_run_does_not_press(mock_cls):
    ctrl = MagicMock()
    mock_cls.return_value = ctrl
    app = App(_profile(), dry_run=True)
    app.feed(_ev("note:60", EventType.PRESS, ts=0))
    time.sleep(0.1)
    app.stop()
    ctrl.press.assert_not_called()


@patch("pynput.keyboard.Controller")
def test_app_release_fires_release_mapping(mock_cls):
    ctrl = MagicMock()
    mock_cls.return_value = ctrl
    app = App(_profile(), dry_run=False)
    app.feed(_ev("note:60", EventType.PRESS, ts=0))
    app.feed(_ev("note:60", EventType.RELEASE, ts=200))
    time.sleep(0.1)
    app.stop()
    # Enter was the release mapping; the second chord should press Key.enter.
    from pynput.keyboard import Key

    pressed_keys = [c.args[0] for c in ctrl.press.call_args_list]
    assert any(p is Key.enter for p in pressed_keys)


@patch("pynput.keyboard.Controller")
def test_app_unknown_event_does_nothing(mock_cls):
    ctrl = MagicMock()
    mock_cls.return_value = ctrl
    app = App(_profile(), dry_run=False)
    app.feed(_ev("note:99", EventType.PRESS, ts=0))
    time.sleep(0.1)
    app.stop()
    ctrl.press.assert_not_called()


@patch("pynput.keyboard.Controller")
def test_app_continues_after_action_failure(mock_cls):
    """A bad action must not kill the bus."""
    ctrl = MagicMock()
    ctrl.press.side_effect = [RuntimeError("first one fails"), None]
    mock_cls.return_value = ctrl
    app = App(_profile(), dry_run=False)
    app.feed(_ev("note:60", EventType.PRESS, ts=0))
    app.feed(_ev("note:60", EventType.PRESS, ts=10))  # press again
    time.sleep(0.2)
    app.stop()
    # Both presses were attempted; the second one succeeded.
    assert ctrl.press.call_count >= 2


@patch("pynput.keyboard.Controller")
def test_app_with_real_profile_fixture(mock_cls, tmp_path: Path):
    """Smoke-test using the actual sample profile shipped with the project."""
    from midimap.profile.store import load_profile

    ctrl = MagicMock()
    mock_cls.return_value = ctrl
    sample = Path(__file__).resolve().parent / "fixtures" / "sample_profile.json"
    profile = load_profile(sample)
    assert profile.layers[0].mappings, "fixture should have mappings"

    # Test a press of note:36 (pad 1 select) → Ctrl+1
    app = App(profile, dry_run=True)
    app.feed(_ev("note:36", EventType.PRESS, ts=0))
    time.sleep(0.1)
    app.stop()
    ctrl.press.assert_not_called()  # dry_run
