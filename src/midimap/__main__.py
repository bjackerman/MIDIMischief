"""Allow ``python -m midimap``."""

from __future__ import annotations

from .cli.main import main

raise SystemExit(main())
