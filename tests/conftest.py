"""conftest — make ``src`` importable when running pytest from the repo root.

GUI tests use the offscreen Qt platform plugin so they run on a
headless CI box. We set the env var once at conftest load time and
expose a session-scoped ``qapp`` fixture that all GUI tests reuse.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# tests/ is at <repo>/tests; src is at <repo>/src
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Set the Qt platform plugin before any test imports PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
