"""Application-level wiring between telemetry and windows."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from .auxiliary_windows import CombatWindow
from .map_data import MapTexture
from .map_window import MapWindow
from .telemetry import DataHub
from .waypoints import WaypointStore


class Controller(QtCore.QObject):
    def __init__(
        self,
        hub: DataHub,
        settings: QtCore.QSettings,
        map_texture: MapTexture | None,
        map_message: str,
        rift_icon_path: Path | None,
        waypoint_store: WaypointStore,
    ):
        super().__init__()
        self.map_window = MapWindow(
            settings, map_texture, map_message, rift_icon_path, waypoint_store
        )
        self.combat_window = CombatWindow(settings)
        hub.updated.connect(self.map_window.update_snapshot)
        hub.updated.connect(self.combat_window.update_snapshot)
        self.map_window.onlineModeChanged.connect(hub.set_online)
        self.map_window.combatMeterRequested.connect(self.show_combat_meter)
        hub.set_online(self.map_window.online_mode)

    def show(self) -> None:
        self.map_window.show()

    @QtCore.Slot()
    def show_combat_meter(self) -> None:
        self.combat_window.show()
        self.combat_window.raise_()
        self.combat_window.activateWindow()
