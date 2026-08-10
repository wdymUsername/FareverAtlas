"""Application constants, path discovery, and scalar helpers."""

from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path
from typing import Any

APP_ID = 3672400


def _resolve_project_root() -> Path:
    """Writable portable root (exe folder when frozen; repo root otherwise)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _resolve_asset_root() -> Path:
    """Read-only bundled assets (PyInstaller extract dir when frozen)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "assets"
    return _resolve_project_root() / "assets"


PROJECT_ROOT = _resolve_project_root()
ASSET_ROOT = _resolve_asset_root()
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# --- Shipped asset paths (relative to ASSET_ROOT) ---
DEFAULT_MAP_RELATIVE_PATH = Path("map/w1_siagarta.webp")
NATIVE_CALIBRATION_RELATIVE_PATH = Path("map/w1_siagarta.json")
FOW_REGIONS_RELATIVE_PATH = Path("map/w1_siagarta_fow.json")
FOW_PATTERN_RELATIVE_PATH = Path("map/pattern_fog_of_war_512.webp")

# World / CastleDB extracts
POIS_RELATIVE_PATH = Path("data/w1_siagarta/pois.json")
CRITTER_SPAWNS_RELATIVE_PATH = Path("data/w1_siagarta/critter_spawns.json")
PATROL_PATHS_RELATIVE_PATH = Path("data/w1_siagarta/patrol_paths.json")
DISPLAY_NAMES_RELATIVE_PATH = Path("data/display_names.json")
UNIT_TRAITS_RELATIVE_PATH = Path("data/unit_traits.json")
CURRENCY_CAPS_RELATIVE_PATH = Path("data/currency_caps.json")

# Markers / classes / currency (shipped under ui/)
ACTIVITY_ICON_ATLAS_RELATIVE_PATH = Path("ui/markers/activities.webp")
# Fallback when loading from an installed Farever game tree (not ASSET_ROOT).
GAME_ACTIVITY_ICON_ATLAS_RELATIVE_PATH = Path("data/icons/activities.png")
PLAYER_CURSOR_RELATIVE_PATH = Path("ui/markers/player_cursor.webp")
RIFT_ICON_RELATIVE_PATH = Path("ui/markers/rift_icon.webp")
CLASS_BLANK_RELATIVE_PATH = Path("ui/classes/classBlank.webp")
CLASS_ICON_FILES = {
    "priest": "ui/classes/classPriest.webp",
    "mage": "ui/classes/classMage.webp",
    "warrior": "ui/classes/classWarrior.webp",
    "rogue": "ui/classes/classRogue.webp",
}
LOOSE_KIND_ICON_FILES = {
    "red_orb": "ui/markers/red_orb.webp",
    "plant": "ui/markers/plant.webp",
    "ore": "ui/markers/ore.webp",
}
CURRENCY_ICON_FILES = {
    "Gold": "ui/currency/currency_gold.webp",
    "CraftPoint": "ui/currency/currency_craft.webp",
    "DemonicSoul": "ui/currency/currency_demonic_soul.webp",
    "Nightblood": "ui/currency/currency_nightblood.webp",
}

# UI chrome / planner
UI_POWER_RELATIVE_PATH = Path("ui/chrome/power.svg")
UI_RELOAD_RELATIVE_PATH = Path("ui/chrome/reload.svg")
UI_RELOAD_HOVER_RELATIVE_PATH = Path("ui/chrome/reload_hover.svg")
UI_SETTINGS_RELATIVE_PATH = Path("ui/chrome/settings.svg")
UI_SETTINGS_HOVER_RELATIVE_PATH = Path("ui/chrome/settings_hover.svg")
UI_HELP_RELATIVE_PATH = Path("ui/chrome/help.svg")
UI_HELP_HOVER_RELATIVE_PATH = Path("ui/chrome/help_hover.svg")
UI_FOG_RELATIVE_PATH = Path("ui/chrome/fog.svg")
UI_COLLECT_RELATIVE_PATH = Path("ui/chrome/collect.svg")
UI_WAYPOINT_RELATIVE_PATH = Path("ui/chrome/waypoint.svg")
UI_GITHUB_RELATIVE_PATH = Path("ui/chrome/github.svg")
UI_MAP_RECENTER_RELATIVE_PATH = Path("ui/chrome/map_recenter.svg")
UI_LEVEL_PLUS_RELATIVE_PATH = Path("ui/chrome/level_plus.svg")
UI_LEVEL_MINUS_RELATIVE_PATH = Path("ui/chrome/level_minus.svg")
UI_CLOSE_RELATIVE_PATH = Path("ui/chrome/window_close.svg")
UI_CLOSE_HOVER_RELATIVE_PATH = Path("ui/chrome/window_close_hover.svg")
UI_MINIMIZE_RELATIVE_PATH = Path("ui/chrome/window_minimize.svg")
UI_MINIMIZE_HOVER_RELATIVE_PATH = Path("ui/chrome/window_minimize_hover.svg")
UI_MAXIMIZE_RELATIVE_PATH = Path("ui/chrome/window_maximize.svg")
UI_MAXIMIZE_HOVER_RELATIVE_PATH = Path("ui/chrome/window_maximize_hover.svg")
UI_RESTORE_RELATIVE_PATH = Path("ui/chrome/window_restore.svg")
UI_RESTORE_HOVER_RELATIVE_PATH = Path("ui/chrome/window_restore_hover.svg")
PLANNER_TALENT_SILVER_RELATIVE_PATH = Path(
    "ui/planner/planner_talent_placeholder_silver.svg"
)
PLANNER_TALENT_GOLD_RELATIVE_PATH = Path(
    "ui/planner/planner_talent_placeholder_gold.svg"
)

# Back-compat alias used by older call sites / packaging notes.
RIFT_ICON_NAME = str(RIFT_ICON_RELATIVE_PATH)
WAYPOINT_WORLD = "W1_Siagarta"
WAYPOINT_FILE_NAME = "user_waypoints_siagarta.json"
WAYPOINT_STORE_PATH = PROJECT_ROOT / "user_data" / "waypoints" / WAYPOINT_FILE_NAME
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
WAYPOINT_ICONS = ("pin", "diamond", "circle", "star", "flag", "cross", "crosshair")

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


def discover_game_dir() -> Path | None:
    # Highest-priority source: an explicit directory from FAREVER_GAME_DIR
    # or supplied by the user. This avoids relying on Steam library discovery.
    env_path = os.environ.get(GAME_DIR_ENV, "").strip()
    if env_path:
        candidate = Path(env_path).expanduser()
        if (candidate / "Farever.exe").is_file():
            return candidate.resolve()

    # Optional override under this checkout/exe user_data/.
    conf = PROJECT_ROOT / "user_data" / "game_dir.conf"
    if conf.is_file():
        try:
            line = conf.read_text(encoding="utf-8").splitlines()[0].strip()
        except OSError:
            line = ""
        if line:
            candidate = Path(line).expanduser()
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


def discover_project_asset(relative: str | Path) -> Path | None:
    # Loose Atlas assets live under ASSET_ROOT (bundled when frozen).
    # ``relative`` may be a bare filename or a path under assets/ (e.g. map/…).
    candidate = ASSET_ROOT / Path(relative)
    return candidate if candidate.is_file() else None


def discover_rift_icon() -> Path | None:
    return discover_project_asset(RIFT_ICON_RELATIVE_PATH)


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
