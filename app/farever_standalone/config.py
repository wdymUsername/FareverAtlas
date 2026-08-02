"""Application constants, path discovery, and scalar helpers."""

from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path
from typing import Any

APP_ID = 3672400
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIVE_NAME = "nyx_external_live_state.json"
POI_NAME = "nyx_external_pois.json"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
DEFAULT_MAP_RELATIVE_PATH = Path("data/maps/W1_Siagarta.preview.png")
NATIVE_CALIBRATION_RELATIVE_PATH = Path("data/minimap_calibration.json")
ACTIVITY_ICON_ATLAS_RELATIVE_PATH = Path("data/icons/activities.png")
RIFT_ICON_NAME = "rift_icon_128.png"
CLASS_ICON_FILES = {
    "priest": "classPriest.webp",
    "mage": "classMage.webp",
    "warrior": "classWarrior.webp",
    "rogue": "classRogue.webp",
}
LOOSE_KIND_ICON_FILES = {
    "red_orb": "redOrb.webp",
    "plant": "plant.webp",
    "ore": "ore.webp",
}
WAYPOINT_WORLD = "W1_Siagarta"
WAYPOINT_FILE_NAME = f"user_waypoints_{WAYPOINT_WORLD}.json"
WAYPOINT_COLORS = {
    "cyan": "#55c6d8",
    "blue": "#5b91d8",
    "green": "#68bd7b",
    "yellow": "#d8bd5b",
    "orange": "#d89055",
    "red": "#d86469",
    "magenta": "#bd6fd1",
    "white": "#d8e0e8",
}
WAYPOINT_ICONS = ("pin", "diamond", "circle", "star", "flag", "cross")
DEFAULT_MOSAIC_SIZE = 11264.0

GAME_DIR_ENV = "FAREVER_GAME_DIR"


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    if sys.platform == "win32":
        candidates = [
            Path(value) / "Steam"
            for value in (
                os.environ.get("PROGRAMFILES(X86)", ""),
                os.environ.get("PROGRAMFILES", ""),
            )
            if value
        ]
        try:
            import winreg

            registry_locations = (
                (
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Valve\Steam",
                    "SteamPath",
                ),
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    r"Software\WOW6432Node\Valve\Steam",
                    "InstallPath",
                ),
            )
            for hive, key_name, value_name in registry_locations:
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        value, _kind = winreg.QueryValueEx(key, value_name)
                    if value:
                        candidates.append(Path(str(value)))
                except OSError:
                    pass
        except ImportError:
            pass
    else:
        candidates = [
            Path.home() / ".local/share/Steam",
            Path.home() / ".steam/steam",
            Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        ]

    def add(path: Path) -> None:
        path = path.expanduser()
        if path not in roots and path.exists():
            roots.append(path)

    for root in candidates:
        add(root)
        vdf = root / "steamapps/libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            add(Path(raw.replace("\\\\", "\\")))

    if sys.platform != "win32":
        # Common user-managed Steam library layouts.
        for pattern in ("Games/*/steam", "Games/*/SteamLibrary", "SteamLibrary"):
            for root in Path.home().glob(pattern):
                add(root)

    return roots


def discover_state_dir() -> Path | None:
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            candidate = Path(local_app_data) / "farever-minimap/combatlogs"
            if candidate.exists():
                return candidate
        return None

    suffix = Path(
        f"steamapps/compatdata/{APP_ID}/pfx/drive_c/users/steamuser/"
        "AppData/Local/farever-minimap/combatlogs"
    )
    for root in _steam_roots():
        candidate = root / suffix
        if candidate.exists():
            return candidate
    return None


def default_state_dir() -> Path:
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / "farever-minimap/combatlogs"
        return Path.home() / "AppData/Local/farever-minimap/combatlogs"
    return (
        Path.home()
        / f".local/share/Steam/steamapps/compatdata/{APP_ID}/pfx/"
        "drive_c/users/steamuser/AppData/Local/farever-minimap/combatlogs"
    )


