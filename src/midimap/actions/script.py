"""ScriptRunner — spawn a subprocess for a ScriptAction.

Security-first design
---------------------
- ``subprocess.Popen(argv, shell=False)``. The argv list is passed
  verbatim, no shell interpolation, no string→argv splitting. This is
  the single most important security property of the action layer.
- The user is in control of the command line. There's no special
  parsing, no globbing, no env expansion from midimap.
- ``risky: true`` triggers a confirmation callback (the GUI will show
  a dialog; the headless CLI defaults to "ask once per session, then
  allow for the rest of the run").
- ``MIDIMAP_EVENT`` env var is set so the script can inspect what
  triggered it. The JSON payload is small and contains no secrets.
- All stdout/stderr is captured to a bounded ring buffer (10K lines
  default). The script cannot silently spam the parent.
- Timeout: SIGTERM at ``timeout_s``, then SIGKILL after 5s grace.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shlex
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

ConfirmCallback = Callable[[str], bool]


class ScriptRunner:
    def __init__(
        self,
        *,
        confirm_callback: ConfirmCallback | None = None,
        max_log_lines: int = 10_000,
        enabled: bool = True,
        confirm_risky: bool = True,
        dry_run: bool = False,
    ) -> None:
        self._confirm = confirm_callback or (lambda _d: True)
        self._log: deque[str] = deque(maxlen=max_log_lines)
        self._confirmed_risky: set[str] = set()  # command descriptions user has approved this session
        self._enabled = enabled
        self._confirm_risky = confirm_risky
        self._dry_run = dry_run

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def set_dry_run(self, dry_run: bool) -> None:
        self._dry_run = dry_run

    def run(self, params: dict, event=None) -> bool:  # type: ignore[no-untyped-def]
        """Run a script. ``params`` is the ScriptAction.model_dump() dict,
        optionally already-template-substituted. ``event`` is the
        triggering NormalizedEvent (used to populate MIDIMAP_EVENT env)."""
        argv = list(params.get("command") or [])
        if not argv:
            log.warning("script action has empty command")
            return False

        if not self._enabled:
            log.info("scripts disabled — skipping: %s", shlex.join(argv))
            return False

        cwd = params.get("cwd") or str(Path.home())
        env_user = dict(params.get("env") or {})
        timeout = float(params.get("timeout_s", 30.0))
        risky = bool(params.get("risky", False))

        if event is not None:
            # Provide the triggering event to the script. Keep it small and
            # JSON-safe. No secrets are present in NormalizedEvent.
            env_user.setdefault(
                "MIDIMAP_EVENT",
                json.dumps(
                    {
                        "device": event.device_id,
                        "control": event.control_id,
                        "event": event.event_type.value,
                        "value": int(event.value),
                        "velocity": event.velocity,
                        "channel": event.channel,
                        "timestamp_ms": event.timestamp_ms,
                    }
                ),
            )

        desc = shlex.join(argv)

        if risky and self._confirm_risky:
            if desc not in self._confirmed_risky and not self._confirm(desc):
                log.info("user declined risky %s", desc)
                return False
            self._confirmed_risky.add(desc)

        if self._dry_run:
            log.info("[DRY-RUN] script: %s (cwd=%s, timeout=%.1fs, risky=%s)", desc, cwd, timeout, risky)
            return True

        log.info("running %s (cwd=%s, timeout=%.1fs)", desc, cwd, timeout)

        env = {**os.environ, **env_user}
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                shell=False,                # <-- NEVER shell=True
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError as e:
            log.error("script not found: %s", e)
            return False
        except OSError as e:
            log.error("failed to spawn %s: %s", desc, e)
            return False

        def _drain() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                self._log.append(line.rstrip())
                log.debug("[script] %s", line.rstrip())

        t = threading.Thread(target=_drain, name="midimap-script-drain", daemon=True)
        t.start()

        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.warning("script %s timed out after %.1fs, sending SIGTERM", desc, timeout)
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            try:
                rc = proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                log.error("script %s did not exit after SIGTERM, killing", desc)
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=2.0)
                rc = -1
            log.error("script timed out: %s", desc)
            return False

        t.join(timeout=1.0)
        log.info("script exited rc=%d: %s", rc, desc)
        return rc == 0

    def tail(self, n: int = 200) -> list[str]:
        """Last ``n`` captured lines across all scripts (most recent first)."""
        if n <= 0:
            return []
        return list(self._log)[-n:]
