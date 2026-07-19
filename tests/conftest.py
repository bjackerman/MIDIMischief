"""conftest — make ``src`` importable when running pytest from the repo root."""

from __future__ import annotations

import sys
from pathlib import Path

# tests/ is at <repo>/tests; src is at <repo>/src
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
