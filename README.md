# Farever Atlas

[![Windows portable exe](https://github.com/wdymUsername/FareverAtlas/actions/workflows/windows-portable.yml/badge.svg)](https://github.com/wdymUsername/FareverAtlas/actions/workflows/windows-portable.yml)
[![VirusTotal](https://badges.cssnr.com/vt/wdymUsername/FareverAtlas/FareverAtlas.exe)](https://github.com/wdymUsername/FareverAtlas/releases/tag/Nightly)

Farever Atlas is a standalone map and companion app for Farever. It runs in
its own window and reads live player telemetry from a read-only native
bridge. It does not write game memory.

Start Farever and log in to a character before launching Atlas.

## Features

### Working

**Map**
- Pan, zoom, recenter / free view
- Live player position, heading, HP / shield
- Player / party display names
- Static POIs with filters (obelisks, respawns, dungeons, merchants, activities)
- Loot filters (chests, red orbs, plants, ore) and live interactibles in range
- Nearby enemies and players (optional names)
- Instance detection with local-instance view (blank map until custom dungeon
  art exists — map files are not shipped unless someone draws them)
- Offline mode (stops bridge polling; keeps last map position)
- Nightling Rift hourly countdown

**Fog of war**
- Enable / disable, soft edge, hide markers under fog
- Baked clear-zone FoW in release builds
- Layer / bake authoring tools (`--dev` only)

**Waypoints**
- Create, edit, delete; manager; visibility; active route line

**Party**
- Party cards (class, HP / shield, distance)
- Party markers on the map

**Players**
- Split World / Friends roster
- Live instance roster: search, sort, class pin, party-only
- Local friends (★) with HERE / AWAY on this layer
- Focus / follow on the map
- Steam profile and chat; Web API avatars / status and Steam-friend badge
  (configure Steam Web API key; SteamID64 for Steam-friend list)

**App / launcher**
- Settings: General, Map, Party, Bridge Status, About
- Always on top, restore window positions, single-instance lock
- `./farever` / `farever.bat` — `setup`, `start`, `stop`, `restart`
- Portable Windows exe (no Python required)

### WIP

- Gather nav (first implementation)
- DPS widget / Combat Meter (UI present; telemetry not wired properly yet)
- Planner (page shell and some UI only)

### Planned

- Codex
- Alerts / target cast warnings (need live cast data from the bridge)
- Completed red-orb tracking (hide when collected)
- Combat Meter advanced options (after DPS pipeline rework)
- Planner equipment, live stats, selectable skills, real talent data / icons

## Requirements

- Farever running and logged in to a character
- **Linux / Proton:** Python 3.10+, Steam + Proton; build the bridge once
- **Windows portable:** just the exe (creates runtime dirs next to itself)
- **Windows source:** Python 3.10+ and a built `farever-atlas-bridge.exe`

## Quick start

### Linux / Proton

```bash
./farever setup
./farever start
```

`./farever setup` creates the Python venv and builds the Windows bridge
(requires Rust + the `x86_64-pc-windows-gnu` target). Start Farever through
Steam first so the Proton prefix exists. The launcher starts the bridge under
Proton, then opens Atlas.

Stop or restart later:

```bash
./farever stop
./farever restart
```

### Windows (portable exe)

Drop `dist/FareverAtlas.exe` into any folder and run it. On first launch it
creates writable runtime dirs next to itself:

```text
FareverAtlas.exe
native_bridge/          bridge binary + farever-telemetry.json
user_data/
  settings.ini
  waypoints/
  builds/
  friends/
```

No Python install is required for the portable build.

### Windows (source / venv)

Build or copy the bridge first
(`native_bridge\build.sh` targeting `x86_64-pc-windows-gnu`, or a prebuilt
`native_bridge\farever-atlas-bridge.exe`), then:

```bat
farever.bat setup
farever.bat start
```

```bat
farever.bat stop
farever.bat restart
```

## Launcher

| Command | Effect |
| --- | --- |
| `setup` | Creates `.venv`, installs Python deps, and builds the bridge (Linux) |
| `start` | Starts the native bridge, then Farever Atlas |
| `stop` | Stops Atlas and the bridge |
| `restart` | `stop`, then `start` |

Optional environment variables:

- `FAREVER_GAME_DIR` — Farever install directory
- `FAREVER_STEAM_ROOT` — Steam root used to find the Proton prefix (Linux)
- `FAREVER_PROTON` — Proton launcher path (Linux)
- `FAREVER_TELEMETRY_INTERVAL_MS` — bridge poll interval (default `100`)

Live telemetry is read from `native_bridge/farever-telemetry.json`.

## Safety

The native bridge is a read-only Windows helper. It opens Farever with
`PROCESS_QUERY_LIMITED_INFORMATION` and `PROCESS_VM_READ` only, fingerprints
known builds, and rejects unknown ones instead of guessing offsets.

On Linux it must run inside Farever’s Proton prefix via
`native_bridge/watch-proton.sh` (invoked by `./farever start`).

See [`native_bridge/README.md`](native_bridge/README.md) for build and safety
details.

## Antivirus / VirusTotal

Release builds of `FareverAtlas.exe` are submitted to VirusTotal. Some engines
may still flag the portable exe or the bundled bridge as suspicious. Those are
expected **false positives**, not evidence that Atlas modifies the game.

Why this happens:

- **PyInstaller packaging** — the Windows build is a single frozen Python exe.
  Many AV products score packed / rarely seen PyInstaller binaries poorly.
- **No code signing** — releases are not Authenticode-signed. For a small
  open-source project the certificate cost isn’t worth it, so reputation and
  heuristic scanners treat new hashes cautiously. That is normal here.
- **Read-only process access** — the native bridge opens Farever with
  `PROCESS_QUERY_LIMITED_INFORMATION` and `PROCESS_VM_READ` to sample live
  telemetry. Memory-reading helpers are often lumped with cheats or injectors
  even when they never write memory, inject code, or hook input.
- **Low prevalence** — a fresh Nightly hash has little or no prior reputation,
  so cloud AV may disagree until that build is more widely seen.

Prefer downloading from the
[Nightly release](https://github.com/wdymUsername/FareverAtlas/releases/tag/Nightly),
check the attached `.sha256`, and compare the VirusTotal badge / release notes
scan link for that exact asset. If your AV quarantines the file, add an
exclusion for the Atlas folder or restore it from quarantine after verifying
the hash.

## Development and Contributing

Issues and pull requests are welcome. Keep changes focused; say which area
you’re touching (map, FoW, bridge, Players, packaging, docs).

### Dev setup

```bash
./farever setup
./farever start --dev
```

`--dev` is mostly QoL for working on Atlas itself: a Reload button for soft
in-process UI reloads, plus FoW layer / bake authoring. It is not a full
debugger, profiler, or bridge toolkit — treat it as convenience options on
top of a normal run, not a separate development environment.
Start Farever through Steam first on Linux so the Proton
prefix exists.

Windows source workflow: build or copy `farever-atlas-bridge.exe`, then
`farever.bat setup` and `farever.bat start` (add `--dev` the same way).

Optional map-asset tooling deps:

```bash
.venv/bin/pip install -r tools/requirements.txt
```

### Guidelines

- **Read-only boundary** — the bridge must stay query / `PROCESS_VM_READ` only.
  No write memory, injection, input simulation, or networking in the helper.
  Unknown Farever builds should keep failing closed. See
  [`native_bridge/README.md`](native_bridge/README.md).
- **Style** — Python targets 3.10+; `pyproject.toml` sets Black / Ruff at
  line length 99. Match existing naming and module layout under `app/`.
- **Don’t commit local junk** — `user_data/`, telemetry JSON, `.venv/`,
  `extracted/`, bridge logs, Steam API keys, or personal waypoints / friends.
- **Assets** — prefer updating checked-in files under `assets/`. Use `tools/`
  only when rebuilding map / FoW data; that folder is not part of the portable
  ship.
- **Scope** — small PRs are easier to review. Call out WIP / Planned items from
  the Features list if you’re extending them rather than finishing them.

### Pull requests

1. Branch from `main`.
2. When your change touches live telemetry or the UI, verify against a
   supported Farever build (`--dev` is optional QoL for UI work, not required
   for every change).
3. Describe what you changed and how you tested it.
4. Portable exe / release packaging is optional for most PRs; CI builds
   Windows artifacts on relevant paths.

## Packaging and releases

Rebuild the portable exe on Linux (Wine + Windows Python + PyInstaller):

```bash
./native_bridge/build.sh
./packaging/windows/build_wine.sh
```

On native Windows with Python 3.12+:

```bat
packaging\windows\build.bat
```

The portable build ships the app, assets, and bridge only — not `tools/`.

GitHub Actions builds the same portable exe
(`.github/workflows/windows-portable.yml`) and publishes a rolling
[Nightly](https://github.com/wdymUsername/FareverAtlas/releases/tag/Nightly)
release daily at 00:00 UTC (or on demand via Actions → Run workflow).
VirusTotal submission and distribution notes live in
[`DISTRIBUTION_README.txt`](DISTRIBUTION_README.txt).

## Layout

```text
app/                 Atlas application (PySide6)
assets/              Map, icons, fonts, POI data
native_bridge/       Telemetry bridge + Proton launcher
packaging/windows/   Portable Windows exe build
tools/               Dev utilities (map / FoW rebuild, extractors; not shipped)
farever              Linux launcher
farever.bat          Windows launcher
```

Local settings, telemetry, virtualenvs, extracted game data, backups, and
character waypoint / friend files are intentionally not shipped.
