#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_NAME="farever-atlas-bridge.exe"

mapfile -t OLD_BRIDGE_PIDS < <(pgrep -f "$BRIDGE_NAME" || true)
for pid in "${OLD_BRIDGE_PIDS[@]}"; do
    [[ "$pid" == "$$" ]] || kill "$pid" 2>/dev/null || true
done

"$ROOT/native_bridge/watch-proton.sh" &
BRIDGE_WRAPPER_PID=$!
cleanup() {
    kill "$BRIDGE_WRAPPER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$ROOT/run.sh" "$@"
