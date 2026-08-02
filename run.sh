#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "Virtual environment missing. Run: $ROOT/setup.sh" >&2
    exit 1
fi

# install_bridge.sh records the exact Farever directory here. This file stays
# beside the standalone app and does not add another file to the game folder.
GAME_DIR_FILE="$ROOT/nyx_game_dir.conf"
if [[ -z "${FAREVER_GAME_DIR:-}" && -f "$GAME_DIR_FILE" ]]; then
    IFS= read -r FAREVER_GAME_DIR < "$GAME_DIR_FILE" || true
    export FAREVER_GAME_DIR
fi

export PYTHONPATH="$ROOT/app${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m farever_standalone "$@"
