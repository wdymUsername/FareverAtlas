"""Command-line entry point and application bootstrap."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .config import discover_game_dir, discover_rift_icon
from .controller import Controller
from .fonts import apply_ui_font, ensure_ui_fonts
from .pages.map.data import MapCalibration, load_map_texture
from .portable import (
    ensure_portable_dirs,
    instance_lock_path,
    is_frozen,
    settings_ini_path,
)
from .telemetry import DataHub
from .waypoints import WaypointStore


def apply_palette(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    if not is_frozen():
        try:
            ensure_ui_fonts()
        except Exception as exc:  # noqa: BLE001 - startup should continue on font issues
            print(f"Warning: could not prepare UI fonts: {exc}", file=sys.stderr)
    apply_ui_font(app, point_size=10)
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#151b22"))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#e6edf3"))
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#0f141a"))
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#18202a"))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#202a35"))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor("#e6edf3"))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#e6edf3"))
    palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#202a35"))
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#e6edf3"))
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#3478b7"))
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
    app.setPalette(palette)


def _load_settings() -> QtCore.QSettings:
    # Policy: all settings live in this checkout/exe user_data/settings.ini
    # (source and portable). Never use a shared ~/.config / AppData org store.
    ensure_portable_dirs()
    settings = QtCore.QSettings(
        str(settings_ini_path()), QtCore.QSettings.Format.IniFormat
    )
    settings.setFallbacksEnabled(False)
    if settings.allKeys():
        return settings

    # One-time migration from the old shared Qt org/app store (and earlier names).
    for legacy_name in ("FareverAtlas", "FareverStandalone", "FareverMinimap"):
        legacy = QtCore.QSettings("Local", legacy_name)
        keys = legacy.allKeys()
        if not keys:
            continue
        for key in keys:
            settings.setValue(key, legacy.value(key))
        settings.sync()
        # Clear the shared store so a fresh clone does not re-import secrets.
        legacy.clear()
        legacy.sync()
        break
    return settings


def _instance_lock() -> QtCore.QLockFile:
    ensure_portable_dirs()
    return QtCore.QLockFile(str(instance_lock_path()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game-dir",
        type=Path,
        help="Farever installation directory containing Farever.exe and data/",
    )
    parser.add_argument(
        "--map-image",
        type=Path,
        help="Force a particular map image instead of auto-discovering installed assets",
    )
    parser.add_argument(
        "--map-bounds",
        type=float,
        nargs=4,
        metavar=("MIN_X", "MAX_X", "MIN_Y", "MAX_Y"),
        help="Override world-coordinate bounds for the map image",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Enable the Reload control for soft in-process UI reloads",
    )
    parser.add_argument(
        "--test-toast",
        action="store_true",
        help="With --dev, summon sample toasts after the window opens",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.test_toast and not args.dev:
        print("--test-toast requires --dev", file=sys.stderr)
        return 2
    game_dir = args.game_dir.expanduser() if args.game_dir else discover_game_dir()
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Farever Atlas")
    # Organization name is unused for settings (IniFormat file under user_data/).
    app.setOrganizationName("Local")
    apply_palette(app)

    instance_lock = _instance_lock()
    if not instance_lock.tryLock(100):
        print("Farever Atlas is already running.", file=sys.stderr)
        return 0

    settings = _load_settings()
    map_texture, map_message = load_map_texture(game_dir, args.map_image, args.map_bounds)
    if map_texture is not None and map_texture.calibration is not None:
        # Prefer the stitched/native calibration; clear stale eye-fit overrides.
        if settings.contains("map/calibration"):
            settings.remove("map/calibration")
    elif (
        map_texture is not None
        and args.map_bounds is None
        and map_texture.calibration is None
    ):
        saved_calibration = MapCalibration.from_json_value(settings.value("map/calibration"))
        if saved_calibration is not None:
            map_texture.calibration = saved_calibration
            map_texture.calibration_source = "saved manual calibration fallback"
    rift_icon_path = discover_rift_icon()
    waypoint_store = WaypointStore()
    hub = DataHub()
    controller = Controller(
        hub,
        settings,
        map_texture,
        map_message,
        rift_icon_path,
        waypoint_store,
        dev_mode=bool(args.dev),
        boot={
            "game_dir": game_dir,
            "map_image": args.map_image,
            "map_bounds": args.map_bounds,
        },
    )
    if args.dev:
        print(
            "Dev mode: Reload (title bar) soft-reloads UI; "
            "Toast summons sample notifications.",
            flush=True,
        )
    controller.show()
    hub.start()
    if args.test_toast:
        QtCore.QTimer.singleShot(
            250, controller.map_window._summon_test_toasts
        )
    app.aboutToQuit.connect(lambda: settings.sync())
    return app.exec()
