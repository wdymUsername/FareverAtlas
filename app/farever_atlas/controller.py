"""Application-level wiring between telemetry and windows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6 import QtCore

from .auxiliary_windows import CombatWindow
from .pages.map.data import MapTexture
from .shell.window import AtlasWindow
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
        *,
        dev_mode: bool = False,
        boot: dict[str, Any] | None = None,
    ):
        super().__init__()
        self.hub = hub
        self.settings = settings
        self.map_texture = map_texture
        self.map_message = map_message
        self.rift_icon_path = rift_icon_path
        self.waypoint_store = waypoint_store
        self.dev_mode = dev_mode
        self.boot = boot or {}
        self.reloading = False

        self.map_window = AtlasWindow(
            settings,
            map_texture,
            map_message,
            rift_icon_path,
            waypoint_store,
            dev_mode=dev_mode,
        )
        self.combat_window = CombatWindow(settings)
        hub.updated.connect(self.map_window.update_snapshot)
        hub.updated.connect(self.combat_window.update_snapshot)
        self.map_window.onlineModeChanged.connect(hub.set_online)
        self.map_window.combatMeterRequested.connect(self.show_combat_meter)
        self.map_window.main_navigation_overlay.settingsChanged.connect(
            self.combat_window.apply_settings_preferences
        )
        if dev_mode:
            self.map_window.uiReloadRequested.connect(self.reload_ui)
        hub.set_online(self.map_window.online_mode)

    def show(self) -> None:
        self.map_window.show()

    @QtCore.Slot()
    def show_combat_meter(self) -> None:
        self.combat_window.show()
        self.combat_window.raise_()
        self.combat_window.activateWindow()

    @QtCore.Slot()
    def reload_ui(self) -> None:
        if not self.dev_mode or self.reloading:
            return
        import importlib

        from . import dev_reload

        # Pick up edits to the reload orchestrator itself.
        importlib.reload(dev_reload)
        try:
            dev_reload.reload_ui(self)
        except Exception:
            # Errors are logged and toasted inside reload_ui when possible.
            pass
