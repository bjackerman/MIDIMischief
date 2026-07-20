# Contributing

Thanks for taking a look at MIDIMischief. It's a small project: one developer,
one user-base, one repo. PRs and issues are welcome.

## Development setup

```bash
git clone https://github.com/bjackerman/MIDIMischief
cd MIDIMischief
python -m pip install -e ".[all,dev]"
```

This installs the package in editable mode plus the GUI, HID, and dev
extras. The `[all]` extra pulls in `mido`, `python-rtmidi`, `pynput`,
`pydantic`, `PyYAML`, `PySide6`, and `hidapi`. `[dev]` adds `pytest` and
`ruff`.

## Running the tests

```bash
# quick run, headless (no display needed for the GUI tests)
QT_QPA_PLATFORM=offscreen python -m pytest

# a specific test file
python -m pytest tests/test_mapping_engine.py

# verbose
python -m pytest -v

# only the GUI tests
python -m pytest tests/test_gui_*
```

The test suite is fully self-contained. 245 tests, ~15s wall time on
this Win11 dev box, 3 platform-skipped on Windows. No test ever shows
a real Qt dialog (modal `QDialog.exec` would hang the event loop
forever); tests use the same `monkeypatch` pattern M4 introduced.

## Linting

```bash
python -m ruff check src tests
python -m ruff check --fix src tests   # auto-fix what's safe
```

The repo is ruff-clean at the time of writing. Keep it that way before
opening a PR.

## Architecture at a glance

```
DeviceManager ──► EventBus ──► MappingEngine ──► ActionExecutor
   (MIDI+HID)        (queue)       (layers)          (5 backends)
```

The full design doc lives in
[`C:\Users\bjack\.hermes\plans\2026-07-19_105037-midicontroller-desktop-app.md`](
in the upstream `bjackerman/MIDIMischief` design plan) — but the short
version is:

- **`devices/`** is swappable. New backends (e.g. native Win32 raw HID,
  Linux evdev) plug in by implementing the same `list/connect/disconnect`
  protocol and emitting `NormalizedEvent`.
- **`mapping/`** is data-driven. Add a new action kind by writing a
  pydantic model under `profile/schema.py` and a dispatcher branch in
  `actions/__init__.py`.
- **`actions/`** are all `dry_run`-aware. Test mode is a single boolean
  flip on `App.start(dry_run=True)`.
- **`gui/`** uses lazy Qt imports so non-GUI commands (`midimap run`,
  `midimap validate`, etc.) work without PySide6 installed.

## Adding a HID device

1. Plug the device in.
2. `python -c "import hid; [print(d) for d in hid.enumerate()]"` — copy
   the `vendor_id` and `product_id` from the row whose `product_string`
   matches.
3. Create a YAML file under
   `~/.config/midimap/devices/<your_vid>:<your_pid>.yaml` with a
   descriptor. See `src/midimap/devices/builtin_descriptors/descriptors.yaml`
   for the boot-keyboard example.
4. The matching `DeviceDescriptor` is loaded at startup. User-level
   files override shipped defaults on a `(vid, pid)` basis.

## Adding a plugin

A plugin is any Python callable exposed via the `midimap.plugins`
entry-point group. Project layout:

```toml
# pyproject.toml of your plugin package
[project.entry-points."midimap.plugins"]
greet = "my_pkg:greet"
```

```python
# my_pkg/__init__.py
def greet(name: str = "world", *, event=None) -> bool:
    print(f"hello {name} (event: {event})")
    return True
```

A mapping in a profile:

```yaml
- id: greet_test
  input:
    control: "note:60"
    event: press
  action:
    type: plugin
    function: greet
    args:
      name: Brian
```

The signature is inspected: the `event` kwarg is only passed when the
plugin accepts it. See `src/midimap/plugins/registry.py`.

## Issues and PRs

- Open an issue first for non-trivial changes.
- One PR per logical change.
- Tests for any new behavior; ruff clean before pushing.
- Update the changelog under "Unreleased" if it's user-visible.

## Code style

- Python 3.10+ syntax (`from __future__ import annotations` is fine
  for older readability, but the target is 3.10).
- pydantic v2 for all structured config.
- Lazy imports of Qt / hidapi so headless commands don't depend on
  the GUI or HID stack being installed.
- `dry_run` is sacred — every action dispatcher honors it.
- Modal Qt dialogs are *banned* in tests; use `monkeypatch` or
  `log.exception` + `_last_error` (the M4 pattern).

## License

By contributing, you agree to license your contributions under the
project's [MIT License](./LICENSE).

## Packaging desktop releases

Packaging is defined in the root [`midimap.spec`](./midimap.spec), with native
installer helpers under [`packaging/`](./packaging) and CI in
[`.github/workflows/package.yml`](./.github/workflows/package.yml). Release
builds require Python 3.10+ and all optional runtime dependencies because the
frozen application deliberately includes GUI (`PySide6`) and HID (`hidapi`)
support:

```bash
python -m pip install ".[all,package]"
python -m PyInstaller --noconfirm --clean --distpath dist midimap.spec
```

The spec includes runtime descriptor data and installed `midimap.plugins`
entry-points. Install any plugin distribution into the same virtualenv before
running PyInstaller, then smoke-test the frozen binary with:

```bash
./dist/MIDIMischief gui       # Linux/macOS executable (macOS is inside .app)
# Windows: .\dist\MIDIMischief.exe gui
```

### Native installer commands

- **Windows:** Install [NSIS](https://nsis.sourceforge.io/) and run
  `makensis /DVERSION=0.1.0 /DDIST_DIR=dist packaging/windows/MIDIMischief.nsi`.
  This produces the x64 setup executable and Start Menu/Desktop shortcuts.
- **macOS:** Run `bash packaging/macos/create_dmg.sh`. For a distributable
  release, export `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID`, and
  `APPLE_APP_PASSWORD`, then run `bash packaging/macos/sign_and_notarize.sh`.
  The latter Developer-ID-signs the app and DMG, submits it to Apple, and
  staples the notarization ticket.
- **Linux:** Install `appimagetool` and FUSE 2, then run
  `bash packaging/linux/build_appimage.sh`. The AppImage itself is portable;
  developers still need ALSA and hidapi development/runtime libraries when
  building native Python dependencies.

Do not commit signing credentials, certificates, provisioning profiles, or
notarization passwords. The package workflow signs/notarizes only tagged macOS
builds when its `APPLE_*` secrets are present. Validate every installer on a
clean platform VM before publishing; in particular verify macOS Accessibility,
Linux `udev` HID access, and that the required external plugin entry-points are
visible in Settings.
