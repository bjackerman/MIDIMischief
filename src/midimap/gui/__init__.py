"""midimap GUI package.

Lazy import of Qt so that non-GUI commands (``monitor``, ``run``) do
not pay the import cost or require PySide6 to be installed. The
``gui`` extras in ``pyproject.toml`` declare the dependency.
"""

from __future__ import annotations
