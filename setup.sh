#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
VENV_PYTHON="$ROOT/.venv/bin/python"

cd "$ROOT"
"$PYTHON" -m venv .venv
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt

printf '\nSetup complete. Start with:\n  %q/run.sh\n' "$ROOT"
