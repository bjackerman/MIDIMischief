"""End-to-end tests for M3 action types (media, builtin, script) through
the full App stack with mocked backends."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from midimap.app import App
from midimap.events import EventType, NormalizedEvent, Value
from midimap.profile.schema import (
    BuiltinAction,
    InputSpec,
    Layer,
    Mapping,
    MediaAction,
    Profile,
    ScriptAction,
)


def _profile(mappings: list[Mapping]) -> Profile:
    return Profile(layers={0: Layer(mappings=mappings)})


def _ev(ctrl: str, et: EventType, val: int = 100, ts: int = 0) -> NormalizedEvent:
    return NormalizedEvent(
        device_id="midi:fake",
        control_id=ctrl,
        event_type=et,
        value=Value(val),
        timestamp_ms=ts,
    )


@patch("pynput.keyboard.Controller")
def test_e2e_script_action_dispatched(mock_cls):
    with patch("midimap.actions.script.subprocess.Popen") as popen_cls:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.wait.return_value = 0
        popen_cls.return_value = proc
        mock_cls.return_value = MagicMock()

        prof = _profile(
            [
                Mapping(
                    id="script1",
                    input=InputSpec(control="note:60", event="press"),
                    action=ScriptAction(command=["python", "-V"]),
                )
            ]
        )
        app = App(prof, dry_run=False, auto_connect=False)
        app.devices.start()
        app.feed(_ev("note:60", EventType.PRESS, val=100))
        time.sleep(0.1)
        app.stop()
        # Popen was called
        assert popen_cls.called
        # argv was the script command
        assert popen_cls.call_args.args[0] == ["python", "-V"]
        # env includes MIDIMAP_EVENT
        env = popen_cls.call_args.kwargs["env"]
        assert "MIDIMAP_EVENT" in env


@patch("pynput.keyboard.Controller")
def test_e2e_script_template_substitution(mock_cls):
    """$value in a script arg must be substituted with the event's value."""
    with patch("midimap.actions.script.subprocess.Popen") as popen_cls:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.wait.return_value = 0
        popen_cls.return_value = proc
        mock_cls.return_value = MagicMock()

        prof = _profile(
            [
                Mapping(
                    id="script_with_value",
                    input=InputSpec(control="cc:1", event="change"),
                    action=ScriptAction(command=["logger", "$value"]),
                )
            ]
        )
        app = App(prof, dry_run=False, auto_connect=False)
        app.devices.start()
        app.feed(_ev("cc:1", EventType.CHANGE, val=73))
        time.sleep(0.1)
        app.stop()
        argv = popen_cls.call_args.args[0]
        assert argv == ["logger", "73"]


@patch("pynput.keyboard.Controller")
def test_e2e_no_scripts_flag_hard_disables(mock_cls):
    with patch("midimap.actions.script.subprocess.Popen") as popen_cls:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.wait.return_value = 0
        popen_cls.return_value = proc
        mock_cls.return_value = MagicMock()

        prof = _profile(
            [
                Mapping(
                    id="script1",
                    input=InputSpec(control="note:60"),
                    action=ScriptAction(command=["rm", "-rf", "/"]),
                )
            ]
        )
        app = App(prof, dry_run=False, auto_connect=False, scripts_enabled=False)
        app.devices.start()
        app.feed(_ev("note:60", EventType.PRESS))
        time.sleep(0.1)
        app.stop()
        popen_cls.assert_not_called()


@patch("pynput.keyboard.Controller")
def test_e2e_builtin_volume_dry_run(mock_cls, caplog):
    """In dry-run, builtin should log but not call any backend."""
    import logging
    caplog.set_level(logging.INFO, logger="midimap.actions.builtin")
    mock_cls.return_value = MagicMock()

    prof = _profile(
        [
            Mapping(
                id="vol",
                input=InputSpec(control="cc:1", event="change"),
                action=BuiltinAction(name="volume_set", params={"value": "$value"}),
            )
        ]
    )
    app = App(prof, dry_run=True, auto_connect=False)
    app.devices.start()
    app.feed(_ev("cc:1", EventType.CHANGE, val=42))
    time.sleep(0.1)
    app.stop()
    # The dry-run log should mention volume_set: 42%
    assert any("volume_set" in r.message and "42" in r.message for r in caplog.records)


