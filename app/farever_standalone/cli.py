"""Command-line entry point and application bootstrap."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .config import (
    default_state_dir,
    discover_game_dir,
    discover_rift_icon,
    discover_state_dir,
)
from .controller import Controller
from .map_data import MapCalibration, load_map_texture
from .telemetry import DataHub
from .waypoints import WaypointStore


def apply_palette(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="Directory containing nyx_external_live_state.json and nyx_external_pois.json",
    )
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = args.state_dir.expanduser() if args.state_dir else discover_state_dir()
    if state_dir is None:
        state_dir = default_state_dir()
    game_dir = args.game_dir.expanduser() if args.game_dir else discover_game_dir()
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Farever Standalone")
    app.setOrganizationName("Local")
    apply_palette(app)

    runtime_dir = QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.StandardLocation.RuntimeLocation
    )
    lock_dir = Path(runtime_dir) if runtime_dir else Path(QtCore.QDir.tempPath())
    instance_lock = QtCore.QLockFile(
        str(lock_dir / "farever-standalone.lock")
    )
    if not instance_lock.tryLock(100):
        print("Farever Standalone is already running.", file=sys.stderr)
        return 0

    settings = QtCore.QSettings("Local", "FareverStandalone")
    map_texture, map_message = load_map_texture(game_dir, args.map_image, args.map_bounds)
    if (
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
    hub = DataHub(state_dir)
    controller = Controller(
        hub, settings, map_texture, map_message, rift_icon_path, waypoint_store
    )
    controller.show()
    hub.start()
    app.aboutToQuit.connect(lambda: settings.sync())
    return app.exec()
