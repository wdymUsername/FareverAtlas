"""Portable frozen-app bootstrap: dirs, bridge lifecycle, settings paths."""

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


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def ensure_portable_dirs() -> None:
    """Create writable runtime directories next to the executable / project root."""
    for relative in (
        Path("user_data") / "waypoints",
        Path("user_data") / "builds",
        Path("native_bridge"),
    ):
        (PROJECT_ROOT / relative).mkdir(parents=True, exist_ok=True)


def settings_ini_path() -> Path:
    return PROJECT_ROOT / "user_data" / "settings.ini"


def instance_lock_path() -> Path:
    return PROJECT_ROOT / "user_data" / "farever-atlas.lock"


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
        subprocess.run(
            ["taskkill", "/IM", BRIDGE_NAME, "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    subprocess.run(
        ["pkill", "-f", BRIDGE_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def start_bridge(interval_ms: int | None = None) -> subprocess.Popen[bytes]:
    """Start the native bridge writing telemetry under PROJECT_ROOT."""
    global _bridge_process

    bridge = ensure_bridge_binary()
    telemetry = PROJECT_ROOT / "native_bridge" / TELEMETRY_NAME
    if interval_ms is None:
        raw = os.environ.get("FAREVER_TELEMETRY_INTERVAL_MS", "100").strip()
        try:
            interval_ms = max(1, int(raw))
        except ValueError:
            interval_ms = 100

    _kill_existing_bridges()
    creationflags = 0
    if sys.platform == "win32":
        # Hide the console window but keep the child attached so we can stop it.
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

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
        creationflags=creationflags,
    )
    atexit.register(stop_bridge)
    return _bridge_process


def stop_bridge() -> None:
    """Stop the bridge child started by this process, then any leftovers."""
    global _bridge_process
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
    _kill_existing_bridges()


def bootstrap_frozen() -> None:
    """Prepare portable layout and start the bridge when running frozen."""
    if not is_frozen():
        return
    ensure_portable_dirs()
    start_bridge()
