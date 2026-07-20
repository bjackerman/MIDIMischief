# Changelog

All notable changes to MIDIMischief are documented here. Versions follow
[SemVer](https://semver.org/).

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
- 245 tests pass, ruff clean, 3 platform-skipped (macOS/Linux)
- 8 commits on `master`
- 1,000s of lines of code

[0.1.0]: https://github.com/bjackerman/MIDIMischief/releases/tag/v0.1.0
