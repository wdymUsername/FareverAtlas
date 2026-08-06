#!/usr/bin/env bash
# Build dist/FareverAtlas.exe on Linux using Wine + Windows Python + PyInstaller.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
WINEPREFIX="${WINEPREFIX:-$HOME/.wine}"
export WINEPREFIX
export WINEDEBUG="${WINEDEBUG:--all}"
PYTHON_VERSION="${FAREVER_WIN_PYTHON_VERSION:-3.12.10}"
PYTHON_INSTALLER="python-${PYTHON_VERSION}-amd64.exe"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_INSTALLER}"
CACHE_DIR="${FAREVER_BUILD_CACHE:-$ROOT/.cache/windows-build}"
INSTALLER_PATH="$CACHE_DIR/$PYTHON_INSTALLER"
BRIDGE_DST="$ROOT/native_bridge/farever-atlas-bridge.exe"
BRIDGE_BUILT="$ROOT/native_bridge/target/x86_64-pc-windows-gnu/release/farever-atlas-bridge.exe"
DIST_DIR="$ROOT/dist"
WORK_DIR="$ROOT/build/pyinstaller"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

wine_python() {
    # Prefer a freshly installed Python 3.12 under the Wine prefix.
    local candidates=(
        "$WINEPREFIX/drive_c/users/$USER/AppData/Local/Programs/Python/Python312/python.exe"
        "$WINEPREFIX/drive_c/Python312/python.exe"
        "$WINEPREFIX/drive_c/Program Files/Python312/python.exe"
        "$WINEPREFIX/drive_c/Program Files (x86)/Python312/python.exe"
    )
    local path
    for path in "${candidates[@]}"; do
        if [[ -f "$path" ]]; then
            printf '%s\n' "$path"
            return 0
        fi
    done
    # Fall back to whatever `python` resolves to inside Wine.
    if wine python --version >/dev/null 2>&1; then
        printf 'python\n'
        return 0
    fi
    return 1
}

ensure_bridge() {
    if [[ -f "$BRIDGE_DST" ]]; then
        return 0
    fi
    if [[ -f "$BRIDGE_BUILT" ]]; then
        cp -f "$BRIDGE_BUILT" "$BRIDGE_DST"
        return 0
    fi
    echo "Building native bridge for Windows..."
    "$ROOT/native_bridge/build.sh"
    [[ -f "$BRIDGE_BUILT" ]] || die "Bridge build did not produce $BRIDGE_BUILT"
    cp -f "$BRIDGE_BUILT" "$BRIDGE_DST"
}

ensure_windows_python() {
    if wine_python >/dev/null; then
        return 0
    fi

    need_cmd curl
    mkdir -p "$CACHE_DIR"
    if [[ ! -f "$INSTALLER_PATH" ]]; then
        echo "Downloading Windows Python ${PYTHON_VERSION}..."
        curl -fL --retry 3 -o "$INSTALLER_PATH.partial" "$PYTHON_URL"
        mv "$INSTALLER_PATH.partial" "$INSTALLER_PATH"
    fi

    echo "Installing Windows Python under Wine (quiet)..."
    # Pre-create the wine prefix non-interactively if needed.
    wineboot -u >/dev/null 2>&1 || true
    wine "$INSTALLER_PATH" \
        /quiet \
        InstallAllUsers=0 \
        PrependPath=1 \
        Include_test=0 \
        Include_launcher=1 \
        SimpleInstall=1
    wine_python >/dev/null || die "Windows Python install finished but python.exe was not found"
}

run_wine_python() {
    local py
    py="$(wine_python)" || die "Windows Python not available"
    if [[ "$py" == "python" ]]; then
        wine python "$@"
    else
        wine "$py" "$@"
    fi
}

ensure_ui_fonts() {
    local python="${PYTHON:-python3}"
    if [[ -x "$ROOT/.venv/bin/python" ]]; then
        python="$ROOT/.venv/bin/python"
    fi
    echo "Preparing UI fonts (Noto Sans)..."
    PYTHONPATH="$ROOT/app${PYTHONPATH:+:$PYTHONPATH}" \
        "$python" -m farever_atlas.fonts
}

main() {
    need_cmd wine
    need_cmd wineboot
    ensure_bridge
    ensure_ui_fonts
    ensure_windows_python

    echo "Using Wine Python: $(wine_python)"
    run_wine_python -m pip install --upgrade pip
    run_wine_python -m pip install -r "$(winepath -w "$ROOT/requirements.txt")" pyinstaller

    mkdir -p "$DIST_DIR" "$WORK_DIR"
    local win_root win_dist win_work win_spec
    win_root="$(winepath -w "$ROOT")"
    win_dist="$(winepath -w "$DIST_DIR")"
    win_work="$(winepath -w "$WORK_DIR")"
    win_spec="$(winepath -w "$ROOT/packaging/windows/farever_atlas.spec")"

    echo "Running PyInstaller..."
    run_wine_python -m PyInstaller \
        --noconfirm \
        --clean \
        --distpath "$win_dist" \
        --workpath "$win_work" \
        "$win_spec"

    [[ -f "$DIST_DIR/FareverAtlas.exe" ]] || die "PyInstaller finished without $DIST_DIR/FareverAtlas.exe"
    echo
    echo "Built: $DIST_DIR/FareverAtlas.exe"
    file "$DIST_DIR/FareverAtlas.exe" || true
    ls -lh "$DIST_DIR/FareverAtlas.exe"
}

main "$@"
