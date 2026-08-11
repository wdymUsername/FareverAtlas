"""Soft in-process UI reload for ``--dev`` sessions.

Keeps the QApplication, DataHub, WaypointStore, and process lock alive while
re-importing application modules and rebuilding top-level windows.
"""

from __future__ import annotations

import importlib
import sys
import traceback
from typing import TYPE_CHECKING, Any

from PySide6 import QtCore, QtWidgets

if TYPE_CHECKING:
    from .controller import Controller

PACKAGE = "farever_atlas"

# Living runtime objects / the reload orchestrator itself must stay imported.
_PRESERVE_MODULES = frozenset(
    {
        PACKAGE,
        f"{PACKAGE}.dev_reload",
        f"{PACKAGE}.cli",
        f"{PACKAGE}.__main__",
        f"{PACKAGE}.telemetry",
        f"{PACKAGE}.waypoints",
        f"{PACKAGE}.controller",
    }
)


def _safe_disconnect(signal: Any, slot: Any) -> None:
    try:
        signal.disconnect(slot)
    except (TypeError, RuntimeError):
        pass


def _persist_window_geometry(window: QtWidgets.QWidget) -> None:
    settings = getattr(window, "_settings", None)
    settings_key = getattr(window, "_settings_key", None)
    if settings is None or not settings_key:
        return
    restore = settings.value("app/restore_window_positions", True)
    if isinstance(restore, str):
        restore = restore.strip().lower() in {"1", "true", "yes", "on"}
    if not restore:
        return
    settings.setValue(f"windows/{settings_key}/geometry", window.saveGeometry())


def _drop_reloadable_modules() -> list[str]:
    dropped: list[str] = []
    for name in list(sys.modules):
        if name != PACKAGE and not name.startswith(PACKAGE + "."):
            continue
        if name in _PRESERVE_MODULES:
            continue
        del sys.modules[name]
        dropped.append(name)
    return dropped


def _reload_map_assets(controller: Controller) -> tuple[Any, str]:
    from .config import discover_game_dir
    from .pages.map.data import MapCalibration, load_map_texture

    boot = controller.boot
    game_dir = boot.get("game_dir")
    if game_dir is None:
        game_dir = discover_game_dir()
    map_image = boot.get("map_image")
    map_bounds = boot.get("map_bounds")
    map_texture, map_message = load_map_texture(game_dir, map_image, map_bounds)
    if map_texture is not None and map_texture.calibration is not None:
        if controller.settings.contains("map/calibration"):
            controller.settings.remove("map/calibration")
    elif (
        map_texture is not None
        and map_bounds is None
        and map_texture.calibration is None
    ):
        saved = MapCalibration.from_json_value(
            controller.settings.value("map/calibration")
        )
        if saved is not None:
            map_texture.calibration = saved
            map_texture.calibration_source = "saved manual calibration fallback"
    return map_texture, map_message


def _wire_windows(
    controller: Controller,
    map_window: Any,
    combat_window: Any,
    overlay_window: Any | None = None,
) -> None:
    hub = controller.hub
    hub.updated.connect(map_window.update_snapshot)
    hub.updated.connect(combat_window.update_snapshot)
    hub.updated.connect(controller._overlay_snapshot)
    map_window.onlineModeChanged.connect(hub.set_online)
    map_window.combatMeterRequested.connect(controller.show_combat_meter)
    map_window.mapViewChanged.connect(controller.sync_overlay_view)
    if hasattr(map_window, "aboutToClose"):
        map_window.aboutToClose.connect(controller.shutdown_windows)
    map_window.main_navigation_overlay.settingsChanged.connect(
        combat_window.apply_settings_preferences
    )
    map_window.main_navigation_overlay.settingsChanged.connect(
        controller.apply_overlay_preferences
    )
    if overlay_window is not None:
        overlay_window.closedByUser.connect(controller._overlay_closed_by_user)
    if controller.dev_mode and hasattr(map_window, "uiReloadRequested"):
        map_window.uiReloadRequested.connect(controller.reload_ui)


def _unwire_windows(
    controller: Controller,
    map_window: Any,
    combat_window: Any,
    overlay_window: Any | None = None,
) -> None:
    hub = controller.hub
    _safe_disconnect(hub.updated, map_window.update_snapshot)
    _safe_disconnect(hub.updated, combat_window.update_snapshot)
    _safe_disconnect(hub.updated, controller._overlay_snapshot)
    _safe_disconnect(map_window.onlineModeChanged, hub.set_online)
    _safe_disconnect(map_window.combatMeterRequested, controller.show_combat_meter)
    _safe_disconnect(map_window.mapViewChanged, controller.sync_overlay_view)
    if hasattr(map_window, "aboutToClose"):
        _safe_disconnect(map_window.aboutToClose, controller.shutdown_windows)
    overlay = getattr(map_window, "main_navigation_overlay", None)
    if overlay is not None:
        _safe_disconnect(
            overlay.settingsChanged, combat_window.apply_settings_preferences
        )
        _safe_disconnect(
            overlay.settingsChanged, controller.apply_overlay_preferences
        )
    if overlay_window is not None:
        _safe_disconnect(overlay_window.closedByUser, controller._overlay_closed_by_user)
    if hasattr(map_window, "uiReloadRequested"):
        _safe_disconnect(map_window.uiReloadRequested, controller.reload_ui)


