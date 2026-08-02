#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STEAM_ROOT="${FAREVER_STEAM_ROOT:-/home/nyx/Games/nvme2/steam}"
PROTON="${FAREVER_PROTON:-$STEAM_ROOT/steamapps/common/Proton 10.0/proton}"
COMPAT_DATA="$STEAM_ROOT/steamapps/compatdata/3672400"
BRIDGE="$ROOT/target/x86_64-pc-windows-gnu/release/farever-atlas-bridge.exe"
OUTPUT="${FAREVER_BRIDGE_REPORT:-$ROOT/farever-process.json}"

if [[ ! -x "$PROTON" ]]; then
    echo "Proton launcher not found: $PROTON" >&2
    exit 1
fi

if [[ ! -f "$BRIDGE" ]]; then
    echo "Bridge binary missing. Run: $ROOT/build.sh" >&2
    exit 1
fi

OUTPUT_WINDOWS="Z:${OUTPUT//\//\\}"

exec env \
    STEAM_COMPAT_DATA_PATH="$COMPAT_DATA" \
    STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM_ROOT" \
    SteamAppId=3672400 \
    SteamGameId=3672400 \
    WINEDEBUG=-all \
    "$PROTON" run "$BRIDGE" --output "$OUTPUT_WINDOWS"
