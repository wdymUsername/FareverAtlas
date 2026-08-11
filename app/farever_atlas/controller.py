"""Application-level wiring between telemetry and windows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .auxiliary_windows import CombatWindow
from .game_window import find_farever_game_window
from .global_hotkey import GlobalHotkey
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
        self._overlay_follow_game = False
        self._overlay_hide_when_unfocused = False
        self._game_ui_open = False
        self._game_is_active = False
        self._shutting_down = False

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
        self._game_window_timer = QtCore.QTimer(self)
        self._game_window_timer.setInterval(400)
        self._game_window_timer.timeout.connect(self._poll_game_window)
        self._overlay_lock_hotkey = GlobalHotkey(self)
        self._overlay_lock_hotkey.activated.connect(self._toggle_overlay_lock_hotkey)
        hub.updated.connect(self.map_window.update_snapshot)
        hub.updated.connect(self.combat_window.update_snapshot)
        hub.updated.connect(self._overlay_snapshot)
        self.map_window.onlineModeChanged.connect(hub.set_online)
        self.map_window.combatMeterRequested.connect(self.show_combat_meter)
        self.map_window.mapViewChanged.connect(self.sync_overlay_view)
        self.map_window.aboutToClose.connect(self.shutdown_windows)
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
    def shutdown_windows(self) -> None:
        """Close every top-level companion when the main Atlas window closes."""
        if self._shutting_down or self.reloading:
            return
        self._shutting_down = True
        self._game_window_timer.stop()
        self._overlay_lock_hotkey.clear()
        overlay = getattr(self, "overlay_window", None)
        if overlay is not None:
            if hasattr(overlay, "_persist_geometry"):
                overlay._persist_geometry()
            if hasattr(overlay, "force_close"):
                overlay.force_close()
            else:
                overlay.close()
        combat = getattr(self, "combat_window", None)
        if combat is not None:
            if hasattr(combat, "_persist_geometry"):
                combat._persist_geometry()
            combat.close()
        self.settings.sync()
        app = QtWidgets.QApplication.instance()
        if app is not None and not app.closingDown():
            # Overlay used to be Qt.Tool and vanished with the shell; as a
            # normal Window it can keep quitOnLastWindowClosed from firing.
            app.quit()

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
        hide_for_focus = self._overlay_hide_when_unfocused and not self._game_is_active
        show = (
            self._overlay_enabled
            and not self._game_ui_open
            and not hide_for_focus
        )
        was_visible = self.overlay_window.isVisible()
        if show == was_visible:
            return
        self.overlay_window.set_overlay_visible(show)
        if show and not was_visible:
            latest = getattr(self.map_window, "latest_snapshot", None)
            if latest is not None:
                self.overlay_window.update_snapshot(latest)
            self.sync_overlay_view()

    def _sync_game_window_timer(self) -> None:
        need_poll = self._overlay_enabled and (
            self._overlay_follow_game or self._overlay_hide_when_unfocused
        )
        if need_poll:
            if not self._game_window_timer.isActive():
                self._game_window_timer.start()
            self._poll_game_window()
        else:
            self._game_window_timer.stop()
            if self._game_is_active:
                self._game_is_active = False

    @QtCore.Slot()
    def _poll_game_window(self) -> None:
        if not self._overlay_enabled:
            self._game_window_timer.stop()
            return
        info = find_farever_game_window()
        prev_active = self._game_is_active
        if info is None:
            self._game_is_active = False
            rect = None
        else:
            self._game_is_active = bool(info.is_active)
            rect = info.rect
        if self._overlay_hide_when_unfocused and prev_active != self._game_is_active:
            self._sync_overlay_visibility()
        if (
            self._overlay_follow_game
            and rect is not None
            and self.overlay_window.isVisible()
        ):
            self.overlay_window.follow_game_rect(rect)

    @QtCore.Slot()
    def sync_overlay_view(self) -> None:
        if not self.overlay_window.isVisible():
            return
        self.overlay_window.sync_from(self.map_window.radar)

    @QtCore.Slot()
    def apply_overlay_preferences(self) -> None:
        enabled = _setting_bool(self.settings, "map/overlay_enabled", False)
        unlocked = _setting_bool(self.settings, "map/overlay_unlocked", False)
        follow = _setting_bool(self.settings, "map/overlay_follow_game", False)
        hide_unfocused = _setting_bool(
            self.settings, "map/overlay_hide_when_unfocused", False
        )
        opacity = int(self.settings.value("map/overlay_opacity", 100) or 100)
        try:
            opacity = int(opacity)
        except (TypeError, ValueError):
            opacity = 100
        if not enabled:
            unlocked = False
        self._overlay_enabled = enabled
        self._overlay_follow_game = follow
        self._overlay_hide_when_unfocused = hide_unfocused
        self.overlay_window.attach_source_radar(self.map_window.radar)
        self.overlay_window.set_opacity_percent(opacity)
        self.overlay_window.set_unlocked(unlocked)
        self.overlay_window.set_follow_enabled(follow)
        self._sync_overlay_lock_hotkey()
        self._sync_game_window_timer()
        self._sync_overlay_visibility()

    def _sync_overlay_lock_hotkey(self) -> None:
        raw = str(self.settings.value("map/overlay_lock_hotkey", "Insert") or "Insert")
        sequence = QtGui.QKeySequence(raw)
        # Only bind while overlay feature is enabled so Insert stays free otherwise.
        if not self._overlay_enabled or sequence.isEmpty():
            self._overlay_lock_hotkey.clear()
            return
        self._overlay_lock_hotkey.set_key_sequence(sequence)

    @QtCore.Slot()
    def _toggle_overlay_lock_hotkey(self) -> None:
        if not self._overlay_enabled:
            return
        unlocked = not _setting_bool(self.settings, "map/overlay_unlocked", False)
        self.settings.setValue("map/overlay_unlocked", unlocked)
        panel = getattr(
            getattr(self.map_window, "main_navigation_overlay", None),
            "settings_panel",
            None,
        )
        if panel is not None and hasattr(panel, "overlay_unlocked"):
            was_suppress = bool(getattr(panel, "_suppress", False))
            panel._suppress = True
            try:
                panel.overlay_unlocked.setChecked(unlocked)
                panel._sync_overlay_controls_enabled()
            finally:
                panel._suppress = was_suppress
        self.apply_overlay_preferences()
        if hasattr(self.map_window, "_sync_overlay_lock_button"):
            self.map_window._sync_overlay_lock_button()

    @QtCore.Slot()
    def _overlay_closed_by_user(self) -> None:
        self.settings.setValue("map/overlay_enabled", False)
        self.settings.setValue("map/overlay_unlocked", False)
        self._overlay_enabled = False
        self.overlay_window.set_unlocked(False)
        self._sync_overlay_lock_hotkey()
        self._sync_game_window_timer()
        self._sync_overlay_visibility()
        # Keep settings UI in sync if the panel is open.
        panel = getattr(
            getattr(self.map_window, "main_navigation_overlay", None),
            "settings_panel",
            None,
        )
        if panel is not None and hasattr(panel, "reload_from_settings"):
            panel.reload_from_settings()
        if hasattr(self.map_window, "_sync_overlay_lock_button"):
            self.map_window._sync_overlay_lock_button()

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
