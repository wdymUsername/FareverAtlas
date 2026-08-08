FAREVER ATLAS
=============

Atlas and its native telemetry bridge are read-only. Start Farever and log in
to a character before starting Atlas.

WINDOWS (PORTABLE EXE)
----------------------
1. Copy FareverAtlas.exe into any folder.
2. Start Farever and log in to a character.
3. Run FareverAtlas.exe.

On first launch Atlas creates next to the exe:

  native_bridge/   bridge + farever-telemetry.json
  user_data/       settings.ini, waypoints/, builds/

No Python install is required for the portable build.

Rebuild from a Linux host with Wine:

  ./native_bridge/build.sh
  ./packaging/windows/build_wine.sh

Or on native Windows with Python 3.12+:

  packaging\windows\build.bat

GitHub Actions also builds dist/FareverAtlas.exe
(.github/workflows/windows-portable.yml).

Nightly release (rolling; attaches FareverAtlas.exe + .sha256):

  - automatic: every day at 00:00 UTC
  - manual: Actions → Windows portable exe → Run workflow

Download: https://github.com/wdymUsername/FareverAtlas/releases/tag/Nightly

Push/PR CI runs still upload the FareverAtlas-windows-portable artifact
without updating Nightly.

WINDOWS (SOURCE / VENV)
-----------------------
1. Install 64-bit Python 3.10 or newer if Python is not already installed.
2. Run: farever.bat setup
3. Run: farever.bat start

Stop or restart later with:

  farever.bat stop
  farever.bat restart

LINUX / PROTON
--------------
1. Install Python 3, its venv module, and Wine/Proton prerequisites.
2. Run: ./farever setup
3. Build the bridge once: ./native_bridge/build.sh
4. Start Farever through Steam and log in.
5. Run: ./farever start

Stop or restart later with:

  ./farever stop
  ./farever restart

The Linux launcher searches the common Steam locations automatically. For a
custom Steam library or Proton build:

  FAREVER_STEAM_ROOT=/path/to/steam ./farever start

or:

  FAREVER_PROTON=/path/to/proton ./farever start

`farever start` starts both the bridge and Atlas. It stops an older bridge
instance before launching a new one, preventing duplicate telemetry processes.

CONTENTS
--------
- app/                   Atlas application
- assets/                map, icons, calibration, and POI data
- native_bridge/         compiled bridge and Proton launcher
- packaging/windows/     portable Windows exe build (Wine or native)
- dist/FareverAtlas.exe  portable Windows build output (when built)
- tools/                 extraction/development utilities
- farever / farever.bat  setup, start, stop, and restart

Local settings, generated telemetry, virtual environments, extracted game
data, backups, and character waypoint files are intentionally not included.
