"""Checkout/exe-local runtime layout: user_data/, bridge lifecycle, paths.

All mutable user/machine state lives under ``PROJECT_ROOT/user_data/`` for both
source installs and the frozen portable exe. Nothing is written to a shared
``~/.config`` / AppData org store.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import PROJECT_ROOT

BRIDGE_NAME = "farever-atlas-bridge.exe"
TELEMETRY_NAME = "farever-telemetry.json"
_bridge_process: subprocess.Popen[bytes] | None = None
_bridge_stopped = False


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def user_data_dir() -> Path:
    return PROJECT_ROOT / "user_data"


def ensure_portable_dirs() -> None:
    """Create writable runtime directories under this checkout / exe folder."""
    for relative in (
        Path("user_data"),
        Path("user_data") / "waypoints",
        Path("user_data") / "builds",
        Path("user_data") / "friends",
        Path("user_data") / "friends" / "cache",
        Path("user_data") / "map",
        Path("native_bridge"),
    ):
        (PROJECT_ROOT / relative).mkdir(parents=True, exist_ok=True)


def settings_ini_path() -> Path:
    return user_data_dir() / "settings.ini"


def instance_lock_path() -> Path:
    return user_data_dir() / "farever-atlas.lock"


def game_dir_conf_path() -> Path:
    """Optional Farever install path override (one line)."""
    return user_data_dir() / "game_dir.conf"


def resolve_game_dir_conf() -> Path | None:
    """Return the game-dir override file, migrating legacy names if needed."""
    current = game_dir_conf_path()
    if current.is_file():
        return current

    legacy_candidates = (
        user_data_dir() / "nyx_game_dir.conf",
        PROJECT_ROOT / "nyx_game_dir.conf",
        PROJECT_ROOT / "game_dir.conf",
    )
    for legacy in legacy_candidates:
        if not legacy.is_file():
            continue
        try:
            current.parent.mkdir(parents=True, exist_ok=True)
            legacy.replace(current)
            return current
        except OSError:
            return legacy
    return None


def _windows_no_window_flags() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _run_hidden(args: list[str]) -> None:
    """Run a helper process without flashing a console window on Windows."""
    subprocess.run(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        creationflags=_windows_no_window_flags(),
    )


def _bundled_bridge_source() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    candidate = Path(meipass) / "native_bridge" / BRIDGE_NAME
    return candidate if candidate.is_file() else None


def ensure_bridge_binary() -> Path:
    """Copy the bundled bridge beside the exe when missing or stale."""
    dest = PROJECT_ROOT / "native_bridge" / BRIDGE_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = _bundled_bridge_source()
    if source is None:
        if dest.is_file():
            return dest
        raise FileNotFoundError(
            f"Bridge binary missing: {dest} (no bundled copy available)"
        )
    if (
        not dest.is_file()
        or dest.stat().st_size != source.stat().st_size
        or dest.stat().st_mtime < source.stat().st_mtime
    ):
        shutil.copy2(source, dest)
    return dest


def _kill_existing_bridges() -> None:
    if sys.platform == "win32":
        # taskkill is a console app; CREATE_NO_WINDOW prevents the flash.
        _run_hidden(["taskkill", "/IM", BRIDGE_NAME, "/F"])
        return
    _run_hidden(["pkill", "-f", BRIDGE_NAME])


def start_bridge(interval_ms: int | None = None) -> subprocess.Popen[bytes]:
    """Start the native bridge writing telemetry under PROJECT_ROOT."""
    global _bridge_process, _bridge_stopped

    bridge = ensure_bridge_binary()
    telemetry = PROJECT_ROOT / "native_bridge" / TELEMETRY_NAME
    if interval_ms is None:
        raw = os.environ.get("FAREVER_TELEMETRY_INTERVAL_MS", "100").strip()
        try:
            interval_ms = max(1, int(raw))
        except ValueError:
            interval_ms = 100

    _kill_existing_bridges()
    _bridge_stopped = False
    _bridge_process = subprocess.Popen(
        [
            str(bridge),
            "--output",
            str(telemetry),
            "--watch-ms",
            str(interval_ms),
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_windows_no_window_flags(),
    )
    atexit.register(stop_bridge)
    return _bridge_process


def stop_bridge() -> None:
    """Stop the bridge child started by this process, then any leftovers."""
    global _bridge_process, _bridge_stopped
    if _bridge_stopped:
        return
    _bridge_stopped = True
    proc = _bridge_process
    _bridge_process = None
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    # Sweep leftovers with a hidden taskkill so Windows never flashes a console.
    _kill_existing_bridges()


def bootstrap_frozen() -> None:
    """Prepare portable layout and start the bridge when running frozen."""
    if not is_frozen():
        return
    ensure_portable_dirs()
    start_bridge()
