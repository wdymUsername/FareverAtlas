#!/usr/bin/env bash
# Launch farever-atlas-bridge.exe under Proton, joining the live game prefix
# when Farever.exe is already running. Restarts on exit or stale telemetry so
# a hung wineserver attach cannot leave Atlas stuck on a frozen report.
set -uo pipefail

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
# Restart when the report stops updating while the game is up (hung attach).
STALE_SECS="${FAREVER_BRIDGE_STALE_SECS:-5}"
RESTART_DELAY_SECS="${FAREVER_BRIDGE_RESTART_DELAY_SECS:-1}"

if [[ ! -x "$PROTON" ]]; then
    echo "Proton launcher not found: $PROTON" >&2
    exit 1
fi

if [[ ! -f "$BRIDGE" ]]; then
    echo "Bridge binary missing. Run: $ROOT/build.sh" >&2
    exit 1
fi

OUTPUT_WINDOWS="Z:${OUTPUT//\//\\}"

game_running() {
    # Match the real Wine/Proton Farever.exe (Linux path or Z:\... form).
    # Avoid matching Cursor/agent command lines that merely mention the path.
    ps -eo cmd --no-headers 2>/dev/null | awk '
        /cursorsandbox/ { next }
        /(^|\/)Farever\.exe([[:space:]]|$)/ { found=1; exit }
        /Z:.*Farever\.exe([[:space:]]|$)/ { found=1; exit }
        END { exit !found }
    '
}

telemetry_age_secs() {
    if [[ ! -f "$OUTPUT" ]]; then
        echo 9999
        return
    fi
    local now mtime
    now=$(date +%s)
    mtime=$(stat -c %Y "$OUTPUT" 2>/dev/null || echo 0)
    echo $((now - mtime))
}

kill_tree() {
    local pid="$1"
    [[ -n "$pid" ]] || return 0
    kill "$pid" 2>/dev/null || true
    # Proton wraps wine; sweep leftover bridge binaries from this attach.
    pkill -f 'farever-atlas-bridge\.exe' 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
}

cleanup() {
    if [[ -n "${CHILD_PID:-}" ]]; then
        kill_tree "$CHILD_PID"
    fi
    exit 0
}
trap cleanup INT TERM

attempt=0
while true; do
    attempt=$((attempt + 1))
    PROTON_VERB=run
    if game_running; then
        PROTON_VERB=runinprefix
    fi

    echo "$(date -Is) starting bridge (attempt=$attempt verb=$PROTON_VERB)" >&2

    env \
        STEAM_COMPAT_DATA_PATH="$COMPAT_DATA" \
        STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM_ROOT" \
        SteamAppId=3672400 \
        SteamGameId=3672400 \
        WINEDEBUG=-all \
        "$PROTON" "$PROTON_VERB" "$BRIDGE" \
        --output "$OUTPUT_WINDOWS" \
        --watch-ms "$INTERVAL_MS" &
    CHILD_PID=$!

    while kill -0 "$CHILD_PID" 2>/dev/null; do
        sleep 1
        # Only treat stale output as a hang once the game is present; otherwise
        # waiting for Farever.exe is expected and the bridge keeps rewriting.
        if game_running; then
            age=$(telemetry_age_secs)
            if (( age > STALE_SECS )); then
                echo "$(date -Is) telemetry stale (${age}s) — restarting bridge" >&2
                kill_tree "$CHILD_PID"
                CHILD_PID=""
                break
            fi
        fi
    done

    if [[ -n "${CHILD_PID:-}" ]]; then
        wait "$CHILD_PID" 2>/dev/null || true
        echo "$(date -Is) bridge exited (rc=$?) — restarting in ${RESTART_DELAY_SECS}s" >&2
        CHILD_PID=""
    fi
    sleep "$RESTART_DELAY_SECS"
done
