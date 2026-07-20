# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for the MIDIMischief desktop application.

Build from an environment with ``pip install .[all] pyinstaller``. Third-party
``midimap.plugins`` distributions installed in that same environment are
collected through their entry-point metadata.
"""

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_entry_point

ROOT = Path(SPECPATH)

# The descriptor YAML files are read at runtime rather than imported, so include
# them explicitly.  This also makes the spec resilient when building straight
# from a checkout instead of a wheel.
datas = collect_data_files(
    "midimap",
    includes=["devices/builtin_descriptors/*.yaml"],
)

# These imports are intentionally lazy in the application, which means static
# analysis cannot find them.  The release builds intentionally include the GUI
# and HID extras; headless source installs can still omit either extra.
hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtNetwork",
    "PySide6.QtWidgets",
    "hid",
    "mido.backends.rtmidi",
    "rtmidi",
    "yaml",
]
binaries = []

# Plugins are discovered with importlib.metadata at runtime.  Ask PyInstaller to
# copy entry-point metadata and plugin modules for every installed plugin using
# the documented midimap.plugins group.
plugin_datas, plugin_hiddenimports = collect_entry_point("midimap.plugins")
datas += plugin_datas
hiddenimports += plugin_hiddenimports

analysis = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    [],
    name="MIDIMischief",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=not sys.platform.startswith("darwin"),
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="MIDIMischief.app",
        bundle_identifier="io.github.bjackerman.midimischief",
        info_plist={
            "CFBundleDisplayName": "MIDIMischief",
            "CFBundleName": "MIDIMischief",
            "CFBundleShortVersionString": "0.2.0",
            "CFBundleVersion": "0.2.0",
            "NSHighResolutionCapable": True,
        },
    )
