"""Tests for ScriptRunner.

We mock ``subprocess.Popen`` so these tests don't actually spawn
processes. The mock simulates the exit code, stdout output, and timeout
behaviour we need to exercise.
"""

from __future__ import annotations

import subprocess
import time
from unittest.mock import MagicMock, patch

from midimap.actions.script import ScriptRunner
from midimap.events import EventType, NormalizedEvent, Value


def _ev(control: str = "cc:1", value: int = 42) -> NormalizedEvent:
    return NormalizedEvent(
        device_id="midi:test",
        control_id=control,
        event_type=EventType.CHANGE,
        value=Value(value),
        velocity=90,
        channel=1,
        timestamp_ms=0,
    )


def _script_params(command: list[str], **overrides) -> dict:
    p = {"command": command, "timeout_s": 5.0, "risky": False}
    p.update(overrides)
    return p


def _mock_popen(stdout_text: str = "", returncode: int = 0, timeout: bool = False):
    """Return a configured MagicMock that pretends to be Popen.

    timeout=True makes proc.wait(timeout=...) raise TimeoutExpired once.
    """
    proc = MagicMock()
    proc.stdout = iter(stdout_text.splitlines(keepends=True)) if stdout_text else iter([])
    proc.wait = MagicMock(return_value=returncode)
    if timeout:
        # First call: TimeoutExpired. Second call: returncode.
        proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="x", timeout=0.01),
            returncode,
        ]
    return proc


# --- empty / disabled ---


def test_empty_command_skips():
    r = ScriptRunner()
    assert r.run({"command": []}, event=_ev()) is False


def test_disabled_runner_skips():
    r = ScriptRunner(enabled=False)
    assert r.run(_script_params(["echo", "hi"]), event=_ev()) is False


# --- happy path ---


@patch("midimap.actions.script.subprocess.Popen")
def test_happy_path_returns_true(mock_cls):
    proc = _mock_popen(stdout_text="hello\nworld\n", returncode=0)
    mock_cls.return_value = proc
    r = ScriptRunner()
    ok = r.run(_script_params(["echo", "hi"]), event=_ev())
    assert ok is True
    # Popen was called with shell=False and an argv list
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["shell"] is False
    assert mock_cls.call_args.args[0] == ["echo", "hi"]


@patch("midimap.actions.script.subprocess.Popen")
def test_non_zero_exit_returns_false(mock_cls):
    proc = _mock_popen(returncode=2)
    mock_cls.return_value = proc
    r = ScriptRunner()
    assert r.run(_script_params(["false"]), event=_ev()) is False


# --- env handling ---


@patch("midimap.actions.script.subprocess.Popen")
def test_midimap_event_env_var_set(mock_cls):
    proc = _mock_popen(returncode=0)
    mock_cls.return_value = proc
    r = ScriptRunner()
    r.run(_script_params(["python", "-V"]), event=_ev(value=64))
    env = mock_cls.call_args.kwargs["env"]
    assert "MIDIMAP_EVENT" in env
    import json
    payload = json.loads(env["MIDIMAP_EVENT"])
    assert payload["control"] == "cc:1"
    assert payload["value"] == 64
    assert payload["event"] == "change"


@patch("midimap.actions.script.subprocess.Popen")
def test_user_env_overrides_midimap_event(mock_cls):
    proc = _mock_popen(returncode=0)
    mock_cls.return_value = proc
    r = ScriptRunner()
    r.run(
        _script_params(["x"], env={"MIDIMAP_EVENT": "user-set"}),
        event=_ev(),
    )
    env = mock_cls.call_args.kwargs["env"]
    assert env["MIDIMAP_EVENT"] == "user-set"


@patch("midimap.actions.script.subprocess.Popen")
def test_cwd_and_user_env_merged_with_os_environ(mock_cls):
    proc = _mock_popen(returncode=0)
    mock_cls.return_value = proc
    r = ScriptRunner()
    with patch.dict("os.environ", {"FOO": "bar"}):
        r.run(
            _script_params(["x"], cwd="/tmp", env={"BAR": "baz"}),
            event=None,
        )
    env = mock_cls.call_args.kwargs["env"]
    cwd = mock_cls.call_args.kwargs["cwd"]
    assert env["FOO"] == "bar"
    assert env["BAR"] == "baz"
    assert cwd == "/tmp"


