# MIDIMischief

> Cross-platform desktop app that maps USB MIDI controllers and USB
> HID devices to keyboard shortcuts, OS-level actions, and user-defined
> scripts. Free, open-source, no DAW or proprietary drivers required.
> The Python package is still imported as `midimap` (shorter, ergonomic
> CLI command). The project is published as **MIDIMischief**.

[![Tests](https://img.shields.io/badge/tests-245%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

## Table of contents

- [What it does](#what-it-does)
- [Library research summary](#library-research-summary)
- [Architecture](#architecture)
- [GUI walkthrough](#gui-walkthrough)
- [Milestone status](#milestone-status)
- [Quick start](#quick-start)
- [Desktop installers and platform requirements](#desktop-installers-and-platform-requirements)
- [Profile example](#profile-example)
- [Action reference](#action-reference)
- [Profile versioning](#profile-versioning)
- [Platform-specific setup](#platform-specific-setup)
- [Project layout](#project-layout)
- [Modular design](#modular-design)
- [Skeleton code: how events flow](#skeleton-code-how-events-flow)
- [Open questions / known limitations](#open-questions--known-limitations)
- [License](#license)
## What it does

- **Reads MIDI** notes / CCs / velocity / pressure from any controller
  your OS exposes (Maschine, Akai MPD / MPK, Arturia, Launchpad, Korg
  nanoKONTROL, etc.) via the standard USB-Audio class driver. Hot-plug
  and reconnect are handled: the manager re-scans on a 2 s timer and
  emits a `connect` / `disconnect` log line for every change.
- Reads HID reports from gamepads, macro pads, custom boards, and
  the Logitech POP Icon Keys (boot protocol). For other devices, drop a
  YAML descriptor in `~/.config/midimap/devices/<vid>:<pid>.yaml` —
  see [Adding a HID device](#adding-a-hid-device) below. **As of
  v0.2.0**, a [`device_render.py`](src/midimap/gui/widgets/device_render.py)
  visual widget paints the controller's pads/knobs/sliders from the
  descriptor — like Ableton's MIDI-mapping overlay but live.
- **Maps** each event to a **keyboard combo**, **media key** (play/pause,
  volume, etc.), **OS action** (launch app, open URL, system volume),
  **shell command** (with template substitution like `$value` and
  `$control`), or **Python plugin** (entry-point discovered).
- **Granular**: layers toggled by hold-to-activate buttons, value-range
  bands (knob low / mid / high), and press-duration filters.
- **CLI tooling**: `midimap validate`, `midimap diff`, `midimap export`,
  `midimap import` — JSON ↔ YAML round-trip with semantic diff.
- **Qt (PySide6) GUI editor** with live event monitor, learn mode, and
  a profile hot-reload that survives bad edits.
- **245 tests pass, ruff clean.** See [CHANGELOG.md](./CHANGELOG.md) for
  the per-milestone feature log.

## Library research summary

All libraries are free, open-source, and actively maintained. Library
selection is the single biggest "should I trust this tool?" signal, so
here's the full table.

| Library | Role | OS support | License | Event types | Notes |
|---|---|---|---|---|---|
| [`mido`](https://mido.readthedocs.io/) + [`python-rtmidi`](https://spotlightkid.github.io/python-rtmidi/) | MIDI input | Windows (WinMM), macOS (CoreMIDI), Linux (ALSA) | MIT / MIT | Note On/Off (with velocity), Control Change (0–127), Poly Aftertouch, Channel Pressure, Pitch Bend, Program Change, SysEx (raw) | Wraps the OS's USB-MIDI class driver. No proprietary SDK needed. |
| [`hidapi`](https://github.com/libusb/hidapi) | HID input | Win (HID class), macOS (IOHID), Linux (hidraw) | BSD-3 / HIDAPI | Buttons (bitmask), axes (signed 8/16-bit), hats, custom vendor reports | The `hid` PyPI package wraps it. Per-device descriptor required for layout. |
| [`pynput`](https://pynput.readthedocs.io/) | Keyboard / mouse output | Windows, macOS, Linux | LGPLv3 | Synthesises keyboard combos, media keys, mouse events | **Chosen over the `keyboard` package** because `keyboard` is unreliable on macOS Quartz. |
| [`PySide6`](https://doc.qt.io/qtforpython-6/) (Qt 6) | GUI | Windows, macOS, Linux | LGPL | N/A | **Chosen over PyQt6** for LGPL licensing. **Chosen over Electron/Tauri** because the entire app is Python — no IPC, no Node toolchain. |
| [`pydantic`](https://docs.pydantic.dev/) v2 | Config schema | All | MIT | N/A | Discriminated unions for action variants. |
| [`PyYAML`](https://pyyaml.org/) | YAML profile parsing | All | MIT | N/A | Optional format alongside JSON. |
| Plugin discovery: stdlib `importlib.metadata` entry-points | Plugin loader | All | PSF | N/A | Standard Python packaging mechanism. |
| `pycaw` (optional, Windows volume) | `volume_set` | Windows only | MIT | N/A | Not bundled by default; loaded if installed. |
| `playerctl` / `xdotool` (Linux) | Media / volume fallback | Linux only | GPL/LGPL | N/A | Detected at runtime; falls back to logged warning if absent. |

**Stack recommendation, in one line:** Python 3.10+ · PySide6 · mido +
python-rtmidi (MIDI) · hidapi (HID) · pynput (output) · pydantic v2
(schema) · PyYAML (YAML profiles).

**Why this stack:** the MIDI libraries use the OS's class driver so no
DAW or proprietary SDK is needed for basic input; pynput is the only
truly cross-platform keyboard-output library that works on macOS; Qt
Widgets is mature, looks native, and avoids a Node/Electron toolchain
for a Python-first project. The full design rationale lives in
[`C:\Users\bjack\.hermes\plans\2026-07-19_105037-midicontroller-desktop-app.md`][plan]
(72 KB, ~1227 lines).

## Architecture

```
   MIDI / HID devices
         │
         ▼
┌──────────────────────┐
│   DeviceManager      │  • list / connect / disconnect
│   ┌──────────────┐   │  • re-scans on a 2 s timer (hot-plug)
│   │ MIDI backend │   │  • per-port / per-device callback closure
│   │ HID  backend │   │    tags events with the right device_id
│   └──────────────┘   │
└──────────┬───────────┘
           │ NormalizedEvent
           │   device_id, control_id, event_type,
           │   value, velocity, channel, timestamp_ms
           ▼
┌──────────────────────┐
│      EventBus        │  • pub/sub, per-subscriber queue
│  (per-sub thread)    │  • drop-oldest on full (no producer block)
└──────────┬───────────┘
           │ NormalizedEvent
           ▼
┌──────────────────────┐
│   MappingEngine      │  • layer stack + hold-to-activate
│  (headless thread)   │  • value range + press duration filters
│                      │  • returns Action or None
└──────────┬───────────┘
           │ Action (or None)
           ▼
┌──────────────────────┐
│   ActionExecutor     │  • dispatches by action.kind
│  (same thread as     │  • 5 backends:
│   mapping engine)    │    keyboard, media, builtin, script, plugin
└──────────┬───────────┘
           │ OS call / process spawn
           ▼
   keyboard / media key / launch app /
   shell command / Python plugin
```

Both device backends produce the same `NormalizedEvent` so the rest of
the app doesn't care which backend emitted an event. The mapping engine
is data-driven — the profile schema is a `pydantic` v2 model; adding a
new action kind is a 3-file change (schema, executor, GUI form).

## GUI walkthrough

The main window has 4 tabs plus a system tray. From the menu bar:
**File → New / Open / Save / Save As / Reload**, **Edit → Preferences**,
**Help → About / Logs**.

| Tab | What you do there |
|---|---|
| **Devices** | Left: list of detected MIDI + HID devices with Connect/Disconnect and a 2 s rescan. Right: live event monitor (newest first, 5000-row cap, color-coded by event type). Right-click any row → "Bind this control…" opens the binding wizard pre-filled. The "Map this event…" button (next to Pause / Clear) does the same thing. |
| **Profile** | A QTableView of all mappings in the active layer. Toolbar: New, Delete, Reload. Double-click a row to edit. The "Layer" combo at the top switches the visible layer. Press F5 to reload the file. |
| **Event Log** | A live tail of every log line from the app. Filter by substring to focus on a particular control or action. |
| **Settings** | Dry-run / disable-scripts / confirm-risky checkboxes. **Start with the OS** (wires to the autostart helper). Plugins list (entry-points discovered). About panel with version + milestone status. |

**System tray** (right-click): Show / Reload / Quit. Closing the window
hides to tray; double-click the tray icon to show again. A single
instance is enforced via `QLocalServer` — re-launching the binary
focuses the existing window.

**Learn Mode** (Edit menu, or the wizard's input page): a small floating
countdown widget captures the next event from any connected device and
pre-fills the wizard. Right-clicking a live event row is the same flow
but more discoverable.

## Milestone status

All six milestones shipped:

| | | | |
|--|--|--|--|
| M1 | done | MIDI input + live monitor CLI | [commit `f3c3901`](https://github.com/bjackerman/MIDIMischief/commit/f3c3901) |
| M2 | done | Mapping engine + keyboard output | [commit `6914df9`](https://github.com/bjackerman/MIDIMischief/commit/6914df9) |
| M3 | done | Scripts, builtins, media, templates, safety | [commit `29649d4`](https://github.com/bjackerman/MIDIMischief/commit/29649d4) |
| M4 | done | PySide6 GUI editor | [commit `3b5dfee`](https://github.com/bjackerman/MIDIMischief/commit/3b5dfee) |
| M5 | done | Profile hot-reload, validate/diff/export, edit-existing | [commit `5457984`](https://github.com/bjackerman/MIDIMischief/commit/5457984) |
| M6 | done | HID + descriptors + plugins + auto-start | [commit `b8faa7a`](https://github.com/bjackerman/MIDIMischief/commit/b8faa7a) |
| M6.5 | done | Bind from live event (right-click) | [commit `37dcac5`](https://github.com/bjackerman/MIDIMischief/commit/37dcac5) |
| v0.2 | done | Device render widget, MIDI hotplug, descriptor split, packaging, layer controls, binding preserve, is_connected for HID, quit_app removed | [tag `v0.2.0`](https://github.com/bjackerman/MIDIMischief/releases/tag/v0.2.0) |

**264 tests pass, ruff clean.** See [CHANGELOG.md](./CHANGELOG.md) for
the per-version feature log.
## Quick start

```bash
# from D:\hermes\midimap (or wherever you cloned)
python -m pip install -e ".[all,dev]"

# list MIDI devices
python -m midimap monitor --list

# list HID devices
python -c "import hid; [print(d) for d in hid.enumerate()]"

# run a profile headless (dry-run, no keys/script side effects)
python -m midimap run --profile tests/fixtures/sample_profile.json --dry-run

# validate a profile
python -m midimap validate tests/fixtures/sample_profile.json

# diff two profiles
python -m midimap diff tests/fixtures/sample_profile.json tests/fixtures/sample_profile.yaml

# convert JSON <-> YAML
python -m midimap export tests/fixtures/sample_profile.json /tmp/out.yaml
python -m midimap import /tmp/out.yaml /tmp/out.json

# launch the GUI
python -m midimap gui
# or open a profile at launch:
python -m midimap gui --profile tests/fixtures/sample_profile.json
```

## Profile example

```json
{
  "version": 1,
  "name": "Maschine Mikro — Default",
  "device_match": {"kind": "midi", "name_contains": "Maschine Mikro"},
  "default_layer": 0,
  "layers": {
    "0": {
      "name": "Default",
      "mappings": [
        {
          "id": "pad1",
          "input": {"control": "note:60", "event": "press"},
          "action": {"type": "keyboard", "keys": ["ctrl", "1"]}
        },
        {
          "id": "knob1_high",
          "input": {"control": "cc:1", "event": "change", "value_min": 86},
          "action": {"type": "script", "command": ["logger", "$value"], "timeout_s": 5.0}
        }
      ]
    }
  }
}
```

A full action kinds reference: `KeyboardAction`, `MediaAction`,
`BuiltinAction`, `ScriptAction`, `PluginAction`. All are pydantic v2
discriminated unions on the `type` field; invalid combinations are
rejected at load time with a clear error message.

## Action reference

Built-in actions are limited to actions that MIDIMischief implements on
the current platform: `launch_app`, `open_url`, `volume_up`,
`volume_down`, `volume_mute`, `volume_set`, and `noop`. The profile
schema rejects any other builtin name, so a saved mapping cannot refer
to an unimplemented builtin.

`quit_app` is **not** a MIDIMischief builtin and never terminates either
the MIDIMischief process or an arbitrary target application. To close a
specific application, use a `script` action with a command that names
the target explicitly, set `risky: true`, and keep **Confirm risky
scripts the first time** enabled. Scripts are the deliberate escape
hatch for platform-specific process management; they can also be
globally disabled in Settings.

## Profile versioning

The schema's top-level `version` field starts at `1` and is **part of
the on-disk format**. The loader:

- **Same major version** → load as-is.
- **Higher major version** in the file → reject with a clear error
  ("file is v2, this build only supports v1").
- **Lower major version** → run the registered `migrations` chain
  (none yet registered for v0; will land when v2 ships).

Within a major version, **additive changes only** — new optional
fields, new action kinds, new control types. Removing or renaming a
field is a major-version bump and requires a migration script.

## Platform-specific setup

- **Windows 11** — no extra setup. Run `python -m midimap gui`.
- **macOS** — first time a HID device is read the OS will pop a
  permission dialog. Approve it. MIDI works without setup.
- **Linux** — non-root users need a udev rule for raw HID access. One
  example for a specific device (replace `vid`/`pid` with the values
  from `hid.enumerate()`):
  ```
  # /etc/udev/rules.d/99-midimap.rules
  SUBSYSTEM=="hidraw", ATTRS{idVendor}=="046d", ATTRS{idProduct}=="b38f", MODE="0660", TAG+="uaccess"
  ```
  Then `sudo udevadm control --reload && sudo udevadm trigger`.

### Adding a HID device

1. Plug it in.
2. `python -c "import hid; [print(d) for d in hid.enumerate()]"`.
3. Note `vendor_id` and `product_id` from the row whose
   `product_string` matches.
4. Create `~/.config/midimap/devices/<vid>:<pid>.yaml` (Linux/macOS) or
   `%LOCALAPPDATA%\midimap\devices\<vid>-<pid>.yaml` (Windows) with a
   descriptor. See the family-specific examples under
   `src/midimap/devices/builtin_descriptors/`.
5. Reload (the app watches the directory and picks up the new file).

## Project layout

```
src/midimap/
  __init__.py            # version
  __main__.py            # python -m midimap
  app.py                 # App: wires DeviceManager -> bus -> engine -> executor
  events.py              # NormalizedEvent, EventType, Value
  event_bus.py           # pub/sub with drop-oldest per-subscriber queues
  logging_setup.py
  cli/                   # argparse entry, monitor, run, gui, validate, diff, export, import
  devices/
    manager.py           # DeviceManager (MIDI + HID)
    midi_normalizer.py
    hid_manager.py       # HIDDeviceManager
    hid_normalizer.py    # boot-keyboard + generic layouts
    descriptors.py       # YAML/JSON device descriptors
    builtin_descriptors/    # bundled HID catalog, split by device family
  actions/               # Action, ActionExecutor, keyboard, media, builtin, script, plugin, template
  mapping/engine.py
  profile/               # schema (pydantic v2), store, diff, watcher
  plugins/registry.py    # entry-point discovery
  autostart.py           # per-OS auto-start
  gui/                   # PySide6: main_window, 4 tabs, dialogs, widgets
tests/                   # 245 tests, fully self-contained, headless-safe
```

## Modular design

The point of the design isn't the milestones, it's that **any of the
five layers can be swapped without touching the others**:

- **`devices/`** is a backend. New input sources (Linux evdev, native
  Win32 raw HID, BLE MIDI, etc.) plug in by implementing the same
  `list / connect / disconnect / read-loop → NormalizedEvent` protocol.
  The `DeviceManager` doesn't care which backend a `device_id` came
  from — it routes by the `midi:` / `hid:` prefix.
- **`mapping/`** is data-driven. The `MappingEngine` reads a `Profile`
  and matches events; you don't change the engine to support a new
  control type — you add it to the `InputSpec` schema and the
  `parse_control_id()` table.
- **`actions/`** is a registry. Add a new action kind by writing a
  pydantic model in `profile/schema.py`, a dispatcher branch in
  `actions/__init__.py`, and a form in `gui/dialogs/bind_control.py`.
  Three files, ~150 LOC.
- **`plugins/`** is the public extension point. Ship a Python package
  with an entry-point in the `midimap.plugins` group; users can wire
  it into mappings without touching the app.
- **`gui/`** is one of two front-ends. The other is the headless
  `midimap run` and the `monitor` / `validate` / `diff` / `export` /
  `import` subcommands. Both consume the same `App` and `EventBus`.

The `dry_run` flag is honored end-to-end: a single boolean flip on
`App.start(dry_run=True)` makes every action log instead of firing.
This is the recommended way to test a new profile before letting it
press real keys.

## Skeleton code: how events flow

Three code blocks from `src/midimap/`. Full sources are in the repo;
these are the contract that ties the layers together.

### 1. `DeviceManager` — device callback produces `NormalizedEvent`

```python
# src/midimap/devices/manager.py
import mido
from .midi_normalizer import midi_to_normalized

class DeviceManager:
    def connect(self, device_id: str) -> None:
        port_name = device_id.removeprefix("midi:")
        callback = self._make_callback(device_id)
        self._open_ports[device_id] = mido.open_input(
            port_name, callback=callback
        )

    def _make_callback(self, device_id):
        def _cb(message: mido.Message) -> None:
            if self._stop.is_set():
                return
            ev = midi_to_normalized(message, device_id=device_id)
            if ev is not None:
                self._emit(ev)         # -> EventBus subscribers
        return _cb
```

### 2. `MappingEngine` — event becomes an `Action`

```python
# src/midimap/mapping/engine.py
from ..profile.schema import Profile

class MappingEngine:
    def __init__(self, profile: Profile) -> None:
        self._profile = profile

    def process(self, event: NormalizedEvent) -> Action | None:
        # 1. find the active layer(s) — for hold-to-activate, walk the
        #    "layer_hold" chain from the currently-held buttons
        layers = self._active_layers(event)
        # 2. collect every mapping across active layers whose InputSpec
        #    matches the event (control id, event type, value range,
        #    press duration)
        candidates = [
            m for layer in layers
              for m in layer.mappings
              if self._matches(m, event)
        ]
        if not candidates:
            return None
        # 3. last mapping wins (deterministic, layer 0 default, hold
        #    layers override)
        chosen = candidates[-1]
        return Action.from_mapping(chosen, event)
```

### 3. `ActionExecutor` — action becomes a side-effect

```python
# src/midimap/actions/__init__.py
class ActionExecutor:
    def execute(self, action: Action) -> bool:
        try:
            if action.kind == "keyboard":
                self._keyboard.send(action.params["keys"])
            elif action.kind == "media":
                self._media.send(action.params["key"])
            elif action.kind == "builtin":
                run_builtin(action.params["name"], action.params.get("params") or {})
            elif action.kind == "script":
                self._scripts.run(action.params, event=action.event)
            elif action.kind == "plugin":
                return self._dispatch_plugin(action)
            else:
                log.warning("unknown action kind: %r", action.kind)
                return False
            return True
        except Exception:
            log.exception("action execution failed: %s", action.kind)
            return False
```

End-to-end (skeleton from `src/midimap/app.py`):

```python
class App:
    def start(self, profile: Profile, *, dry_run=False, scripts_enabled=True,
              confirm_risky=True, confirm_callback=None, auto_connect=True):
        self.engine = MappingEngine(profile)
        self.executor = ActionExecutor(
            dry_run=dry_run,
            scripts_enabled=scripts_enabled,
            confirm_risky=confirm_risky,
            confirm_callback=confirm_callback,
        )
        self.devices.subscribe(self.bus.publish)
        self.bus.subscribe(self._dispatch, name="engine")
        if auto_connect:
            for d in self.devices.list_devices():
                if profile.matches_device(d):
                    self.devices.connect(d["id"])

    def _dispatch(self, event: NormalizedEvent) -> None:
        action = self.engine.process(event)
        if action is not None:
            self.executor.execute(action)
```

A real event trace (this host, with `tests/fixtures/sample_profile.json`):

```
bus.publish(NormalizedEvent(device_id="midi:ATM SQ 0",
                            control_id="note:60",
                            event_type=PRESS, value=100, ...))
   → engine.process(event)
   → Action(kind="keyboard", params={"keys": ["ctrl", "1"]}, event=event)
   → executor.execute(action)
   → log.info("keyboard send: ['ctrl', '1']")   # or actual keys, if !dry_run
```

## Open questions / known limitations

Documented honestly. PRs welcome.

- **HID exclusivity on Windows.** Some HID devices (notably raw-HID
  game controllers) are owned exclusively by other applications. The
  `connect()` call will fail with a `RuntimeError`; the Devices tab
  shows the error in the status bar. Closing the owning application
  releases the device.
- **macOS IOHID permissions.** The first time a HID device is read on
  macOS, the OS pops a permission dialog. Users must approve; the app
  cannot programmatically grant itself access.
- **Linux udev.** Non-root users need a udev rule; the README has a
  one-liner. No GUI "install udev rules" action yet.
- **MIDI loopback on Windows.** The dev host's ATM SQ ports don't
  deliver events through any (output × input) loopback pairing — this
  is a Windows driver quirk, not a midimap bug. End-to-end tests use
  injected `mido.Message` objects.
- **Volume control is best-effort.** Windows uses `pycaw` if installed
  else logs a warning. macOS uses `osascript`. Linux tries `pactl`
  then `amixer`. Some Linux desktops with strict PipeWire policies
  may require `pactl` to be in the user's `$PATH`.
- **Plugin API is `dict[str, Any]` args, no schema.** The plugin
  registry inspects the callable's signature; the GUI uses the
  signature to build a dynamic form. There's no per-plugin
  `PluginManifest` yet — would be a 0.3.0 addition.
- **One process per user.** The single-instance lock is
  `midimap-single-instance-{USERNAME}`. Two users on the same Windows
  host can run their own instance; that's intentional.

## Desktop installers and platform requirements

Release builds package the `midimap gui` application with PyInstaller. Every
bundle contains the built-in HID descriptor YAML, the GUI and HID dependencies,
and any installed distributions advertising the `midimap.plugins` entry-point.
Third-party plugins must therefore be installed in the **build** environment;
users can alternatively install plugins into a Python environment and run the
source/PyPI command.

| Platform | Release artifact | Install and run | System requirements |
|---|---|---|---|
| Windows 10/11 x64 | NSIS `...-windows-x64-setup.exe` | Run the installer, then start **MIDIMischief** from Start Menu or Desktop. | USB MIDI uses the Windows class driver. HID uses the Windows HID class driver. Grant any keyboard-input permissions requested by endpoint protection. |
| macOS 12+ | `...-macos.dmg` containing `MIDIMischief.app` | Open the DMG, drag the app to Applications, then open it. | Approve the app in Gatekeeper if it is not notarized, and grant **Accessibility** permission in Privacy & Security before sending keyboard/media keys. MIDI uses CoreMIDI; HID uses IOHID. |
| Linux x86_64 | `...-linux-x86_64.AppImage` | `chmod +x MIDIMischief-*.AppImage && ./MIDIMischief-*.AppImage` | A current glibc desktop plus FUSE 2 (`libfuse2` on Ubuntu/Debian). MIDI needs ALSA access; HID users normally need a `udev` rule granting their account access to `/dev/hidraw*`. Wayland compositors may restrict synthetic keyboard input. |

The CI workflow builds all three artifacts on their native GitHub-hosted
runners and attaches them to the workflow run. Tagged macOS releases can be
Developer-ID signed and notarized when the Apple signing secrets are configured.
Unsigned builds remain usable for local testing but prompt users more often.

### Install from Python instead

The installers are intended for end users. For a CLI, development checkout, or
an architecture not covered by the release artifacts, use Python 3.10+:

```bash
python -m pip install "MIDIMischief[all]"
midimap gui
```

On Debian/Ubuntu, install the native libraries first when wheels are unavailable:
`sudo apt install libasound2-dev libhidapi-hidraw0 libfuse2`. On Fedora, the
corresponding packages are typically `alsa-lib-devel`, `hidapi`, and `fuse`.
These packages enable device access; they do not substitute for the Python
`[all]` dependencies.

## License

[MIT](./LICENSE). See [CONTRIBUTING.md](./CONTRIBUTING.md) for the
contribution guide.

[plan]: C:\Users\bjack\.hermes\plans\2026-07-19_105037-midicontroller-desktop-app.md
