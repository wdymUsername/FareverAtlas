FAREVER ATLAS
=============

Atlas and its native telemetry bridge are read-only. Start Farever and log in
to a character before starting Atlas.

WINDOWS
-------
1. Install 64-bit Python 3.10 or newer if Python is not already installed.
2. Run SETUP_WINDOWS.bat once.
3. Run START_WINDOWS.bat whenever you want to use Atlas.

LINUX / PROTON
--------------
1. Install Python 3, its venv module, and Wine/Proton prerequisites.
2. Run SETUP_LINUX.sh once.
3. Start Farever through Steam and log in.
4. Run START_LINUX.sh.

The Linux launcher searches the common Steam locations automatically. For a
custom Steam library or Proton build, launch it like this:

  FAREVER_STEAM_ROOT=/path/to/steam START_LINUX.sh

or:

  FAREVER_PROTON=/path/to/proton START_LINUX.sh

The START launchers start both the bridge and Atlas. They stop an older Atlas
bridge instance before launching a new one, preventing duplicate telemetry
processes.

CONTENTS
--------
- app/                 Atlas application
- assets/              map, icons, calibration, and POI data
- native_bridge/       compiled bridge and Proton launcher
- tools/               extraction/development utilities
- setup/run scripts    individual and combined launch options

Local settings, generated telemetry, virtual environments, extracted game
data, backups, and character waypoint files are intentionally not included.
