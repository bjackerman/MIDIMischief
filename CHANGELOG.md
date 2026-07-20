# Changelog

All notable changes to MIDIMischief are documented here. Versions follow
[SemVer](https://semver.org/).

## [0.2.0] - 2026-07-20

Second release. Closes three of the "known gaps" called out in the
v0.1.0 README, and adds cross-platform packaging.

### New
- **Visual device render widget** (`gui/widgets/device_render.py`, 216
  LOC) — paints a controller's pads/knobs/sliders from the descriptor,
  like Ableton's MIDI-mapping overlay but live. Wired into the Devices
  tab. 84 LOC of tests.
- **Real MIDI hotplug reconciliation** — the v0.1.0 `_hotplug_loop`
  was a stub. This one reconciles open ports against the current
  device list, auto-connects per the active profile, and emits clean
  `connect` / `disconnect` log lines.
- **Cross-platform packaging** — `midimap.spec` (PyInstaller), NSIS
  installer script for Windows, DMG script for macOS, AppImage script
  for Linux, and a `.github/workflows/package.yml` CI that builds all
  three on native GitHub-hosted runners and attaches the artifacts to
  the workflow run.
- **Layer controls in the profile editor** — add/rename/delete buttons
  for layers (previously you could only switch the active layer).
- **Preserve bindings on action edit** — `BindControlDialog` keeps the
  original `id` + `input` when only the `action` changes.
- **HID `is_connected()` is real** — previously returned `False` for
  every HID device; now tracks open HID handles.
- **More bundled device descriptors** — split the single
  `descriptors.yaml` into per-category files
  (`gamepads.yaml`, `macro_pads.yaml`, `midi_adjacent.yaml`,
  `controller_boards.yaml`) so users can override one category
  without touching the others.

### Removed
- **`quit_app` builtin** — was a stub returning `False`. Deleted; use
  the OS-native "Quit" action via a `script` action if you really
  need it.

### Stats
- 264 tests pass (245 → 264, +19), ruff clean, 3 platform-skipped
- 8 merged PRs (#1, #2, #3, #4, #5, #6, #7, #9)
- +1720 / −133 lines across 37 files

## [0.1.0] - 2026-07-19

First public release. Six milestones shipped:

### M1 — MIDI input pipeline
- `mido` + `python-rtmidi` based `DeviceManager`
- `NormalizedEvent` abstraction (device_id, control_id, event_type, value, velocity, channel, timestamp_ms)
- `midimap monitor --list` and `midimap monitor --device SUBSTRING` CLI
- Live event log via the `EventBus` pub/sub

### M2 — Mapping engine + keyboard output
- `pydantic` v2 profile schema (DeviceMatch, InputSpec, Mapping, Layer, Profile)
- JSON + YAML load/save via `midimap profile.load/save`
- `MappingEngine` with layer stack, hold-to-activate, value-range, press-duration filters
- `pynput` keyboard output with combo send and `dry_run` support
- `midimap run --profile <file> [--dry-run]` headless runner

### M3 — Scripts, builtins, media, templates, safety
- `ScriptRunner` with `subprocess`, timeout (SIGTERM→SIGKILL), `MIDIMAP_EVENT` env var
- `risky: true` flag triggers confirm callback; per-session remember
- `BuiltinAction` — `launch_app`, `open_url`, `volume_up/down/mute/set`, `noop`
- `MediaKeySender` — per-OS (Win `SendInput` + `VK_MEDIA_*`, mac `osascript`, Linux `playerctl`/`xdotool`)
- Template substitution in all action params: `$value`, `$vel`, `$control`, `$device`, `$event`, `$channel`, `$ts`, `$$`

### M4 — PySide6 GUI editor
- `MainWindow` with 4 tabs: Devices, Profile, Event Log, Settings
- `EventTableModel`/`EventTableView` (5000-row cap, FIFO drop, color-coded)
- 3-page `BindControlDialog` wizard (Input → Action → Save); `Mapping` model + `mapping_created` signal
- `LearnModeDialog` with countdown timer
- `EventBusQtBridge` for cross-thread delivery via `Qt.QueuedConnection`
- Single-instance lock via `QLocalServer`
- System tray "hide to tray" with Reload + Show + Quit

### M5 — Profile tooling + hot-reload
- `ProfileWatcher` (`QFileSystemWatcher` + 200 ms debounce) — re-validates on change, never blocks the engine
- `midimap validate <profile>` — load + validate, exits 0/1
- `midimap diff <a> <b>` — structural diff (`+/-/~` per layer)
- `midimap export <in> <out>` / `midimap import <in> <out>` — JSON ↔ YAML round-trip
- Edit-existing binding (double-click row), F5 reload, layer combo

### M6 — HID backend + plugins + auto-start
- `HIDDeviceManager` (hidapi 0.15) — enumerate, open, per-device read thread
- `hid_normalizer` for boot-keyboard (8-byte) and generic (configurable buttons/axes) reports
- `DeviceDescriptor` loader (YAML/JSON) + bundled default for Logitech POP Icon Keys
- `DeviceManager` now owns a `HIDDeviceManager` and routes `connect`/`disconnect` by `device_id` prefix
- `PluginRegistry` via `midimap.plugins` entry-point group (plus legacy `midimap_plugins` module)
- `PluginAction` replaces the M4 stub; `PluginSpec.call()` inspects the signature and only passes `event` when accepted
- `autostart` helper: Windows `HKCU\...\Run`, mac `~/Library/LaunchAgents/...plist`, Linux `~/.config/autostart/...desktop`
- Settings tab wires the "Start with the OS" checkbox and shows the registered plugin list

### M6.5 — Bind-from-event
- Right-click a row in the Live Monitor → "Bind this control…" → wizard opens pre-filled
- "Map this event…" button on the Devices tab (enabled when a row is selected)
- New mapping lands in the active profile; engine picks it up immediately

### Stats
- 245 tests pass (v0.1.0; superseded by 264 in v0.2.0), ruff clean, 3 platform-skipped
- 8 commits on `master`
- 1,000s of lines of code

[0.2.0]: https://github.com/bjackerman/MIDIMischief/releases/tag/v0.2.0
[0.1.0]: https://github.com/bjackerman/MIDIMischief/releases/tag/v0.1.0