def discover_game_dir() -> Path | None:
    # Highest-priority source: an explicit directory persisted by install_bridge.sh
    # or supplied by the user. This avoids relying on Steam library discovery.
    env_path = os.environ.get(GAME_DIR_ENV, "").strip()
    if env_path:
        candidate = Path(env_path).expanduser()
        if (candidate / "Farever.exe").is_file():
            return candidate.resolve()

    for root in _steam_roots():
        manifest = root / f"steamapps/appmanifest_{APP_ID}.acf"
        install_name = "Farever"
        if manifest.is_file():
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
                match = re.search(r'"installdir"\s+"([^"]+)"', text)
                if match:
                    install_name = match.group(1)
            except OSError:
                pass
        candidate = root / "steamapps/common" / install_name
        if (candidate / "Farever.exe").is_file():
            return candidate.resolve()

    # Last-resort scan for nonstandard user-managed Steam layouts. Keep the
    # search constrained to likely library roots rather than crawling all HOME.
    patterns = (
        "Games/*/steam/steamapps/common/Farever",
        "Games/*/SteamLibrary/steamapps/common/Farever",
        "SteamLibrary/steamapps/common/Farever",
    )
    for pattern in patterns:
        for candidate in Path.home().glob(pattern):
            if (candidate / "Farever.exe").is_file():
                return candidate.resolve()
    return None


def discover_project_asset(filename: str) -> Path | None:
    # Loose standalone assets belong exclusively to the project directory.
    # farever_external.py lives under <project root>/app, so ../assets is the
    # only supported loose-asset location regardless of the launch cwd.
    candidate = PROJECT_ROOT / "assets" / filename
    return candidate if candidate.is_file() else None


def discover_rift_icon() -> Path | None:
    return discover_project_asset(RIFT_ICON_NAME)


def discover_legacy_waypoint_files() -> list[Path]:
    """Find old Farever/custom-plugin waypoint files for one-time import.

    The standalone never writes these locations. They are only considered when
    its own project-local waypoint file does not yet exist.
    """

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        candidates = [
            Path.home() / WAYPOINT_FILE_NAME,
        ]
        if local_app_data:
            candidates.append(
                Path(local_app_data) / "farever-minimap" / WAYPOINT_FILE_NAME
            )
        return [candidate for candidate in candidates if candidate.is_file()]

    relative_candidates = (
        Path(
            f"steamapps/compatdata/{APP_ID}/pfx/drive_c/users/steamuser/"
            f"{WAYPOINT_FILE_NAME}"
        ),
        Path(
            f"steamapps/compatdata/{APP_ID}/pfx/drive_c/users/steamuser/"
            f"AppData/Local/farever-minimap/{WAYPOINT_FILE_NAME}"
        ),
    )
    found: list[Path] = []
    for root in _steam_roots():
        for relative in relative_candidates:
            candidate = root / relative
            if candidate.is_file() and candidate not in found:
                found.append(candidate)
    return found


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return n if math.isfinite(n) else default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def fmt_number(value: Any) -> str:
    n = safe_float(value)
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.2f}K"
    return f"{n:.1f}"


def fmt_hp(value: Any) -> str:
    """Format health-like values as the nearest whole number."""
    return str(math.floor(max(0.0, safe_float(value)) + 0.5))


def heading_degrees(radians: Any) -> float:
    return math.degrees(safe_float(radians)) % 360.0


def map_heading_degrees(radians: Any) -> float:
    """Convert Farever rot_z to north=0, east=90 map bearing.

    Farever rot_z=0 faces +Y.  Because +Y is south on the world map, the
    north-referenced bearing is the raw angle plus 180 degrees.
    """

    return (heading_degrees(radians) + 180.0) % 360.0


def cardinal(degrees: float) -> str:
    names = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return names[int((degrees + 22.5) // 45.0) % 8]
