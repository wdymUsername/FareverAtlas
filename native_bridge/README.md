# Farever Atlas native bridge

This is the experimental, read-only Windows telemetry helper for Farever Atlas.

Version 0.10.0 performs deliberately bounded live-memory reads. It
reads at most 4096 bytes per call and currently uses that ability only to
verify the DOS and PE signatures of the already-enumerated `Farever.exe` and
`libhl.dll` modules and validate the supported build's HashLink main-context
anchor. The anchor reads the 40-byte `main_context`, verifies its `hlboot.dat`
file pointer, and cross-checks that `hl_module->code` matches its `hl_code`
pointer. It then validates the live `hl_code` counts against offline bytecode
metadata and resolves the `st.Player`, `ent.Hero`, and `st.Group` type
metadata. For each known object global, it derives the value slot from the
module's global index table and cross-checks it against the type metadata's
`global_value` pointer. It also verifies that the populated values are the
expected generated static holders: `st.$Player`, `ent.$Hero`, and `st.$Group`.
It does not mistake those holders for character instances. Offline bytecode
tracing then establishes `global[955] -> $App.inst -> GameApp`, whose live
`me` and `hero` pointers are type-checked. The helper currently reads the
Hero's `posx`, `posy`, `posz`, `rotationZ`, level, attributes pointer, and raw
health-resource fields. The current Player name is also sampled with a bounded
string read, but consumers reject it until its HashLink representation is
fully decoded. Watch mode validates
and attaches once, then refreshes the live root pointers and those four values
at a controlled interval. Atlas reads this snapshot from
`farever-telemetry.json` while it is fresh.
It is intended to run inside the same Proton prefix as `Farever.exe`.
Release builds are a headless Windows PE (no console window); launchers start
it in the background and Atlas consumes `farever-telemetry.json`.

The first milestone only discovers the Farever process and reports its main
module metadata as JSON. It does not inspect game structures.

Before any future structure reader is allowed to run, the helper validates the
on-disk executable against a complete known-build profile:

- PE machine type
- PE timestamp
- loaded image size
- file size
- CRC32

An unknown or partially matching build is rejected instead of being handled
with guessed offsets.

The discovery report also enumerates all modules loaded by Farever. Files loaded
from the Farever installation directory receive the same on-disk fingerprint;
Windows and Proton system modules are listed without being hashed. This remains
metadata-only discovery and does not call `ReadProcessMemory`.

`hlboot.dat` is also gated by its HashLink bytecode version, file size, and
CRC32. See `HLBOOT_FINDINGS.md` for the offline type metadata extracted with
`tools/hlboot_inspect.py`.

## Safety boundary

The helper opens Farever with exactly these Windows process permissions:

- `PROCESS_QUERY_LIMITED_INFORMATION`
- `PROCESS_VM_READ`

It does not request or contain process-memory write, remote-thread, injection,
input-simulation, or networking functionality.

If the process or module cannot be identified safely, it exits with an error
instead of guessing.

## Build

From this directory:

```bash
./build.sh
```

The Windows binary is written to:

```text
target/x86_64-pc-windows-gnu/release/farever-atlas-bridge.exe
```

## Run under Proton

Prefer the repo launcher, which starts the bridge and Atlas together:

```bash
../farever start
```

For bridge-only continuous telemetry:

```bash
./watch-proton.sh
```

It writes `farever-telemetry.json` at 10 Hz by default. Override the interval
(minimum 50 ms) with `FAREVER_TELEMETRY_INTERVAL_MS`. Watch mode stays running
even when Farever is closed or the player is not in a world: it emits
`state: waiting` until attach succeeds, then samples live data. If the game
process exits, it detaches and waits again. Discovery, build fingerprinting,
and HashLink metadata traversal happen once per attach; the watch loop
revalidates root pointers and reads transform fields while connected.

Steam / Proton discovery can be overridden without editing the script:

```bash
FAREVER_STEAM_ROOT=/path/to/steam \
FAREVER_PROTON="/path/to/proton" \
./watch-proton.sh
```
