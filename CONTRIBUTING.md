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
   descriptor. See the focused examples in
   `src/midimap/devices/builtin_descriptors/`.
4. The matching `DeviceDescriptor` is loaded at startup. User-level
   files override shipped defaults on a `(vid, pid)` basis.

### Descriptor contribution format

Bundled descriptors are YAML lists. Add a device to the appropriate family
file under `src/midimap/devices/builtin_descriptors/` (or create a clearly
named family file). Every entry needs a USB `vendor_id`, `product_id`, and a
`layout`; use hexadecimal IDs so they are easy to compare with operating
system and hidapi output.

```yaml
- vendor_id: 0x1234
  product_id: 0x5678
  name: "Example Controller"
  manufacturer: "Example, Inc."       # optional
  layout:
    type: generic
    buttons:
      - {byte: 1, bit: 0, name: "button:play"}
    axes:
      - {byte: 2, size: 1, signed: false, name: "knob:tempo"}
```

`type: boot` decodes an eight-byte USB boot-keyboard report as `mod:*` and
`key:<usage>` controls. `type: generic` accepts `buttons` and `axes`:

- A button has a zero-based report `byte`, a `bit` from 0 through 7, and an
  optional stable `name`. It emits `PRESS` and `RELEASE` as that bit changes.
- An axis has a zero-based report `byte`, `size` of 1, 2, or 4 bytes,
  optional `signed` (default `false`), and an optional stable `name`. It emits
  a `CHANGE` event for every report.
- Byte offsets are into the data returned by hidapi. Include the report-ID
  byte when hidapi returns it; do not include it when the backend strips it.

Use control names that describe the physical control rather than its current
mapping (for example, `button:play`, `encoder:turn`, or `axis:left_x`). Do not
reuse a VID/PID for a different interface layout: describe the tested HID
input interface, and note mode limitations in a YAML comment when needed.

### Capturing a HID report

Capture reports before proposing a descriptor; product documentation alone is
not enough because wired, Bluetooth, and compatibility modes can differ.

1. Identify the HID interface and IDs with:

   ```bash
   python -c "import hid; [print(d) for d in hid.enumerate()]"
   ```

2. Use a short script (or an existing HID monitor) to print `list(device.read(64))`
   while operating **one control at a time**: idle, press, release, and each
   direction/extreme for axes. Record whether a report-ID byte is present.
3. Compare idle and active reports to identify the changing byte/bit or
   little-endian axis field. Repeat after reconnecting and in every supported
   transport/mode.
4. Add a representative idle-to-active report pair to
   `tests/fixtures/builtin_hid_reports.yaml` and its expected normalized
   control. The fixture test loads the shipped descriptor and prevents future
   offset regressions.
5. Run `python -m pytest tests/test_hid.py` and `python -m ruff check src tests`.

Never commit serial numbers, device paths, user names, or a complete raw HID
dump that could contain unrelated input. Keep fixtures to the smallest report
that demonstrates the field being described.

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
