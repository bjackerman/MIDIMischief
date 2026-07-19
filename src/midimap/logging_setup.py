"""Logging setup for midimap.

Single source of truth for the rotating file log and stderr handler.
Call :func:`configure` exactly once at process start (CLI ``main`` does this).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

_DEFAULT_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DEFAULT_LEVEL = os.environ.get("MIDIMAP_LOG_LEVEL", "INFO").upper()


def configure(level: str | int = _DEFAULT_LEVEL, log_file: Path | None = None) -> None:
    """Configure the root logger.

    - stderr handler at the requested level
    - rotating file handler (5 MB x 3) at ``log_file`` if provided
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Replace any prior handlers (idempotent if called twice)
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(_DEFAULT_FMT)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    stream.setLevel(level)
    root.addHandler(stream)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        rotating = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        rotating.setFormatter(fmt)
        rotating.setLevel(logging.DEBUG)  # file always captures everything
        root.addHandler(rotating)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