@patch("pynput.keyboard.Controller")
def test_e2e_media_key_dry_run(mock_cls, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="midimap.actions.media")
    mock_cls.return_value = MagicMock()

    prof = _profile(
        [
            Mapping(
                id="play",
                input=InputSpec(control="note:60"),
                action=MediaAction(key="play_pause"),
            )
        ]
    )
    app = App(prof, dry_run=True, auto_connect=False)
    app.devices.start()
    app.feed(_ev("note:60", EventType.PRESS))
    time.sleep(0.1)
    app.stop()
    assert any("play_pause" in r.message for r in caplog.records)


@patch("pynput.keyboard.Controller")
def test_e2e_profile_global_settings_disable_scripts(mock_cls):
    with patch("midimap.actions.script.subprocess.Popen") as popen_cls:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.wait.return_value = 0
        popen_cls.return_value = proc
        mock_cls.return_value = MagicMock()

        # Profile with global_settings.disable_scripts = true
        prof = Profile(
            global_settings={"disable_scripts": True},
            layers={
                0: Layer(
                    mappings=[
                        Mapping(
                            id="x",
                            input=InputSpec(control="note:60"),
                            action=ScriptAction(command=["rm", "-rf", "/"]),
                        )
                    ]
                )
            },
        )
        # Note: we pass scripts_enabled=None to use the profile's value
        app = App(prof, dry_run=False, auto_connect=False, scripts_enabled=None)
        app.devices.start()
        app.feed(_ev("note:60", EventType.PRESS))
        time.sleep(0.1)
        app.stop()
        popen_cls.assert_not_called()


@patch("pynput.keyboard.Controller")
def test_e2e_risky_script_requires_confirm_then_runs(mock_cls):
    """Risky scripts must go through the confirm callback the first time."""
    with patch("midimap.actions.script.subprocess.Popen") as popen_cls:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.wait.return_value = 0
        popen_cls.return_value = proc
        mock_cls.return_value = MagicMock()

        confirms: list[str] = []
        def cb(d: str) -> bool:
            confirms.append(d)
            return True

        prof = _profile(
            [
                Mapping(
                    id="risky",
                    input=InputSpec(control="note:60"),
                    action=ScriptAction(command=["rm", "-rf", "/"], risky=True),
                )
            ]
        )
        app = App(
            prof,
            dry_run=False,
            auto_connect=False,
            confirm_callback=cb,
            confirm_risky=True,
        )
        app.devices.start()
        app.feed(_ev("note:60", EventType.PRESS))
        time.sleep(0.1)
        app.feed(_ev("note:60", EventType.PRESS))
        time.sleep(0.1)
        app.stop()

        # Confirm was called once (remembered after first approval)
        assert len(confirms) == 1
        # Script ran both times
        assert popen_cls.call_count == 2


@patch("pynput.keyboard.Controller")
def test_e2e_risky_script_declined_does_not_run(mock_cls):
    with patch("midimap.actions.script.subprocess.Popen") as popen_cls:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.wait.return_value = 0
        popen_cls.return_value = proc
        mock_cls.return_value = MagicMock()

        def cb(d: str) -> bool:
            return False  # user always declines

        prof = _profile(
            [
                Mapping(
                    id="risky",
                    input=InputSpec(control="note:60"),
                    action=ScriptAction(command=["dangerous"], risky=True),
                )
            ]
        )
        app = App(prof, dry_run=False, auto_connect=False, confirm_callback=cb, confirm_risky=True)
        app.devices.start()
        app.feed(_ev("note:60", EventType.PRESS))
        time.sleep(0.1)
        app.stop()
        popen_cls.assert_not_called()
