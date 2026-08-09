#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${FAREVER_STEAM_ROOT:-}" ]]; then
    STEAM_ROOT="$FAREVER_STEAM_ROOT"
else
    for candidate in \
        "$HOME/.steam/steam" \
        "$HOME/.local/share/Steam" \
        "$HOME"/Games/*/steam \
        "$HOME"/Games/*/*/steam; do
        if [[ -d "$candidate/steamapps/compatdata/3672400" ]]; then
            STEAM_ROOT="$candidate"
            break
        fi
    done
    : "${STEAM_ROOT:=$HOME/.steam/steam}"
fi
if [[ -n "${FAREVER_PROTON:-}" ]]; then
    PROTON="$FAREVER_PROTON"
else
    PROTON="$STEAM_ROOT/steamapps/common/Proton 10.0/proton"
    if [[ ! -x "$PROTON" ]]; then
        for candidate in "$STEAM_ROOT"/steamapps/common/Proton*/proton; do
            if [[ -x "$candidate" ]]; then
                PROTON="$candidate"
            fi
        done
    fi
fi
COMPAT_DATA="$STEAM_ROOT/steamapps/compatdata/3672400"
BRIDGE="$ROOT/farever-atlas-bridge.exe"
if [[ ! -f "$BRIDGE" ]]; then
    BRIDGE="$ROOT/target/x86_64-pc-windows-gnu/release/farever-atlas-bridge.exe"
fi
OUTPUT="${FAREVER_TELEMETRY_REPORT:-$ROOT/farever-telemetry.json}"
INTERVAL_MS="${FAREVER_TELEMETRY_INTERVAL_MS:-100}"

if [[ ! -x "$PROTON" ]]; then
    echo "Proton launcher not found: $PROTON" >&2
    exit 1
fi

if [[ ! -f "$BRIDGE" ]]; then
    echo "Bridge binary missing. Run: $ROOT/build.sh" >&2
    exit 1
fi

OUTPUT_WINDOWS="Z:${OUTPUT//\//\\}"

# Join the live Farever wineserver when the game is already running. Plain
# `proton run` from outside SteamLinuxRuntime can attach to a stale view where
# hero/world pointers look valid but GameLayer.units stays empty and frozen.
PROTON_VERB=run
if pgrep -f '(^|/)Farever\.exe([[:space:]]|$)' >/dev/null 2>&1; then
    PROTON_VERB=runinprefix
fi

exec env \
    STEAM_COMPAT_DATA_PATH="$COMPAT_DATA" \
    STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM_ROOT" \
    SteamAppId=3672400 \
    SteamGameId=3672400 \
    WINEDEBUG=-all \
    "$PROTON" "$PROTON_VERB" "$BRIDGE" --output "$OUTPUT_WINDOWS" --watch-ms "$INTERVAL_MS"
