"""Application-level wiring between telemetry and windows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6 import QtCore

from .auxiliary_windows import CombatWindow
from .map_overlay_window import MapOverlayWindow
from .pages.map.data import MapTexture, Snapshot
from .shell.window import AtlasWindow
from .telemetry import DataHub
from .waypoints import WaypointStore


def _setting_bool(settings: QtCore.QSettings, key: str, default: bool) -> bool:
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _snapshot_game_ui_open(snapshot: Snapshot) -> bool:
    """True when the game has a blocking UI window open (map, inventory, …)."""
    if not snapshot.connected:
        return False
    ui = snapshot.state.get("ui") if isinstance(snapshot.state, dict) else None
    if isinstance(ui, dict):
        if bool(ui.get("open")):
            return True
        windows = ui.get("windows")
        return isinstance(windows, list) and any(
            isinstance(name, str) and name.strip() for name in windows
        )
    return False


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
        self._overlay_enabled = False
        self._game_ui_open = False

        self.map_window = AtlasWindow(
            settings,
            map_texture,
            map_message,
            rift_icon_path,
            waypoint_store,
            dev_mode=dev_mode,
        )
        self.combat_window = CombatWindow(settings)
        self.overlay_window = MapOverlayWindow(settings, map_texture)
        self.overlay_window.attach_source_radar(self.map_window.radar)
        hub.updated.connect(self.map_window.update_snapshot)
        hub.updated.connect(self.combat_window.update_snapshot)
        hub.updated.connect(self._overlay_snapshot)
        self.map_window.onlineModeChanged.connect(hub.set_online)
        self.map_window.combatMeterRequested.connect(self.show_combat_meter)
        self.map_window.mapViewChanged.connect(self.sync_overlay_view)
        self.map_window.main_navigation_overlay.settingsChanged.connect(
            self.combat_window.apply_settings_preferences
        )
        self.map_window.main_navigation_overlay.settingsChanged.connect(
            self.apply_overlay_preferences
        )
        self.overlay_window.closedByUser.connect(self._overlay_closed_by_user)
        if dev_mode:
            self.map_window.uiReloadRequested.connect(self.reload_ui)
        hub.set_online(self.map_window.online_mode)
        self.apply_overlay_preferences()

    def show(self) -> None:
        self.map_window.show()

    @QtCore.Slot()
    def show_combat_meter(self) -> None:
        self.combat_window.show()
        self.combat_window.raise_()
        self.combat_window.activateWindow()

    @QtCore.Slot(object)
    def _overlay_snapshot(self, snapshot: Snapshot) -> None:
        self._set_game_ui_open(_snapshot_game_ui_open(snapshot))
        if not self.overlay_window.isVisible():
            return
        self.overlay_window.update_snapshot(snapshot)
        self.sync_overlay_view()

    def _set_game_ui_open(self, open_ui: bool) -> None:
        open_ui = bool(open_ui)
        if open_ui == self._game_ui_open:
            return
        self._game_ui_open = open_ui
        self._sync_overlay_visibility()

    def _sync_overlay_visibility(self) -> None:
        """Show companion overlays only when enabled and no game UI is up."""
        show = self._overlay_enabled and not self._game_ui_open
        was_visible = self.overlay_window.isVisible()
        self.overlay_window.set_overlay_visible(show)
        if show and not was_visible:
            latest = getattr(self.map_window, "latest_snapshot", None)
            if latest is not None:
                self.overlay_window.update_snapshot(latest)
            self.sync_overlay_view()

    @QtCore.Slot()
    def sync_overlay_view(self) -> None:
        if not self.overlay_window.isVisible():
            return
        self.overlay_window.sync_from(self.map_window.radar)

    @QtCore.Slot()
    def apply_overlay_preferences(self) -> None:
        enabled = _setting_bool(self.settings, "map/overlay_enabled", False)
        unlocked = _setting_bool(self.settings, "map/overlay_unlocked", False)
        opacity = int(self.settings.value("map/overlay_opacity", 100) or 100)
        try:
            opacity = int(opacity)
        except (TypeError, ValueError):
            opacity = 100
        if not enabled:
            unlocked = False
        self._overlay_enabled = enabled
        self.overlay_window.attach_source_radar(self.map_window.radar)
        self.overlay_window.set_opacity_percent(opacity)
        self.overlay_window.set_unlocked(unlocked)
        self._sync_overlay_visibility()

    @QtCore.Slot()
    def _overlay_closed_by_user(self) -> None:
        self.settings.setValue("map/overlay_enabled", False)
        self.settings.setValue("map/overlay_unlocked", False)
        self._overlay_enabled = False
        self.overlay_window.set_unlocked(False)
        self._sync_overlay_visibility()
        # Keep settings UI in sync if the panel is open.
        panel = getattr(
            getattr(self.map_window, "main_navigation_overlay", None),
            "settings_panel",
            None,
        )
        if panel is not None and hasattr(panel, "reload_from_settings"):
            panel.reload_from_settings()

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
