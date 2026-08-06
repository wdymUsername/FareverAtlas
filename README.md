# Farever Atlas

[![Windows portable exe](https://github.com/wdymUsername/FareverAtlas/actions/workflows/windows-portable.yml/badge.svg)](https://github.com/wdymUsername/FareverAtlas/actions/workflows/windows-portable.yml)

## Quick start

### Linux / Proton

```bash
./farever setup
./native_bridge/build.sh
./farever start
```

For UI development, start with `--dev` to get a Reload button next to
Settings. It soft-reloads Atlas Python/UI code in-process without restarting
the bridge:

```bash
./farever start --dev
```

Stop or restart later with:

```bash
./farever stop
./farever restart
```

Start Farever through Steam first so the Proton prefix exists. The launcher
starts the Windows bridge under Proton, then opens the Atlas UI.

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
```

Start Farever and log in before launching Atlas. No Python install is required
for the portable build.

Rebuild the portable exe on Linux (Wine + Windows Python + PyInstaller):

```bash
./native_bridge/build.sh
./packaging/windows/build_wine.sh
```

On a native Windows machine with Python 3.12+:

```bat
packaging\windows\build.bat
```

GitHub Actions builds the same portable exe on `windows-latest`
(`.github/workflows/windows-portable.yml`). Download the
`FareverAtlas-windows-portable` artifact from the workflow run, or the exe
attached to a GitHub Release. Manual runs: Actions → Windows portable exe →
Run workflow.

### Windows (source / venv)

```bat
farever.bat setup
farever.bat start
```

Stop or restart later with:

```bat
farever.bat stop
farever.bat restart
```

Build the bridge for Windows first (`native_bridge\build.sh` from a toolchain
that can target `x86_64-pc-windows-gnu`, or copy a prebuilt
`native_bridge\farever-atlas-bridge.exe`).

## What the launcher does

| Command | Effect |
| --- | --- |
| `setup` | Creates `.venv` and installs Python dependencies |
| `start` | Starts the native bridge, then Farever Atlas |
| `stop` | Stops Atlas and the bridge |
| `restart` | `stop`, then `start` |

Optional environment variables:

- `FAREVER_GAME_DIR` — Farever install directory
- `FAREVER_STEAM_ROOT` — Steam root used to find the Proton prefix (Linux)
- `FAREVER_PROTON` — Proton launcher path (Linux)
- `FAREVER_TELEMETRY_INTERVAL_MS` — bridge poll interval (default `100`)

Live telemetry is read from `native_bridge/farever-telemetry.json`.

## Bridge notes

The native bridge is a read-only Windows helper. On Linux it must run inside
Farever's Proton prefix via `native_bridge/watch-proton.sh` (invoked by
`./farever start`). See `native_bridge/README.md` for build and safety details.