# --- risky ---


def test_risky_requires_confirm_and_can_be_declined():
    r = ScriptRunner(confirm_callback=lambda _d: False)
    assert r.run(_script_params(["rm", "-rf", "/"], risky=True), event=_ev()) is False


def test_risky_remembered_after_first_confirm():
    calls: list[str] = []
    def cb(d: str) -> bool:
        calls.append(d)
        return True
    r = ScriptRunner(confirm_callback=cb)
    p = _script_params(["rm", "-rf", "/"], risky=True)
    with patch("midimap.actions.script.subprocess.Popen") as mock_cls:
        mock_cls.return_value = _mock_popen(returncode=0)
        r.run(p, event=_ev())
        # Same args again — should not re-prompt.
        r.run(p, event=_ev())
    assert len(calls) == 1


def test_risky_disabled_by_confirm_risky_false():
    """If confirm_risky is False, risky scripts run without prompting."""
    r = ScriptRunner(confirm_callback=lambda _d: (_ for _ in ()).throw(AssertionError("should not be called")),
                     confirm_risky=False)
    with patch("midimap.actions.script.subprocess.Popen") as mock_cls:
        mock_cls.return_value = _mock_popen(returncode=0)
        assert r.run(_script_params(["dangerous"], risky=True), event=_ev()) is True


# --- timeout ---


@patch("midimap.actions.script.subprocess.Popen")
def test_timeout_kills_via_terminate(mock_cls):
    proc = MagicMock()
    proc.stdout = iter([])
    # First wait: TimeoutExpired. Second wait: returncode=0 (after SIGTERM).
    proc.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="x", timeout=0.01),
        0,
    ]
    mock_cls.return_value = proc
    r = ScriptRunner()
    assert r.run(_script_params(["sleep", "99"], timeout_s=0.01), event=_ev()) is False
    # terminate was called
    proc.terminate.assert_called()


@patch("midimap.actions.script.subprocess.Popen")
def test_timeout_kills_via_kill_if_terminate_ignored(mock_cls):
    proc = MagicMock()
    proc.stdout = iter([])
    proc.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="x", timeout=0.01),  # initial
        subprocess.TimeoutExpired(cmd="x", timeout=0.01),  # grace period
        0,  # after kill
    ]
    mock_cls.return_value = proc
    r = ScriptRunner()
    assert r.run(_script_params(["sleep", "99"], timeout_s=0.01), event=_ev()) is False
    proc.terminate.assert_called()
    proc.kill.assert_called()


# --- error paths ---


@patch("midimap.actions.script.subprocess.Popen")
def test_file_not_found_returns_false(mock_cls):
    mock_cls.side_effect = FileNotFoundError("not on PATH")
    r = ScriptRunner()
    assert r.run(_script_params(["does-not-exist"]), event=_ev()) is False


@patch("midimap.actions.script.subprocess.Popen")
def test_oserror_returns_false(mock_cls):
    mock_cls.side_effect = OSError("permission denied")
    r = ScriptRunner()
    assert r.run(_script_params(["/root/secret"]), event=_ev()) is False


# --- dry run ---


@patch("midimap.actions.script.subprocess.Popen")
def test_dry_run_does_not_spawn(mock_cls):
    r = ScriptRunner(dry_run=True)
    assert r.run(_script_params(["echo", "hi"]), event=_ev()) is True
    mock_cls.assert_not_called()


# --- output capture ---


@patch("midimap.actions.script.subprocess.Popen")
def test_stdout_captured_to_tail(mock_cls):
    proc = MagicMock()
    lines = ["line1\n", "line2\n", "line3\n"]
    proc.stdout = iter(lines)
    proc.wait.returnvalue = 0
    mock_cls.return_value = proc
    r = ScriptRunner()
    r.run(_script_params(["echo"]), event=_ev())
    # Drain thread must finish; give it a moment.
    time.sleep(0.2)
    assert "line1" in r.tail()
    assert "line3" in r.tail()
