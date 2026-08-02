# Farever Standalone v0.12.2

## Windows

Farever Standalone supports native Windows installations in addition to
Linux/Proton.

1. Install 64-bit Python 3.10 or newer.
2. Run `setup.bat`.
3. Run `install_bridge.bat`. If Farever is in a nonstandard location, pass it
   explicitly:

   ```bat
   install_bridge.bat "D:\SteamLibrary\steamapps\common\Farever"
   ```

4. Start Farever, then run `run.bat`.

On Windows, live telemetry is read from:

```text
%LOCALAPPDATA%\farever-minimap\combatlogs
```

The launcher uses `nyx_game_dir.conf` when present and otherwise searches
Windows Steam libraries. The same project-local assets and waypoint JSON file
are used on both platforms.

## Linux / Proton

Run `setup.sh`, `install_bridge.sh`, and `run.sh` as before.

## Bridge v0.11.1

- Reduced complete live-state polling and JSON writes from 10 Hz to 5 Hz.
- Standalone map interpolation remains smooth while the game performs roughly
  half as many telemetry API reads and file writes.

## v0.12.2

- Confined the floating WAYPOINTS panel to the visible map canvas.
- Kept the WAYPOINTS header pinned while the panel body scrolls.
- Added a compact vertical scrollbar when expanded filters and custom waypoints
  exceed the available map height.
- Recalculates the panel limit while the window is resized and during roll
  animations, preventing any part of the panel from escaping the map.

Changes from v0.11.7:

- Removed the outline and backing plate from the class artwork; the project-local WebP is now shown cleanly inside the existing 30 px icon area.
- HP value text now switches contrast automatically:
  - dark text over a mostly filled bright HP/shield bar
  - light text over the dark empty track at low health
- The HP bar width now follows the visible identity-line width, within compact limits, so the lower row no longer extends substantially farther right than the upper row.
- Character/Rift vertical alignment and shield overlay behavior are unchanged.


## v0.12.1

- Restored the `Snapshot` dataclass constructor lost during the v0.12.0 module split.
- Added packaging validation for positional and keyword snapshot construction.
