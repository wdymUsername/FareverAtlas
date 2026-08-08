# Farever Atlas native bridge

Read-only Windows telemetry helper for Farever Atlas (`farever-atlas-bridge`).

It discovers `Farever.exe` inside the same Proton / Windows process space, fingerprints the supported build, attaches with query + VM-read rights only, and writes a live snapshot to `farever-telemetry.json`. Atlas polls that file while it is fresh.

Current report version: **0.21.9** (`bridge_version` in the JSON). Release builds are a headless Windows PE (no console window).

## Safety boundary

The helper opens Farever with exactly these process permissions:

- `PROCESS_QUERY_LIMITED_INFORMATION`
- `PROCESS_VM_READ`

It does not request or contain process-memory write, remote-thread, injection, input-simulation, or networking functionality.

Each `ReadProcessMemory` call is capped at **4096** bytes. Unknown or partially matching Farever / `hlboot.dat` builds are rejected instead of guessed.

## Supported build

Live telemetry is gated on a complete known-build profile (`farever-2026-07-20`):

| Check | Source |
| --- | --- |
| PE machine, timestamp, image size, file size, CRC32 | on-disk `Farever.exe` |
| Loaded image size vs PE | process module list |
| DOS / PE signatures | live PE header reads for `Farever.exe` and `libhl.dll` |
| HashLink bytecode version, file size, CRC32 | on-disk `hlboot.dat` |
| Live `hl_code` header counts / entrypoint | runtime main-context anchor |

Field offsets are derived from HashLink type metadata for that bytecode, never hard-coded absolute game addresses. Offline findings live in [`HLBOOT_FINDINGS.md`](HLBOOT_FINDINGS.md); inspect bytecode with `tools/hlboot_inspect.py`.

## Watch telemetry

`--output PATH --watch-ms N` validates and attaches once, then refreshes the snapshot at interval `N` (50–5000 ms; default launcher uses **100** ms / 10 Hz).

States:

- `waiting` — Farever not running, unsupported build, or player / world roots not ready yet (`message` explains why)
- `connected` — live sample written

Discovery, fingerprinting, and HashLink metadata traversal happen once per attach. Soft sample failures (loading, teleport, GC) keep the attach and emit `waiting` until roots recover; hard attach failures (or a long soft-failure streak) detach and wait again.

### Connected snapshot fields

| Field | Contents |
| --- | --- |
| `player` | name, uid, class, level, combat flag, vitality / health / shield / special energy (HUD gauges used when available) |
| `position`, `rotation_z` | local hero transform |
| `camera_yaw` | world camera yaw when readable, else `null` |
| `party` | up to 3 other group members (name, class, vitals, position, distance) |
| `enemies` | nearby non-summon `ent.Foe` markers (id, kind, position; ~500 m / 120 z cull) |
| `players` | other layer heroes outside the party (uncapped distance; display/sort only) |
| `interactibles` | nearby gatherables / chests (`kind`: ore, plant, chest, gatherable) |
| `instance` | coarse map bucket (`world` / `rift` / `dungeon` / `instance` / `unknown`) plus `map_id` and flags |
| `completed_elements` | completion keys from player progress (refreshed periodically) |
| `dps` | observed nearby foe-health delta (`mode: observed_nearby`), not skill-parsed combat log |

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

Requires a `x86_64-pc-windows-gnu` Rust toolchain (and MinGW linker as usual for that target).

## Run under Proton

Prefer the repo launcher, which starts the bridge and Atlas together:

```bash
../farever start
```

Bridge-only continuous telemetry:

```bash
./watch-proton.sh
```

Override Steam / Proton / output / interval without editing the script:

```bash
FAREVER_STEAM_ROOT=/path/to/steam \
FAREVER_PROTON="/path/to/proton" \
FAREVER_TELEMETRY_REPORT=/path/to/farever-telemetry.json \
FAREVER_TELEMETRY_INTERVAL_MS=100 \
./watch-proton.sh
```

Steam app id / compatdata used by the script: `3672400`.

## CLI

```text
farever-atlas-bridge.exe [--output PATH] [--watch-ms MS]
```

- No `--watch-ms`: one-shot discovery / attach report on stdout (and optionally to `--output`)
- `--watch-ms` requires `--output`: continuous telemetry loop described above

## Layout

```text
src/main.rs              bridge implementation
build.sh                 release cross-build + copy next to this README
watch-proton.sh          Proton wrapper for watch mode
tools/hlboot_inspect.py  offline HashLink bytecode inspector
HLBOOT_FINDINGS.md       offline type / anchor notes
farever-telemetry.json   live snapshot (local; do not commit)
```
