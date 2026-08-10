#!/usr/bin/env bash
# Idempotent Cloud Agent setup for Farever Atlas (the PySide6 desktop app).
#
# The native telemetry bridge is a Windows-only, read-only game-memory reader
# and is intentionally NOT built here: it cannot run on a Linux Cloud Agent VM
# (no Farever game / Proton prefix). This prepares everything needed to develop
# and launch the Atlas GUI itself.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 1. System packages: venv tooling, the Qt/X11 runtime PySide6 links against,
#    a headless X server (Xvfb) so the GUI can run without a physical display,
#    and the Noto font family the UI prefers.
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    sudo apt-get update -qq
    sudo apt-get install -y --no-install-recommends \
        python3-venv python3-pip \
        xvfb x11-utils \
        libegl1 libgl1 libdbus-1-3 libxkbcommon0 libxkbcommon-x11-0 \
        libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render0 libxcb-render-util0 libxcb-shape0 \
        libxcb-shm0 libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 \
        libxcb-xkb1 libxcb-util1 libx11-xcb1 libxrender1 \
        libfontconfig1 libfreetype6 fonts-noto-core
fi

# 2. Python virtualenv + app dependencies (mirrors `./farever setup`, minus the
#    Windows-only bridge build).
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

# 3. Bundle the Noto Sans UI font used by the app (downloads once, then cached).
PYTHONPATH="$ROOT/app" .venv/bin/python -m farever_atlas.fonts

cat <<'EOF'

Farever Atlas setup complete.

Launch the GUI (a display is already available at :1 on Cloud Agent VMs):
  PYTHONPATH=app .venv/bin/python -m farever_atlas

Or headless with a virtual display:
  xvfb-run -a env PYTHONPATH=app .venv/bin/python -m farever_atlas

Live game telemetry needs the Windows Farever client + native bridge and is
not available on a Linux VM; the app runs in its waiting/offline state here.
EOF