def reload_ui(controller: Controller) -> None:
    """Rebuild Atlas windows from freshly imported modules."""
    if controller.reloading:
        return

    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("No QApplication instance")

    controller.reloading = True
    quit_was = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)

    old_map = controller.map_window
    old_combat = controller.combat_window
    old_overlay = getattr(controller, "overlay_window", None)
    combat_was_visible = old_combat.isVisible()
    overlay_was_visible = bool(old_overlay is not None and old_overlay.isVisible())
    overlay_was_unlocked = bool(
        old_overlay is not None and getattr(old_overlay, "_unlocked", False)
    )
    hub = controller.hub
    rebuilt = False

    try:
        _unwire_windows(controller, old_map, old_combat, old_overlay)
        _persist_window_geometry(old_map)
        _persist_window_geometry(old_combat)
        if old_overlay is not None:
            _persist_window_geometry(old_overlay)
        controller.settings.sync()

        old_map.hide()
        old_combat.hide()
        if old_overlay is not None:
            old_overlay.hide()

        dropped = _drop_reloadable_modules()
        importlib.invalidate_caches()

        from .auxiliary_windows import CombatWindow
        from .map_overlay_window import MapOverlayWindow
        from .shell.window import AtlasWindow
        from .toast import notify

        map_texture, map_message = _reload_map_assets(controller)
        controller.map_texture = map_texture
        controller.map_message = map_message

        rift_icon_path = controller.rift_icon_path
        try:
            from .config import discover_rift_icon

            rift_icon_path = discover_rift_icon() or rift_icon_path
        except Exception:
            pass
        controller.rift_icon_path = rift_icon_path

        new_map = AtlasWindow(
            controller.settings,
            map_texture,
            map_message,
            rift_icon_path,
            controller.waypoint_store,
            dev_mode=controller.dev_mode,
        )
        new_combat = CombatWindow(controller.settings)
        new_overlay = MapOverlayWindow(controller.settings, map_texture)
        new_overlay.attach_source_radar(new_map.radar)
        _wire_windows(controller, new_map, new_combat, new_overlay)

        controller.map_window = new_map
        controller.combat_window = new_combat
        controller.overlay_window = new_overlay
        rebuilt = True

        hub.set_online(new_map.online_mode)
        new_map.show()
        if combat_was_visible:
            new_combat.show()
            new_combat.raise_()
        if overlay_was_visible:
            new_overlay.set_unlocked(overlay_was_unlocked)
            new_overlay.set_overlay_visible(True)
            controller.sync_overlay_view()

        old_map.close()
        old_combat.close()
        if old_overlay is not None:
            if hasattr(old_overlay, "force_close"):
                old_overlay.force_close()
            else:
                old_overlay.close()
            old_overlay.deleteLater()
        old_map.deleteLater()
        old_combat.deleteLater()
        app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

        if hasattr(hub, "poll"):
            hub.poll()

        notify(
            new_map,
            f"UI reloaded ({len(dropped)} modules)",
            kind="success",
        )
    except Exception:
        traceback.print_exc()
        if not rebuilt:
            # Old class objects remain alive even after sys.modules drop.
            try:
                _wire_windows(controller, old_map, old_combat, old_overlay)
                old_map.show()
                if combat_was_visible:
                    old_combat.show()
                if overlay_was_visible and old_overlay is not None:
                    old_overlay.set_unlocked(overlay_was_unlocked)
                    old_overlay.set_overlay_visible(True)
                button = getattr(old_map, "reload_ui_button", None)
                if button is not None:
                    button.setEnabled(True)
                    button.setToolTip("Reload UI (dev)")
                try:
                    from .toast import notify

                    notify(old_map, "UI reload failed — see console", kind="error")
                except Exception:
                    pass
            except Exception:
                traceback.print_exc()
        else:
            window = controller.map_window
            try:
                from .toast import notify

                notify(window, "UI reload failed — see console", kind="error")
            except Exception:
                pass
        raise
    finally:
        app.setQuitOnLastWindowClosed(quit_was)
        controller.reloading = False
