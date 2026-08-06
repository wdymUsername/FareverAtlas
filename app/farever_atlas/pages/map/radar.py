"""Map canvas rendering and direct map interaction."""

from __future__ import annotations

import math
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import WAYPOINT_COLORS, map_heading_degrees, safe_float, safe_int
from .data import MapTexture, Snapshot


class RadarWidget(QtWidgets.QWidget):
    zoomRequested = QtCore.Signal(int)
    panStateChanged = QtCore.Signal(bool)
    customWaypointContextRequested = QtCore.Signal(object, object)

    # Zoom levels are defined against this reference canvas height. Window
    # resizing changes the visible world extent, not the world-to-pixel scale.
    ZOOM_REFERENCE_HEIGHT_PX = 600.0
    ICON_ATLAS_CELL_SIZE = 128
    ICON_ATLAS_COLUMNS = 8
    WAYPOINT_ICON_SIZE = 24

    # User-confirmed activities.png mapping. Numbers are one-based, left to
    # right across the first row (1-8), then the second row (9-16).
    ACTIVITY_ICON_INDICES = {
        "worldelite": 1,
        "chestorb": 2,
        "worldcamp": 4,
        "timercollectrun": 9,
        "ascension": 10,
        "fightstone": 11,
        "mountrush": 12,
        # WorldPlant intentionally uses the colored-dot fallback.
    }
    KIND_ICON_INDICES = {
        "dungeon": 3,
        "obelisk": 5,
        "respawn": 6,
        "merchant": 8,
        "chest": 11,
        # red_orb, plant, and ore intentionally use colored-dot fallback.
    }

    def __init__(self, map_texture: MapTexture | None = None) -> None:
        super().__init__()
        self.setMinimumSize(320, 240)
        self.state: dict[str, Any] = {}
        self.pois: list[dict[str, Any]] = []
        self.custom_waypoints: list[dict[str, Any]] = []
        self.show_custom_waypoints = True
        self.show_party_members = True
        self.show_party_names = True
        self.show_party_health_rings = True
        self.dim_invalid_party_members = True
        self.show_enemies = True
        self.show_route_line = True
        # World units of elevation difference before an enemy marker is dimmed.
        self.enemy_z_fade = 30.0
        self.active_custom_waypoint_id: int | None = None
        self.radius_m = 200.0
        self.target_radius_m = 200.0
        self.heading_up = False
        self.show_pois = True
        self.poi_kind_visibility: dict[str, bool] = {
            "obelisk": True,
            "respawn": True,
            "dungeon": True,
            "merchant": True,
            "activity": True,
        }
        self.loot_kind_visibility: dict[str, bool] = {
            "chest": False,
            "red_orb": False,
            "plant": False,
            "ore": False,
        }
        self.loot_kind_icon_mode: dict[str, bool] = {
            "chest": True,
            "red_orb": False,
            "plant": False,
            "ore": False,
        }
        self.show_texture = True
        self.rounded = False
        self.map_texture = map_texture
        self._waypoint_icon_cache: dict[int, QtGui.QImage] = {}
        self._loose_kind_icon_cache: dict[str, QtGui.QImage] = {}
        self.view_center_world: tuple[float, float] | None = None
        self._offline_center_world: tuple[float, float] | None = None
        self._drag_last: QtCore.QPointF | None = None
        self._drag_active = False
        self._drag_moved = False
        self._drag_started_panned = False
        self._custom_waypoint_hits: list[tuple[QtCore.QRectF, dict[str, Any]]] = []
        self._enemy_hits: list[tuple[QtCore.QRectF, dict[str, Any]]] = []
        self._hovered_custom_waypoint_id: int | None = None
        self._hovered_enemy_id: str | None = None
        self._live_marker_signature: tuple[Any, ...] | None = None
        # Generous hit slack around the small enemy dots so hover is usable.
        self._enemy_hit_radius = 9.0
        # Cursor-shape changes cannot be interpolated by Qt, so drag release uses
        # a short staged transition: closed hand -> open hand -> resting cursor.
        # The generation token prevents delayed callbacks from overriding a newer
        # hover state or a newly started drag.
        self._cursor_release_generation = 0

        # Telemetry arrives in discrete samples. Render a continuously interpolated
        # player pose so both map-follow movement and arrow rotation remain stable.
        self._display_player: dict[str, float] = {}
        self._smoothing_clock = QtCore.QElapsedTimer()
        self._smoothing_clock.start()
        self._last_smoothing_ns = self._smoothing_clock.nsecsElapsed()
        self._smoothing_timer = QtCore.QTimer(self)
        self._smoothing_timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self._smoothing_timer.setInterval(16)
        self._smoothing_timer.timeout.connect(self._advance_player_smoothing)
        self._smoothing_timer.start()

        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def set_snapshot(self, snapshot: Snapshot) -> None:
        pois_changed = snapshot.pois is not self.pois
        self.state = snapshot.state
        self.pois = snapshot.pois
        raw = self._raw_player()
        if not self._display_pose_valid() and self._raw_pose_valid(raw):
            self._snap_display_player(raw)
        party = self.state.get("party", []) if isinstance(self.state, dict) else []
        enemies = self.state.get("enemies", []) if isinstance(self.state, dict) else []
        target = self.state.get("target", {}) if isinstance(self.state, dict) else {}
        party_signature = tuple(
            (
                str(member.get("uid") or member.get("name") or ""),
                safe_float(member.get("x"), 0.0),
                safe_float(member.get("y"), 0.0),
                safe_float(member.get("heading"), 0.0),
                round(safe_float(member.get("hp"), 0.0)),
                round(safe_float(member.get("max_hp"), 0.0)),
                bool(member.get("hero_valid", True)),
            )
            for member in party
            if isinstance(member, dict)
        ) if isinstance(party, list) else ()
        enemy_signature = tuple(
            (
                str(enemy.get("id") or ""),
                str(enemy.get("kind") or ""),
                safe_float(enemy.get("x"), 0.0),
                safe_float(enemy.get("y"), 0.0),
                safe_float(enemy.get("z"), 0.0),
            )
            for enemy in enemies
            if isinstance(enemy, dict)
        ) if isinstance(enemies, list) else ()
        target_signature = (
            (
                True,
                safe_float(target.get("x"), 0.0),
                safe_float(target.get("y"), 0.0),
                round(safe_float(target.get("hp"), 0.0)),
            )
            if isinstance(target, dict) and target.get("exists")
            else (False,)
        )
        completed_elements = self.state.get("completed_elements", [])
        completed_signature = tuple(
            sorted(str(value) for value in completed_elements)
        ) if isinstance(completed_elements, list) else ()
        live_signature = (
            party_signature,
            enemy_signature,
            target_signature,
            completed_signature,
        )
        if pois_changed or live_signature != self._live_marker_signature:
            self._live_marker_signature = live_signature
            self.update()

    def set_offline_mode(
        self, offline: bool, cached_center: tuple[float, float] | None = None
    ) -> None:
        """Park the map on a valid center without a live player marker.

        Used for Offline Mode and for online waiting (bridge up, no live pose).
        """
        if not offline:
            self._offline_center_world = None
            return
        self._display_player.clear()
        center = cached_center
        calibration = self.map_texture.calibration if self.map_texture else None
        if center is None and calibration is not None and calibration.valid():
            logical_w = self.map_texture.logical_width
            logical_h = self.map_texture.logical_height
            center = (
                (logical_w * 0.5 - calibration.offset_x) / calibration.scale_x,
                (logical_h * 0.5 - calibration.offset_y) / calibration.scale_y,
            )
        if center is not None and all(math.isfinite(value) for value in center):
            self._offline_center_world = center
        self.update()

    def set_custom_waypoints(
        self,
        waypoints: list[dict[str, Any]],
        *,
        visible: bool,
        active_id: int | None,
    ) -> None:
        self.custom_waypoints = [dict(item) for item in waypoints]
        self.show_custom_waypoints = bool(visible)
        self.active_custom_waypoint_id = active_id
        self.update()

    def _raw_player(self) -> dict[str, Any]:
        player = self.state.get("player", {}) if isinstance(self.state, dict) else {}
        return player if isinstance(player, dict) else {}

    @staticmethod
    def _raw_pose_valid(player: dict[str, Any]) -> bool:
        x = safe_float(player.get("x"), math.nan)
        y = safe_float(player.get("y"), math.nan)
        return math.isfinite(x) and math.isfinite(y)

    def _display_pose_valid(self) -> bool:
        return (
            math.isfinite(self._display_player.get("x", math.nan))
            and math.isfinite(self._display_player.get("y", math.nan))
        )

    def _snap_display_player(self, raw: dict[str, Any]) -> None:
        x = safe_float(raw.get("x"), math.nan)
        y = safe_float(raw.get("y"), math.nan)
        if not (math.isfinite(x) and math.isfinite(y)):
            return
        self._display_player["x"] = x
        self._display_player["y"] = y
        heading = safe_float(raw.get("heading"), math.nan)
        if math.isfinite(heading):
            self._display_player["heading"] = heading

    @staticmethod
    def _shortest_angle_delta(target: float, current: float) -> float:
        return (target - current + math.pi) % (2.0 * math.pi) - math.pi

    def set_zoom_radius(self, radius_m: float, *, immediate: bool = False) -> None:
        target = max(1.0, float(radius_m))
        self.target_radius_m = target
        if immediate or not math.isfinite(self.radius_m):
            self.radius_m = target
        self.update()

    def _advance_player_smoothing(self) -> None:
        now_ns = self._smoothing_clock.nsecsElapsed()
        dt = max(0.001, min(0.050, (now_ns - self._last_smoothing_ns) / 1_000_000_000.0))
        self._last_smoothing_ns = now_ns

        zoom_changed = False
        radius_delta = self.target_radius_m - self.radius_m
        if abs(radius_delta) > 0.05:
            # Exponential easing remains frame-rate independent and can be
            # retargeted mid-animation by repeated button or wheel input.
            zoom_alpha = 1.0 - math.exp(-dt / 0.115)
            self.radius_m += radius_delta * zoom_alpha
            zoom_changed = True
        else:
            self.radius_m = self.target_radius_m

        raw = self._raw_player()
        if not self._raw_pose_valid(raw):
            if zoom_changed:
                self.update()
            return
        if not self._display_pose_valid():
            self._snap_display_player(raw)
            self.update()
            return

        target_x = safe_float(raw.get("x"), math.nan)
        target_y = safe_float(raw.get("y"), math.nan)
        current_x = self._display_player["x"]
        current_y = self._display_player["y"]
        distance = math.hypot(target_x - current_x, target_y - current_y)
        pose_changed = False

        # Large discontinuities are loading transitions, fast travel, or respawns;
        # snapping avoids visibly sliding across the entire zone.
        teleport_threshold = max(50.0, self.radius_m * 0.50)
        if distance >= teleport_threshold:
            self._display_player["x"] = target_x
            self._display_player["y"] = target_y
            pose_changed = True
        elif distance > 0.002:
            position_alpha = 1.0 - math.exp(-dt / 0.095)
            self._display_player["x"] = current_x + (target_x - current_x) * position_alpha
            self._display_player["y"] = current_y + (target_y - current_y) * position_alpha
            pose_changed = True
        else:
            self._display_player["x"] = target_x
            self._display_player["y"] = target_y

        target_heading = safe_float(raw.get("heading"), math.nan)
        if math.isfinite(target_heading):
            current_heading = self._display_player.get("heading", target_heading)
            if not math.isfinite(current_heading):
                current_heading = target_heading
            angle_delta = self._shortest_angle_delta(target_heading, current_heading)
            if abs(angle_delta) > 0.0002:
                heading_alpha = 1.0 - math.exp(-dt / 0.075)
                current_heading += angle_delta * heading_alpha
                pose_changed = True
            else:
                current_heading = target_heading
            self._display_player["heading"] = current_heading

        if zoom_changed or pose_changed:
            self.update()

    def _player(self) -> dict[str, Any]:
        raw = self._raw_player()
        if not self._display_pose_valid():
            return raw
        player = dict(raw)
        player["x"] = self._display_player["x"]
        player["y"] = self._display_player["y"]
        if math.isfinite(self._display_player.get("heading", math.nan)):
            player["heading"] = self._display_player["heading"]
        return player

    def _view_center(self) -> dict[str, float]:
        if self.view_center_world is not None:
            return {"x": self.view_center_world[0], "y": self.view_center_world[1]}
        if self._offline_center_world is not None:
            return {
                "x": self._offline_center_world[0],
                "y": self._offline_center_world[1],
            }
        player = self._player()
        return {
            "x": safe_float(player.get("x"), math.nan),
            "y": safe_float(player.get("y"), math.nan),
        }

    def is_panned(self) -> bool:
        return self.view_center_world is not None

    def recenter(self) -> None:
        was_panned = self.view_center_world is not None
        self.view_center_world = None
        self._drag_last = None
        self._drag_active = False
        self._drag_moved = False
        self._drag_started_panned = False
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        if was_panned:
            self.panStateChanged.emit(False)
        self.update()

    def center_on(self, x: float, y: float) -> None:
        if not (math.isfinite(x) and math.isfinite(y)):
            return
        next_center = (x, y)
        if self.map_texture is not None:
            next_center = self.map_texture.clamp_world_center(*next_center)
        self.view_center_world = next_center
        self.panStateChanged.emit(True)
        self.update()

    def _pixels_per_metre(self) -> float:
        return self.ZOOM_REFERENCE_HEIGHT_PX / (2.0 * max(self.radius_m, 1.0))

    def map_status(self) -> str:
        if self.map_texture is None:
            return "Map texture unavailable"
        source = self.map_texture.calibration_source
        calibration = self.map_texture.calibration
        if calibration is None:
            return f"Map: {self.map_texture.label} — uncalibrated"
        player = self._player()
        zoom_text = (
            f"; native zoom={self.map_texture.native_zoom:.1f}"
            if self.map_texture.native_zoom is not None
            and math.isfinite(self.map_texture.native_zoom)
            else ""
        )
        atlas_text = (
            f"; icons={self.map_texture.activity_icon_atlas_source}"
            if self.map_texture.activity_icon_atlas is not None
            and not self.map_texture.activity_icon_atlas.isNull()
            else "; icons=fallback dots"
        )
        return (
            f"Map: {self.map_texture.label} — calibration {source}; "
            f"sx={calibration.scale_x:.9f}, ox={calibration.offset_x:.3f}, "
            f"sy={calibration.scale_y:.9f}, oy={calibration.offset_y:.3f}; "
            f"logical {self.map_texture.logical_width:.0f}x"
            f"{self.map_texture.logical_height:.0f}{zoom_text}{atlas_text}; "
            f"{self.map_texture.diagnostic(player)}"
        )

    def _north_up_point(
        self,
        obj: dict[str, Any],
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
    ) -> QtCore.QPointF:
        # World-space orientation is authoritative: +X east/right, +Y south/down.
        dx = safe_float(obj.get("x")) - safe_float(view_center.get("x"))
        dy = safe_float(obj.get("y")) - safe_float(view_center.get("y"))
        return center + QtCore.QPointF(dx * pixels_per_metre, dy * pixels_per_metre)

    def _world_to_screen(
        self,
        obj: dict[str, Any],
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
    ) -> QtCore.QPointF:
        return self._north_up_point(obj, center, pixels_per_metre, view_center)

    def world_at_screen(self, point: QtCore.QPointF) -> dict[str, float] | None:
        viewport = QtCore.QRectF(self.rect().adjusted(3, 3, -3, -3))
        if not viewport.contains(point):
            return None
        center = viewport.center()
        view_center = self._view_center()
        center_x = safe_float(view_center.get("x"), math.nan)
        center_y = safe_float(view_center.get("y"), math.nan)
        pixels_per_metre = self._pixels_per_metre()
        if not (
            math.isfinite(center_x)
            and math.isfinite(center_y)
            and pixels_per_metre > 1e-9
        ):
            return None
        player = self._player()
        return {
            "x": center_x + (point.x() - center.x()) / pixels_per_metre,
            "y": center_y + (point.y() - center.y()) / pixels_per_metre,
            "z": safe_float(player.get("z"), 0.0),
        }

    def custom_waypoint_at(self, point: QtCore.QPointF) -> dict[str, Any] | None:
        for hit_rect, waypoint in reversed(self._custom_waypoint_hits):
            if hit_rect.contains(point):
                return dict(waypoint)
        return None

    def enemy_at(self, point: QtCore.QPointF) -> dict[str, Any] | None:
        # Nearest wins when markers overlap — helpful in dense packs.
        best: dict[str, Any] | None = None
        best_distance = math.inf
        for hit_rect, enemy in self._enemy_hits:
            if not hit_rect.contains(point):
                continue
            center = hit_rect.center()
            distance = math.hypot(point.x() - center.x(), point.y() - center.y())
            if distance < best_distance:
                best_distance = distance
                best = enemy
        return dict(best) if best is not None else None

    @staticmethod
    def _enemy_display_name(enemy: dict[str, Any]) -> str:
        kind = str(enemy.get("kind") or "").strip()
        if not kind:
            return "Enemy"
        # Creature ids arrive as HashLink identifiers like Crimson_Z2W_Sword_2.
        return " ".join(part for part in kind.replace("_", " ").split() if part)

    def _world_in_view(
        self,
        obj: dict[str, Any],
        view_center: dict[str, Any],
        viewport: QtCore.QRectF,
        margin_pixels: float = 12.0,
    ) -> bool:
        pixels_per_metre = max(1e-9, self._pixels_per_metre())
        half_width_m = viewport.width() / (2.0 * pixels_per_metre)
        half_height_m = viewport.height() / (2.0 * pixels_per_metre)
        margin_m = margin_pixels / pixels_per_metre
        dx = abs(safe_float(obj.get("x")) - safe_float(view_center.get("x")))
        dy = abs(safe_float(obj.get("y")) - safe_float(view_center.get("y")))
        return dx <= half_width_m + margin_m and dy <= half_height_m + margin_m

    def _cancel_cursor_release_ease(self) -> None:
        self._cursor_release_generation += 1

    def _resting_cursor_for_point(
        self, point: QtCore.QPointF | None = None
    ) -> QtCore.Qt.CursorShape:
        if point is None:
            point = QtCore.QPointF(
                self.mapFromGlobal(QtGui.QCursor.pos())
            )
        if self.custom_waypoint_at(point) is not None:
            return QtCore.Qt.CursorShape.PointingHandCursor
        return QtCore.Qt.CursorShape.ArrowCursor

    def _set_resting_cursor(self, point: QtCore.QPointF | None = None) -> None:
        if self._drag_active:
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            return
        self.setCursor(self._resting_cursor_for_point(point))

    def _ease_cursor_from_drag(self, point: QtCore.QPointF) -> None:
        self._cursor_release_generation += 1
        generation = self._cursor_release_generation
        resting_cursor = self._resting_cursor_for_point(point)

        # Relax the grip first, then settle onto the context-appropriate cursor.
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

        def settle() -> None:
            if generation != self._cursor_release_generation or self._drag_active:
                return
            self.setCursor(resting_cursor)

        QtCore.QTimer.singleShot(115, settle)

    def _event_is_over_child_ui(self, global_point: QtCore.QPoint) -> bool:
        """Return True when a propagated map event originated over child UI.

        Floating panels are children of the radar so they can remain anchored to
        the map viewport. Some controls ignore mouse buttons they do not use
        (notably a QPushButton ignoring right-click), which normally lets the
        event propagate into RadarWidget. Resolve the widget physically beneath
        the cursor and keep those events inside the overlay hierarchy.
        """
        application = QtWidgets.QApplication.instance()
        if application is None:
            return False

        popup = application.activePopupWidget()
        if popup is not None and popup.isVisible():
            popup_rect = QtCore.QRect(
                popup.mapToGlobal(QtCore.QPoint(0, 0)), popup.size()
            )
            if popup_rect.contains(global_point):
                return True

        target = application.widgetAt(global_point)
        return (
            target is not None
            and target is not self
            and self.isAncestorOf(target)
        )

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # noqa: N802
        if self._event_is_over_child_ui(event.globalPosition().toPoint()):
            event.accept()
            return
        delta = event.angleDelta().y()
        if delta != 0:
            self.zoomRequested.emit(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:  # noqa: N802
        if self._event_is_over_child_ui(event.globalPos()):
            event.accept()
            return
        point = QtCore.QPointF(event.pos())
        world = self.world_at_screen(point)
        if world is not None:
            waypoint = self.custom_waypoint_at(point)
            self.customWaypointContextRequested.emit(world, waypoint)
            event.accept()
            return
        super().contextMenuEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._event_is_over_child_ui(event.globalPosition().toPoint()):
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            center = self._view_center()
            center_x = safe_float(center.get("x"), math.nan)
            center_y = safe_float(center.get("y"), math.nan)
            if math.isfinite(center_x) and math.isfinite(center_y):
                self._drag_started_panned = self.is_panned()
                self.view_center_world = (center_x, center_y)
                self._drag_last = event.position()
                self._drag_active = True
                self._drag_moved = False
                self._cancel_cursor_release_ease()
                self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._event_is_over_child_ui(event.globalPosition().toPoint()):
            event.accept()
            return
        if (
            self._drag_active
            and self._drag_last is not None
            and self.view_center_world is not None
        ):
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            delta = event.position() - self._drag_last
            self._drag_last = event.position()
            if abs(delta.x()) + abs(delta.y()) > 0.5:
                self._drag_moved = True
            pixels_per_metre = self._pixels_per_metre()
            if self._drag_moved and pixels_per_metre > 1e-9:
                center_x, center_y = self.view_center_world
                next_center = (
                    center_x - delta.x() / pixels_per_metre,
                    center_y - delta.y() / pixels_per_metre,
                )
                if self.map_texture is not None:
                    next_center = self.map_texture.clamp_world_center(*next_center)
                self.view_center_world = next_center
                self.panStateChanged.emit(True)
                self.update()
            event.accept()
            return
        self._cancel_cursor_release_ease()
        waypoint = self.custom_waypoint_at(event.position())
        waypoint_id = safe_int(waypoint.get("id"), -1) if waypoint else None
        enemy = None if waypoint is not None else self.enemy_at(event.position())
        enemy_id = str(enemy.get("id") or "") if enemy is not None else None
        hover_changed = (
            waypoint_id != self._hovered_custom_waypoint_id
            or enemy_id != self._hovered_enemy_id
        )
        if hover_changed:
            self._hovered_custom_waypoint_id = waypoint_id
            self._hovered_enemy_id = enemy_id
            if waypoint is not None:
                player = self._player()
                distance = math.hypot(
                    safe_float(waypoint.get("x")) - safe_float(player.get("x")),
                    safe_float(waypoint.get("y")) - safe_float(player.get("y")),
                )
                tooltip = (
                    f"{waypoint.get('name') or 'Custom Waypoint'}\n"
                    f"X {safe_float(waypoint.get('x')):.1f}  "
                    f"Y {safe_float(waypoint.get('y')):.1f}  "
                    f"Z {safe_float(waypoint.get('z')):.1f}\n"
                    f"{distance:.1f} m · Right-click to manage"
                )
                QtWidgets.QToolTip.showText(
                    event.globalPosition().toPoint(), tooltip, self
                )
                self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            elif enemy is not None:
                player = self._player()
                distance = math.hypot(
                    safe_float(enemy.get("x")) - safe_float(player.get("x")),
                    safe_float(enemy.get("y")) - safe_float(player.get("y")),
                )
                tooltip = (
                    f"{self._enemy_display_name(enemy)}\n"
                    f"{distance:.1f} m"
                )
                QtWidgets.QToolTip.showText(
                    event.globalPosition().toPoint(), tooltip, self
                )
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            else:
                QtWidgets.QToolTip.hideText()
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        self._hovered_custom_waypoint_id = None
        self._hovered_enemy_id = None
        QtWidgets.QToolTip.hideText()
        if not self._drag_active:
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._event_is_over_child_ui(event.globalPosition().toPoint()):
            # A drag may begin on the map and end over an overlay. End the map
            # gesture cleanly without letting the release activate map UI.
            if event.button() == QtCore.Qt.MouseButton.LeftButton and self._drag_active:
                self._drag_active = False
                self._drag_last = None
                self._drag_moved = False
                self._drag_started_panned = False
                self._ease_cursor_from_drag(event.position())
                self.panStateChanged.emit(self.is_panned())
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._drag_active:
            if not self._drag_moved and not self._drag_started_panned:
                self.view_center_world = None
            self._drag_active = False
            self._drag_last = None
            self._drag_moved = False
            self._drag_started_panned = False
            self._ease_cursor_from_drag(event.position())
            self.panStateChanged.emit(self.is_panned())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._event_is_over_child_ui(event.globalPosition().toPoint()):
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.recenter()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    @classmethod
    def _poi_icon_index(cls, kind: str, subkind: str) -> int | None:
        normalized_kind = kind.strip().lower()
        if normalized_kind == "activity":
            return cls.ACTIVITY_ICON_INDICES.get(subkind.strip().lower())
        return cls.KIND_ICON_INDICES.get(normalized_kind)

    def _waypoint_icon(self, icon_index: int) -> QtGui.QImage | None:
        if icon_index <= 0:
            return None
        cached = self._waypoint_icon_cache.get(icon_index)
        if cached is not None:
            return cached
        if self.map_texture is None:
            return None
        atlas = self.map_texture.activity_icon_atlas
        if atlas is None or atlas.isNull():
            return None

        cell = self.ICON_ATLAS_CELL_SIZE
        zero_based = icon_index - 1
        column = zero_based % self.ICON_ATLAS_COLUMNS
        row = zero_based // self.ICON_ATLAS_COLUMNS
        source = QtCore.QRect(column * cell, row * cell, cell, cell)
        if not atlas.rect().contains(source):
            return None

        icon = atlas.copy(source).scaled(
            self.WAYPOINT_ICON_SIZE,
            self.WAYPOINT_ICON_SIZE,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        if icon.isNull():
            return None
        self._waypoint_icon_cache[icon_index] = icon
        return icon

    def _loose_kind_icon(self, kind: str) -> QtGui.QImage | None:
        normalized_kind = kind.strip().lower()
        cached = self._loose_kind_icon_cache.get(normalized_kind)
        if cached is not None:
            return cached
        if self.map_texture is None:
            return None
        source = self.map_texture.loose_kind_icons.get(normalized_kind)
        if source is None or source.isNull():
            return None
        icon = source.scaled(
            self.WAYPOINT_ICON_SIZE,
            self.WAYPOINT_ICON_SIZE,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        if icon.isNull():
            return None
        self._loose_kind_icon_cache[normalized_kind] = icon
        return icon

    def icon_available_for_kind(self, kind: str) -> bool:
        normalized_kind = kind.strip().lower()
        if self._loose_kind_icon(normalized_kind) is not None:
            return True
        icon_index = self._poi_icon_index(normalized_kind, "")
        return icon_index is not None and self._waypoint_icon(icon_index) is not None

    def _draw_poi_marker(
        self,
        painter: QtGui.QPainter,
        point: QtCore.QPointF,
        kind: str,
        subkind: str,
    ) -> None:
        normalized_kind = kind.strip().lower()
        use_icon = self.loot_kind_icon_mode.get(normalized_kind, True)
        if use_icon:
            icon = self._loose_kind_icon(normalized_kind)
            if icon is None:
                icon_index = self._poi_icon_index(normalized_kind, subkind)
                icon = self._waypoint_icon(icon_index) if icon_index is not None else None
            if icon is not None:
                x = point.x() - icon.width() / 2.0
                y = point.y() - icon.height() / 2.0
                painter.drawImage(QtCore.QPointF(x, y), icon)
                return

        painter.setPen(QtGui.QPen(QtGui.QColor("#101318"), 1.0))
        painter.setBrush(self._poi_color(kind))
        painter.drawEllipse(point, 3.5, 3.5)

    @staticmethod
    def _poi_color(kind: str) -> QtGui.QColor:
        colors = {
            "chest": QtGui.QColor("#e4b84a"),
            "red_orb": QtGui.QColor("#e35b62"),
            "plant": QtGui.QColor("#63c174"),
            "ore": QtGui.QColor("#aeb6c2"),
            "merchant": QtGui.QColor("#b785e5"),
            "dungeon": QtGui.QColor("#f28c54"),
            "activity": QtGui.QColor("#5ba6e6"),
            "respawn": QtGui.QColor("#f0f0f0"),
            "obelisk": QtGui.QColor("#7ce4df"),
        }
        return colors.get(kind, QtGui.QColor("#9ba7b4"))

    @staticmethod
    def _star_polygon(point: QtCore.QPointF, outer: float, inner: float) -> QtGui.QPolygonF:
        vertices: list[QtCore.QPointF] = []
        for index in range(10):
            angle = -math.pi / 2.0 + index * math.pi / 5.0
            radius = outer if index % 2 == 0 else inner
            vertices.append(
                point + QtCore.QPointF(math.cos(angle) * radius, math.sin(angle) * radius)
            )
        return QtGui.QPolygonF(vertices)

    def _draw_custom_waypoint_marker(
        self,
        painter: QtGui.QPainter,
        point: QtCore.QPointF,
        waypoint: dict[str, Any],
        active: bool,
    ) -> None:
        color_name = str(waypoint.get("color") or "cyan").lower()
        color = QtGui.QColor(WAYPOINT_COLORS.get(color_name, WAYPOINT_COLORS["cyan"]))
        icon = str(waypoint.get("icon") or "pin").lower()
        outline = QtGui.QColor("#0b1117")

        if active:
            painter.setPen(QtGui.QPen(color.lighter(135), 2.0))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawEllipse(point, 12.0, 12.0)

        painter.setPen(
            QtGui.QPen(
                outline,
                1.6,
                QtCore.Qt.PenStyle.SolidLine,
                QtCore.Qt.PenCapStyle.RoundCap,
                QtCore.Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(color)
        if icon == "diamond":
            painter.drawPolygon(
                QtGui.QPolygonF(
                    [
                        point + QtCore.QPointF(0, -8),
                        point + QtCore.QPointF(8, 0),
                        point + QtCore.QPointF(0, 8),
                        point + QtCore.QPointF(-8, 0),
                    ]
                )
            )
        elif icon == "circle":
            painter.drawEllipse(point, 7.0, 7.0)
        elif icon == "star":
            painter.drawPolygon(self._star_polygon(point, 8.5, 3.8))
        elif icon == "flag":
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(
                QtGui.QPen(
                    outline,
                    3.5,
                    QtCore.Qt.PenStyle.SolidLine,
                    QtCore.Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(point + QtCore.QPointF(-5, -8), point + QtCore.QPointF(-5, 9))
            painter.setPen(QtGui.QPen(outline, 1.4))
            painter.setBrush(color)
            painter.drawPolygon(
                QtGui.QPolygonF(
                    [
                        point + QtCore.QPointF(-4, -8),
                        point + QtCore.QPointF(7, -5),
                        point + QtCore.QPointF(-4, 0),
                    ]
                )
            )
        elif icon == "cross":
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(
                QtGui.QPen(
                    outline,
                    5.0,
                    QtCore.Qt.PenStyle.SolidLine,
                    QtCore.Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(point + QtCore.QPointF(-6, -6), point + QtCore.QPointF(6, 6))
            painter.drawLine(point + QtCore.QPointF(6, -6), point + QtCore.QPointF(-6, 6))
            painter.setPen(
                QtGui.QPen(
                    color,
                    2.4,
                    QtCore.Qt.PenStyle.SolidLine,
                    QtCore.Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(point + QtCore.QPointF(-6, -6), point + QtCore.QPointF(6, 6))
            painter.drawLine(point + QtCore.QPointF(6, -6), point + QtCore.QPointF(-6, 6))
        else:  # pin
            pin_center = point + QtCore.QPointF(0, -3)
            painter.drawEllipse(pin_center, 6.0, 6.0)
            painter.drawPolygon(
                QtGui.QPolygonF(
                    [
                        point + QtCore.QPointF(-4.5, 0),
                        point + QtCore.QPointF(4.5, 0),
                        point + QtCore.QPointF(0, 9),
                    ]
                )
            )
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(outline)
            painter.drawEllipse(pin_center, 2.0, 2.0)

        self._custom_waypoint_hits.append(
            (QtCore.QRectF(point.x() - 13.0, point.y() - 13.0, 26.0, 26.0), dict(waypoint))
        )

        if active:
            name = str(waypoint.get("name") or "Custom Waypoint")
            font = QtGui.QFont(painter.font())
            font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
            font.setBold(True)
            painter.setFont(font)
            metrics = QtGui.QFontMetricsF(font)
            text_rect = metrics.boundingRect(name).adjusted(-5, -2, 5, 2)
            text_rect.moveBottomLeft(point + QtCore.QPointF(11, -7))
            painter.setPen(QtGui.QPen(QtGui.QColor("#26333f"), 1.0))
            painter.setBrush(QtGui.QColor(12, 18, 24, 218))
            painter.drawRoundedRect(text_rect, 4.0, 4.0)
            painter.setPen(QtGui.QColor("#edf3f7"))
            painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignCenter, name)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        available = self.rect().adjusted(3, 3, -3, -3)
        viewport = QtCore.QRectF(available)
        center = viewport.center()
        pixels_per_metre = self._pixels_per_metre()

        painter.fillRect(self.rect(), QtGui.QColor("#11161d"))
        clip_shape = QtGui.QPainterPath()
        clip_shape.addRect(viewport)
        painter.save()
        painter.setClipPath(clip_shape)
        painter.fillPath(clip_shape, QtGui.QColor("#171f29"))

        player = self._player()
        view_center = self._view_center()
        self._custom_waypoint_hits = []
        self._enemy_hits = []

        map_drawn = False
        if self.show_texture and self.map_texture is not None:
            map_view = self.map_texture.render_view(
                view_center,
                pixels_per_metre,
                max(2, round(viewport.width())),
                max(2, round(viewport.height())),
            )
            painter.save()
            if map_view is not None:
                if self.heading_up:
                    painter.translate(center)
                    painter.rotate(-map_heading_degrees(player.get("heading")))
                    painter.translate(-center)
                painter.setOpacity(0.92)
                painter.drawImage(viewport, map_view)
                map_drawn = True
            elif not self.map_texture.image.isNull():
                # Never present a featureless black square when telemetry and the
                # calibration disagree. A dim full-zone texture makes the failure
                # explicit while the projection self-check waits for POIs.
                fallback = self.map_texture.image
                painter.setOpacity(0.38)
                painter.drawImage(viewport, fallback)
            painter.restore()
            painter.fillPath(clip_shape, QtGui.QColor(0, 0, 0, 24))

        collectible_kinds = {"chest", "red_orb", "plant", "ore"}
        enabled_poi_kinds = {
            kind for kind, enabled in self.poi_kind_visibility.items() if enabled
        }
        enabled_loot_kinds = {
            kind for kind, enabled in self.loot_kind_visibility.items() if enabled
        }
        all_poi_kinds_enabled = bool(self.poi_kind_visibility) and all(
            self.poi_kind_visibility.values()
        )
        if enabled_poi_kinds or enabled_loot_kinds:
            completed_elements = self.state.get("completed_elements", [])
            completed_element_ids = {
                str(value) for value in completed_elements
            } if isinstance(completed_elements, list) else set()
            for poi in self.pois:
                if not isinstance(poi, dict):
                    continue
                kind = str(poi.get("kind", "")).strip().lower()
                is_collectible = kind in collectible_kinds
                if is_collectible:
                    if kind not in enabled_loot_kinds:
                        continue
                elif kind in self.poi_kind_visibility:
                    if kind not in enabled_poi_kinds:
                        continue
                elif not all_poi_kinds_enabled:
                    # Preserve forward compatibility for unknown non-loot marker
                    # kinds without adding a premature UI category. Unknown kinds
                    # are shown only when the complete POI group is enabled.
                    continue
                if not self._world_in_view(poi, view_center, viewport):
                    continue
                point = self._world_to_screen(poi, center, pixels_per_metre, view_center)
                subkind = str(poi.get("subkind", "")).strip()
                collected = (
                    kind == "red_orb"
                    and str(poi.get("id") or "") in completed_element_ids
                )
                if collected:
                    painter.save()
                    painter.setOpacity(0.32)
                self._draw_poi_marker(painter, point, kind, subkind)
                if collected:
                    painter.restore()

        active_waypoint: dict[str, Any] | None = None
        if self.show_custom_waypoints:
            for waypoint in self.custom_waypoints:
                if not isinstance(waypoint, dict):
                    continue
                if safe_int(waypoint.get("id"), -1) == self.active_custom_waypoint_id:
                    active_waypoint = waypoint
                    break

            player_x = safe_float(player.get("x"), math.nan)
            player_y = safe_float(player.get("y"), math.nan)
            if active_waypoint is not None and self.show_route_line and math.isfinite(player_x) and math.isfinite(player_y):
                player_point_for_route = self._world_to_screen(
                    player, center, pixels_per_metre, view_center
                )
                destination_point = self._world_to_screen(
                    active_waypoint, center, pixels_per_metre, view_center
                )
                route_color = QtGui.QColor(
                    WAYPOINT_COLORS.get(
                        str(active_waypoint.get("color") or "cyan").lower(),
                        WAYPOINT_COLORS["cyan"],
                    )
                )
                route_color.setAlpha(145)
                painter.setPen(
                    QtGui.QPen(route_color, 1.5, QtCore.Qt.PenStyle.DashLine)
                )
                painter.drawLine(player_point_for_route, destination_point)

            for waypoint in self.custom_waypoints:
                if not isinstance(waypoint, dict):
                    continue
                if not self._world_in_view(waypoint, view_center, viewport, 24.0):
                    continue
                point = self._world_to_screen(
                    waypoint, center, pixels_per_metre, view_center
                )
                is_active = (
                    safe_int(waypoint.get("id"), -1)
                    == self.active_custom_waypoint_id
                )
                self._draw_custom_waypoint_marker(
                    painter, point, waypoint, is_active
                )

        enemies = self.state.get("enemies", []) if isinstance(self.state, dict) else []
        player_z = safe_float(player.get("z"), 0.0)
        if self.show_enemies and isinstance(enemies, list):
            for enemy in enemies:
                if not isinstance(enemy, dict):
                    continue
                enemy_x = safe_float(enemy.get("x"), math.nan)
                enemy_y = safe_float(enemy.get("y"), math.nan)
                if not (math.isfinite(enemy_x) and math.isfinite(enemy_y)):
                    continue
                if not self._world_in_view(enemy, view_center, viewport, 10.0):
                    continue
                point = self._world_to_screen(
                    enemy, center, pixels_per_metre, view_center
                )
                enemy_z = safe_float(enemy.get("z"), player_z)
                far = (
                    math.isfinite(enemy_z)
                    and math.isfinite(player_z)
                    and abs(enemy_z - player_z) > self.enemy_z_fade
                )
                fill = QtGui.QColor("#FF5348")
                if far:
                    fill.setAlpha(110)
                painter.setPen(QtGui.QPen(QtGui.QColor("#190d0d"), 1.0))
                painter.setBrush(fill)
                painter.drawEllipse(point, 2.8, 2.8)
                hit = self._enemy_hit_radius
                self._enemy_hits.append(
                    (
                        QtCore.QRectF(
                            point.x() - hit, point.y() - hit, hit * 2.0, hit * 2.0
                        ),
                        dict(enemy),
                    )
                )

        party = self.state.get("party", []) if isinstance(self.state, dict) else []
        player_uid = str(player.get("uid") or "")
        for member in party if self.show_party_members and isinstance(party, list) else []:
            if not isinstance(member, dict):
                continue
            hero_valid = bool(member.get("hero_valid", True))
            if not hero_valid and not self.dim_invalid_party_members:
                continue
            member_x = safe_float(member.get("x"), math.nan)
            member_y = safe_float(member.get("y"), math.nan)
            if not (math.isfinite(member_x) and math.isfinite(member_y)):
                continue
            member_uid = str(member.get("uid") or "")
            if player_uid and member_uid == player_uid:
                continue
            if not self._world_in_view(member, view_center, viewport, 28.0):
                continue

            point = self._world_to_screen(member, center, pixels_per_metre, view_center)
            class_color = {
                "mage": "#7aa2f7",
                "priest": "#d9b7ff",
                "rogue": "#79d7a5",
                "warrior": "#f0a36b",
            }.get(str(member.get("class") or "").strip().lower(), "#67b7ff")

            painter.save()
            if not hero_valid:
                painter.setOpacity(0.35)

            # Use the same Farever heading correction as the local-player
            # marker, with a slightly smaller arrow for party members.
            heading = safe_float(member.get("heading")) + (math.pi / 2.0)
            forward_x, forward_y = math.sin(heading), -math.cos(heading)
            side_x, side_y = -forward_y, forward_x
            tip = point + QtCore.QPointF(forward_x * 9.0, forward_y * 9.0)
            base = point - QtCore.QPointF(forward_x * 5.0, forward_y * 5.0)
            left = base + QtCore.QPointF(side_x * 5.0, side_y * 5.0)
            right = base - QtCore.QPointF(side_x * 5.0, side_y * 5.0)
            painter.setPen(QtGui.QPen(QtGui.QColor("#081016"), 1.5))
            painter.setBrush(QtGui.QColor(class_color))
            painter.drawPolygon(QtGui.QPolygonF([tip, left, right]))

            hp = safe_float(member.get("hp"), math.nan)
            max_hp = safe_float(member.get("max_hp"), math.nan)
            if (
                self.show_party_health_rings
                and member.get("attributes_valid", True)
                and math.isfinite(hp)
                and math.isfinite(max_hp)
                and max_hp > 0
            ):
                hp_ratio = max(0.0, min(1.0, hp / max_hp))
                hp_color = QtGui.QColor("#70d88b" if hp_ratio > 0.35 else "#ef6b6b")
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.setPen(QtGui.QPen(QtGui.QColor("#26333f"), 2.0))
                hp_ring = QtCore.QRectF(point.x() - 10, point.y() - 10, 20, 20)
                painter.drawEllipse(hp_ring)
                painter.setPen(QtGui.QPen(hp_color, 2.0))
                painter.drawArc(hp_ring, 90 * 16, round(-360 * 16 * hp_ratio))

            name = str(member.get("name") or "").strip()
            if self.show_party_names and name:
                metrics = painter.fontMetrics()
                label_rect = metrics.boundingRect(name).adjusted(-4, -2, 4, 2)
                label_rect.moveLeft(round(point.x() + 12))
                label_rect.moveBottom(round(point.y() - 4))
                painter.setPen(QtGui.QPen(QtGui.QColor("#26333f"), 1.0))
                painter.setBrush(QtGui.QColor(12, 18, 24, 218))
                painter.drawRoundedRect(QtCore.QRectF(label_rect), 3.0, 3.0)
                painter.setPen(QtGui.QColor("#f2f7fc"))
                painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignCenter, name)
            painter.restore()

        target_obj = self.state.get("target", {}) or {}
        if isinstance(target_obj, dict) and target_obj.get("exists"):
            point = self._world_to_screen(target_obj, center, pixels_per_metre, view_center)
            size = 7.0
            polygon = QtGui.QPolygonF([
                point + QtCore.QPointF(0, -size),
                point + QtCore.QPointF(size, 0),
                point + QtCore.QPointF(0, size),
                point + QtCore.QPointF(-size, 0),
            ])
            painter.setPen(QtGui.QPen(QtGui.QColor("#190d0d"), 1.5))
            painter.setBrush(QtGui.QColor("#ff6666"))
            painter.drawPolygon(polygon)

        player_x = safe_float(player.get("x"), math.nan)
        player_y = safe_float(player.get("y"), math.nan)
        if math.isfinite(player_x) and math.isfinite(player_y):
            player_point = self._world_to_screen(player, center, pixels_per_metre, view_center)
            # Farever's heading value is rotated 90 degrees clockwise relative
            # to the Atlas player triangle's forward axis. Correct the marker
            # counter-clockwise by 90 degrees without changing map orientation.
            heading = safe_float(player.get("heading")) + (math.pi / 2.0)
            forward_x, forward_y = math.sin(heading), -math.cos(heading)
            side_x, side_y = -forward_y, forward_x
            tip = player_point + QtCore.QPointF(forward_x * 14.0, forward_y * 14.0)
            base = player_point - QtCore.QPointF(forward_x * 7.0, forward_y * 7.0)
            left = base + QtCore.QPointF(side_x * 7.0, side_y * 7.0)
            right = base - QtCore.QPointF(side_x * 7.0, side_y * 7.0)
            painter.setPen(QtGui.QPen(QtGui.QColor("#081016"), 1.5))
            painter.setBrush(QtGui.QColor("#f4f7fa"))
            painter.drawPolygon(QtGui.QPolygonF([tip, left, right]))

        if self.show_texture and self.map_texture is not None and not map_drawn:
            painter.setPen(QtGui.QColor("#ffd27a"))
            painter.drawText(
                viewport.adjusted(14, 14, -14, -14),
                QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignHCenter,
                "Viewport outside texture — showing full-map fallback",
            )
        painter.restore()

        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor("#8d9aa7"), 1.5))
        painter.drawRect(viewport)
        # The map is permanently north-up. Keep all cardinal directions
        # visible around the viewport; north is emphasized in bold red.
        cardinal_font = painter.font()
        cardinal_font.setPointSizeF(max(cardinal_font.pointSizeF(), 10.0))

        cardinal_rects = {
            "N": QtCore.QRectF(viewport.center().x() - 14.0, viewport.top() + 7.0, 28.0, 20.0),
            "E": QtCore.QRectF(viewport.right() - 29.0, viewport.center().y() - 10.0, 22.0, 20.0),
            "S": QtCore.QRectF(viewport.center().x() - 14.0, viewport.bottom() - 27.0, 28.0, 20.0),
            "W": QtCore.QRectF(viewport.left() + 7.0, viewport.center().y() - 10.0, 22.0, 20.0),
        }

        for label in ("N", "E", "S", "W"):
            label_font = QtGui.QFont(cardinal_font)
            label_font.setBold(label == "N")
            painter.setFont(label_font)

            rect = cardinal_rects[label]
            shadow_rect = rect.translated(1.0, 1.0)
            painter.setPen(QtGui.QColor(5, 9, 13, 225))
            painter.drawText(shadow_rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)

            if label == "N":
                painter.setPen(QtGui.QColor(235, 68, 68, 245))
            else:
                painter.setPen(QtGui.QColor(235, 241, 247, 220))
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
