# Farever Atlas native bridge

Read-only Windows telemetry helper for Farever Atlas (`farever-atlas-bridge`).

It discovers `Farever.exe` inside the same Proton / Windows process space,
fingerprints the supported build, attaches with query + VM-read rights only, and
writes a live snapshot to `farever-telemetry.json`. Atlas polls that file while
it is fresh.

Current report version: **0.24.1** (`bridge_version` in the JSON, from
`Cargo.toml`). Release builds are a headless Windows PE (no console window).

## Safety boundary

The helper opens Farever with exactly these process permissions:

- `PROCESS_QUERY_LIMITED_INFORMATION`
- `PROCESS_VM_READ`

It does not request or contain process-memory write, remote-thread, injection,
input-simulation, or networking functionality.

Each `ReadProcessMemory` call is capped at **4096** bytes. Unknown or partially
matching Farever / `hlboot.dat` builds are rejected instead of guessed.

## Supported build

Live telemetry is gated on a complete known-build profile (`farever-2026-07-20`):

| Check | Source |
| --- | --- |
| PE machine, timestamp, image size, file size, CRC32 | on-disk `Farever.exe` |
| Loaded image size vs PE | process module list |
| DOS / PE signatures | live PE header reads for `Farever.exe` and `libhl.dll` |
| HashLink bytecode version, file size, CRC32 | on-disk `hlboot.dat` |
| Live `hl_code` header counts / entrypoint | runtime main-context anchor |

Field offsets are derived from HashLink type metadata for that bytecode, never
hard-coded absolute game addresses. Offline findings live in
[`HLBOOT_FINDINGS.md`](HLBOOT_FINDINGS.md); inspect bytecode with
`tools/hlboot_inspect.py`.

## Watch telemetry

`--output PATH --watch-ms N` validates and attaches once, then refreshes the
snapshot at interval `N` (50–5000 ms; default launcher uses **100** ms / 10 Hz).
The loop holds to a fixed cadence (missed deadlines are dropped, not stacked).

States:

- `waiting` — Farever not running, unsupported build, or player / world roots
  not ready yet (`message` explains why)
- `connected` — live sample written

Discovery, fingerprinting, and HashLink metadata traversal happen once per
attach. Soft sample failures (loading, teleport, GC) keep the attach and emit
`waiting` until roots recover; hard attach failures (or a long soft-failure
streak) detach and wait again.

### Connected snapshot fields

| Field | Contents |
| --- | --- |
| `player` | name, uid, class, level, combat flag, vitality / health / shield / special energy (HUD gauges when available); `currencies` (`kind` / `amount` purse rows from loadout, HeroData fallback); `currency_counters` (progress counters for tiered caps, currently `DemonicSouls_CapacityIndex`) |
| `position`, `rotation_z` | local hero transform |
| `camera_yaw` | world camera yaw when readable, else `null` |
| `party` | up to 3 other group members (name, class, vitals, position, distance) |
| `enemies` | nearby non-summon combat `ent.Foe` markers (id, kind, spark, elite, boss, miniboss, unique, position; ~500 m / 120 z cull, max 150). Companion critters are excluded. Rank flags come from CastleDB `unit.flags` kind lists baked into the bridge (see `assets/unit_traits.json` / `tools/extract_unit_traits.py`). |
| `critters` | Wild Critter-kind `ent.Foe` markers (id, kind, spark, elite, boss, miniboss, unique, position; full layer like `players` — units + entities, no range cull, max 120). Player-owned companion pets (`Foe.summonOwner`) are excluded. |
| `players` | other layer heroes outside the party (uncapped distance; display/sort only; max 400) |
| `interactibles` | nearby gatherables / chests (`kind`: ore, plant, chest, gatherable; ~500 m / 160 z cull, max 200) |
| `instance` | coarse map bucket (`world` / `rift` / `dungeon` / `instance` / `unknown`) plus `map_id` and flags |
| `time_of_day` | day cycle from `world.World.timeOfDay` (`factor` 0–1, `elapsed`, `speed`, `paused`), or `null` |
| `ui` | open game UI windows from `ui.BaseUI.windows` (`open` bool + short class names such as `MapWindow`) |
| `completed_elements` | completion keys from player progress (refreshed periodically) |
| `completed_activities` | finished world-activity keys from `Progress.activities` (refreshed periodically) |
| `collection` | account-wide owned ids: `mounts`, `gliders`, `pets`, `gears` (refreshed every ~30 samples) |
| `codex_units` | per-unit hunting-log map `id → { kills, rank }` from `Progress.unitsProgress` (refreshed every ~30 samples) |
| `dps` | extremely rough nearby foe-health delta (`mode: observed_nearby`); UI exists but values should not be taken at face value — not a skill-parsed combat log |

## Build

From this directory (Linux cross-compile to Windows):

```bash
./build.sh
```

Writes:

```text
farever-atlas-bridge.exe
target/x86_64-pc-windows-gnu/release/farever-atlas-bridge.exe
```

Requires a `x86_64-pc-windows-gnu` Rust toolchain (and MinGW linker as usual for
that target).

## Run under Proton

Prefer the repo launcher, which starts the bridge and Atlas together:

```bash
../farever start
```

Bridge-only continuous telemetry:

```bash
./watch-proton.sh
```

`watch-proton.sh` joins Farever’s Proton prefix and restarts the bridge if the
telemetry file goes stale while the game is still running.

Override Steam / Proton / output / interval without editing the script:

```bash
FAREVER_STEAM_ROOT=/path/to/steam \
FAREVER_PROTON="/path/to/proton" \
FAREVER_TELEMETRY_REPORT=/path/to/farever-telemetry.json \
FAREVER_TELEMETRY_INTERVAL_MS=100 \
FAREVER_BRIDGE_STALE_SECS=5 \
FAREVER_BRIDGE_RESTART_DELAY_SECS=1 \
./watch-proton.sh
```

Optional bridge profiling (any value enables it):

```bash
FAREVER_BRIDGE_PROFILE=1 ./watch-proton.sh
```

Writes mean per-phase timings beside the telemetry output as
`*.profile.txt` (Proton often swallows stderr).

Steam app id / compatdata used by the script: `3672400`.

## CLI

```text
farever-atlas-bridge.exe [--output PATH] [--watch-ms MS]
```

- No `--watch-ms`: one-shot discovery / attach report on stdout (and optionally
  to `--output`)
- `--watch-ms` requires `--output`: continuous telemetry loop described above

## Layout

```text
src/main.rs              bridge implementation
build.sh                 release cross-build + copy next to this README
watch-proton.sh          Proton wrapper for watch mode (stale-restart)
tools/hlboot_inspect.py  offline HashLink bytecode inspector
HLBOOT_FINDINGS.md       offline type / anchor notes
farever-telemetry.json   live snapshot (local; do not commit)
*.profile.txt            optional phase timings when FAREVER_BRIDGE_PROFILE is set
```
