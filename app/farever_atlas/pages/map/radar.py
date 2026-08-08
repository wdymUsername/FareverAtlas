"""Map canvas rendering and direct map interaction."""

from __future__ import annotations

import math
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import (
    WAYPOINT_COLORS,
    discover_project_asset,
    map_heading_degrees,
    safe_float,
    safe_int,
)
from .data import MapTexture, Snapshot
from .fog import FogOfWar
from .fow_layers import canonical_fow_layer

# Built once: rebuilding these per marker cost ~7.6k QColor allocations a frame.
_POI_COLORS: dict[str, QtGui.QColor] = {
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
_POI_COLOR_FALLBACK = QtGui.QColor("#9ba7b4")

_COLLECTIBLE_KINDS = frozenset({"chest", "red_orb", "plant", "ore", "gatherable"})
# Coarse enough that most views touch few buckets, fine enough that a bucket
# holds a handful of POIs. Only used to narrow the per-frame view cull.
_POI_GRID_CELL_M = 128.0


class RadarWidget(QtWidgets.QWidget):
    zoomRequested = QtCore.Signal(int)
    panStateChanged = QtCore.Signal(bool)
    customWaypointContextRequested = QtCore.Signal(object, object)
    playerContextRequested = QtCore.Signal(object)
    fowLineToolChanged = QtCore.Signal(bool)
    fowLineDraftChanged = QtCore.Signal()
    fowLayerDirtyChanged = QtCore.Signal()

    # Zoom levels are defined against this reference canvas height. Window
    # resizing changes the visible world extent, not the world-to-pixel scale.
    ZOOM_REFERENCE_HEIGHT_PX = 600.0
    ICON_ATLAS_CELL_SIZE = 128
    ICON_ATLAS_COLUMNS = 8
    WAYPOINT_ICON_SIZE = 24
    # Game UI icons/playerCursor.png — white chevron + orange diamond (points +X).
    PLAYER_ARROW_ASSET = "playerCursor.png"
    PLAYER_ARROW_SIZE = 28
    # Must match native_bridge interactible sweep (XY metres / Z cull).
    # Static loot outside this bubble is drawn from the POI file; inside the
    # bubble, a static marker is suppressed only when a live interactible
    # covers it (failed/empty live sweeps must not blank the map).
    LOOT_LIVE_RANGE_M = 600.0
    LOOT_LIVE_Z_CULL_M = 80.0
    LOOT_LIVE_MATCH_M = 12.0

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
        self.show_players = True
        self.show_player_names = False
        self.show_route_line = True
        # World units of elevation difference before an enemy marker is dimmed.
        self.enemy_z_fade = 30.0
        # Same elevation fade for non-party player markers.
        self.player_z_fade = 30.0
        # Metres of |Δz| before a marker gets an up/down chevron.
        self.z_indicator_threshold = 2.0
        self.active_custom_waypoint_id: int | None = None
        self.active_gather_target: dict[str, Any] | None = None
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
        self.fog = FogOfWar.load()
        self.map_texture = map_texture
        self._waypoint_icon_cache: dict[int, QtGui.QImage] = {}
        self._loose_kind_icon_cache: dict[str, QtGui.QImage] = {}
        # Marker rendering is the paint hot path: pre-render each marker variant
        # to a pixmap and pre-parse the static POI file into flat tuples, both
        # keyed on the marker filters so a filter change rebuilds them.
        self._marker_sprite_cache: dict[
            tuple[str, str, str, float], tuple[QtGui.QPixmap, float, float]
        ] = {}
        self._prepared_source: list[Any] | None = None
        self._prepared_filters: tuple[Any, ...] | None = None
        self._prepared_pois: list[tuple[Any, ...]] = []
        self._poi_grid: dict[tuple[int, int], list[int]] = {}
        self._poi_grid_origin: tuple[float, float] = (0.0, 0.0)
        self._player_arrow_icon_cache: QtGui.QImage | None = None
        self._player_arrow_icon_asset: str | None = None
        self._player_arrow_icon_missing = False
        self.view_center_world: tuple[float, float] | None = None
        self._follow_target_key: str | None = None
        self._follow_target_name: str = ""
        self._offline_center_world: tuple[float, float] | None = None
        self._drag_last: QtCore.QPointF | None = None
        self._drag_active = False
        self._drag_moved = False
        self._drag_started_panned = False
        self._custom_waypoint_hits: list[tuple[QtCore.QRectF, dict[str, Any]]] = []
        self._enemy_hits: list[tuple[QtCore.QRectF, dict[str, Any]]] = []
        self._interactible_hits: list[tuple[QtCore.QRectF, dict[str, Any]]] = []
        self._player_hits: list[tuple[QtCore.QRectF, dict[str, Any]]] = []
        self._hovered_custom_waypoint_id: int | None = None
        self._hovered_enemy_id: str | None = None
        self._hovered_interactible_id: str | None = None
        self._live_marker_signature: tuple[Any, ...] | None = None
        # Generous hit slack around the small enemy dots so hover is usable.
        self._enemy_hit_radius = 9.0
        self._interactible_hit_radius = 10.0
        self._player_hit_radius = 12.0
        # Cursor-shape changes cannot be interpolated by Qt, so drag release uses
        # a short staged transition: closed hand -> open hand -> resting cursor.
        # The generation token prevents delayed callbacks from overriding a newer
        # hover state or a newly started drag.
        self._cursor_release_generation = 0

        # FOW Points tool: edit vertices on the Align edit layer.
        # Empty draft click starts a new ring; Close commits into the edit layer.
        self._fow_line_tool = False
        self._fow_line_draft: list[tuple[float, float]] = []
        self._fow_line_cursor: tuple[float, float] | None = None
        self._fow_edit_ring: int | None = None
        self._fow_edit_vertex: int | None = None
        self._fow_edit_dragging = False
        self._fow_edit_drag_last_world: tuple[float, float] | None = None
        self._fow_hover_ring: int | None = None
        self._fow_hover_vertex: int | None = None
        self._fow_hover_edge: int | None = None
        self._fow_selected: set[tuple[int, int]] = set()
        self._fow_marquee_origin: QtCore.QPointF | None = None
        self._fow_marquee_current: QtCore.QPointF | None = None
        self._fow_marquee_active = False
        self._fow_marquee_add = False
        self._fow_marquee_threshold_px = 5.0
        self._fow_vertex_hit_px = 9.0
        self._fow_edge_hit_px = 7.0
        self._z4_drag_mode = False
        self._z4_dragging = False
        self._z4_drag_last_world: tuple[float, float] | None = None
        self._fow_edit_layer = "Z4"
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)

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
        self._sync_follow_center()
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
        nearby_players = self.state.get("players", []) if isinstance(self.state, dict) else []
        players_signature = tuple(
            (
                str(other.get("id") or ""),
                str(other.get("uid") or other.get("name") or ""),
                safe_float(other.get("x"), 0.0),
                safe_float(other.get("y"), 0.0),
                safe_float(other.get("heading"), 0.0),
                safe_float(other.get("z"), 0.0),
            )
            for other in nearby_players
            if isinstance(other, dict)
        ) if isinstance(nearby_players, list) else ()
        interactibles = (
            self.state.get("interactibles", []) if isinstance(self.state, dict) else []
        )
        interactible_signature = tuple(
            (
                str(item.get("id") or ""),
                str(item.get("kind") or ""),
                safe_float(item.get("x"), 0.0),
                safe_float(item.get("y"), 0.0),
                safe_float(item.get("z"), 0.0),
            )
            for item in interactibles
            if isinstance(item, dict)
        ) if isinstance(interactibles, list) else ()
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
            players_signature,
            interactible_signature,
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

    def set_gather_target(self, target: dict[str, Any] | None) -> None:
        if target is None:
            self.active_gather_target = None
        else:
            self.active_gather_target = dict(target)
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
        camera_heading = safe_float(raw.get("camera_heading"), math.nan)
        if math.isfinite(camera_heading):
            self._display_player["camera_heading"] = camera_heading

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

        target_camera = safe_float(raw.get("camera_heading"), math.nan)
        if math.isfinite(target_camera):
            current_camera = self._display_player.get("camera_heading", target_camera)
            if not math.isfinite(current_camera):
                current_camera = target_camera
            camera_delta = self._shortest_angle_delta(target_camera, current_camera)
            if abs(camera_delta) > 0.0002:
                camera_alpha = 1.0 - math.exp(-dt / 0.075)
                current_camera += camera_delta * camera_alpha
                pose_changed = True
            else:
                current_camera = target_camera
            self._display_player["camera_heading"] = current_camera

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
        if math.isfinite(self._display_player.get("camera_heading", math.nan)):
            player["camera_heading"] = self._display_player["camera_heading"]
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

    def is_following(self) -> bool:
        return bool(self._follow_target_key)

    def follow_target_key(self) -> str | None:
        return self._follow_target_key

    def follow_target_name(self) -> str:
        return self._follow_target_name

    @staticmethod
    def follow_key_for(entry: dict[str, Any]) -> str:
        uid = str(entry.get("uid") or "").strip()
        if uid:
            return uid
        name = str(entry.get("name") or "").strip()
        return f"name:{name.lower()}" if name else ""

    def clear_follow(self) -> None:
        had = bool(self._follow_target_key)
        self._follow_target_key = None
        self._follow_target_name = ""
        if had:
            self.panStateChanged.emit(self.is_panned())

    def set_follow_target(self, entry: dict[str, Any]) -> bool:
        key = self.follow_key_for(entry)
        if not key:
            return False
        x = safe_float(entry.get("x"), math.nan)
        y = safe_float(entry.get("y"), math.nan)
        if not (math.isfinite(x) and math.isfinite(y)):
            live = self._lookup_follow_pose(key)
            if live is None:
                return False
            x, y = live
        self._follow_target_key = key
        self._follow_target_name = str(entry.get("name") or "").strip()
        self.center_on(x, y)
        return True

    def _lookup_follow_pose(self, key: str) -> tuple[float, float] | None:
        if not key:
            return None
        candidates: list[dict[str, Any]] = []
        party = self.state.get("party", []) if isinstance(self.state, dict) else []
        players = self.state.get("players", []) if isinstance(self.state, dict) else []
        if isinstance(party, list):
            candidates.extend(member for member in party if isinstance(member, dict))
        if isinstance(players, list):
            candidates.extend(other for other in players if isinstance(other, dict))
        for entry in candidates:
            if self.follow_key_for(entry) != key:
                continue
            x = safe_float(entry.get("x"), math.nan)
            y = safe_float(entry.get("y"), math.nan)
            if math.isfinite(x) and math.isfinite(y):
                return (x, y)
        return None

    def _sync_follow_center(self) -> None:
        if not self._follow_target_key:
            return
        pose = self._lookup_follow_pose(self._follow_target_key)
        if pose is None:
            # Target left the layer / lost pose — drop follow so the view does
            # not freeze on the last point with is_following() still true.
            self.clear_follow()
            return
        next_center = pose
        if self.map_texture is not None and not self._local_instance_mode():
            next_center = self.map_texture.clamp_world_center(*next_center)
        self.view_center_world = next_center

    @property
    def fow_line_tool_active(self) -> bool:
        return self._fow_line_tool

    @property
    def fow_line_draft_count(self) -> int:
        return len(self._fow_line_draft)

    @property
    def fow_edit_layer(self) -> str:
        return self._fow_edit_layer

    @property
    def fow_selection_count(self) -> int:
        return len(self._fow_selected)

    def set_fow_edit_layer(self, tier: str) -> None:
        key = canonical_fow_layer(tier)
        if key is None:
            return
        if key == self._fow_edit_layer:
            return
        if self._fow_line_tool and self.fog.any_layer_dirty():
            self.fog.bake_dirty_layers()
            self.fowLayerDirtyChanged.emit()
        self._fow_edit_layer = key
        self._fow_line_draft.clear()
        self._fow_line_cursor = None
        self._fow_clear_edit_state()
        if self._fow_line_tool:
            self.fog.promote_layer_for_edit(key)
            self.fowLayerDirtyChanged.emit()
        self.fowLineDraftChanged.emit()
        self.update()

    def set_z4_drag_mode(self, active: bool) -> None:
        active = bool(active)
        if active == self._z4_drag_mode:
            return
        self._z4_drag_mode = active
        self._z4_dragging = False
        self._z4_drag_last_world = None
        if active:
            self.set_fow_line_tool(False)
            self.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
        elif not self._fow_line_tool:
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.update()

    @property
    def z4_drag_mode_active(self) -> bool:
        return self._z4_drag_mode

    def set_fow_line_tool(self, active: bool) -> None:
        active = bool(active)
        if active == self._fow_line_tool:
            return
        if active:
            self.set_z4_drag_mode(False)
            self.fog.promote_layer_for_edit(self._fow_edit_layer)
            self.fowLayerDirtyChanged.emit()
        self._fow_line_tool = active
        if not active:
            if self.fog.any_layer_dirty():
                self.fog.bake_dirty_layers()
                self.fowLayerDirtyChanged.emit()
            self._fow_line_draft.clear()
            self._fow_line_cursor = None
            self._fow_clear_edit_state()
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        else:
            self.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.fowLineToolChanged.emit(self._fow_line_tool)
        self.fowLineDraftChanged.emit()
        self.update()

    def fow_line_undo(self) -> None:
        if not self._fow_line_draft:
            return
        self._fow_line_draft.pop()
        self.fowLineDraftChanged.emit()
        self.update()

    def fow_line_close(self) -> bool:
        if len(self._fow_line_draft) < 3:
            return False
        layer = self._fow_edit_layer
        rings = [list(ring) for ring in self.fog.source_rings(layer)]
        local_ring = [
            self.fog.layer_local_point(layer, float(x), float(y))
            for x, y in self._fow_line_draft
        ]
        rings.append(local_ring)
        self._fow_commit_rings(rings)
        if not self.fog.layer_enabled(layer):
            self.fog.set_layer_enabled(layer, True)
        self._fow_line_draft.clear()
        self._fow_line_cursor = None
        self.fowLineDraftChanged.emit()
        self.update()
        return True

    def fow_line_clear_custom(self) -> None:
        """Clear editable rings for the current edit layer (session Clear)."""
        self._fow_line_draft.clear()
        self._fow_line_cursor = None
        self._fow_clear_edit_state()
        self._fow_commit_rings([])
        self.fowLineDraftChanged.emit()
        self.update()

    def bake_fow_edit_layer(self) -> bool:
        ok = self.fog.bake_layer(self._fow_edit_layer)
        self.fowLayerDirtyChanged.emit()
        self.update()
        return ok

    def reset_fow_edit_geometry(self) -> bool:
        ok = self.fog.reset_layer_geometry(self._fow_edit_layer)
        self._fow_clear_edit_state()
        if self._fow_line_tool:
            self.fog.promote_layer_for_edit(self._fow_edit_layer)
        self.fowLayerDirtyChanged.emit()
        self.fowLineDraftChanged.emit()
        self.update()
        return ok

    def _fow_clear_edit_state(self) -> None:
        self._fow_edit_ring = None
        self._fow_edit_vertex = None
        self._fow_edit_dragging = False
        self._fow_edit_drag_last_world = None
        self._fow_hover_ring = None
        self._fow_hover_vertex = None
        self._fow_hover_edge = None
        self._fow_selected.clear()
        self._fow_clear_marquee()

    def _fow_clear_marquee(self) -> None:
        self._fow_marquee_origin = None
        self._fow_marquee_current = None
        self._fow_marquee_active = False
        self._fow_marquee_add = False

    def _fow_commit_rings(self, rings: list[list[tuple[float, float]]]) -> None:
        self.fog.set_editable_rings(self._fow_edit_layer, rings, mark_dirty=True)
        self.fowLayerDirtyChanged.emit()

    def _fow_line_add_vertex_at(self, screen_point: QtCore.QPointF) -> bool:
        world = self.world_at_screen(screen_point)
        if world is None:
            return False
        self._fow_line_draft.append((float(world["x"]), float(world["y"])))
        self.fowLineDraftChanged.emit()
        self.update()
        return True

    def _fow_screen_point(
        self, x: float, y: float
    ) -> QtCore.QPointF | None:
        viewport = QtCore.QRectF(self.rect().adjusted(3, 3, -3, -3))
        center = viewport.center()
        view_center = self._view_center()
        pixels_per_metre = self._pixels_per_metre()
        if pixels_per_metre <= 1e-9:
            return None
        return self._world_to_screen(
            {"x": x, "y": y}, center, pixels_per_metre, view_center
        )

    def _fow_hit_test(
        self, screen_point: QtCore.QPointF
    ) -> tuple[str, int, int] | None:
        """Return ('vertex'|'edge', ring_index, index) or None."""
        best_vertex: tuple[float, int, int] | None = None
        best_edge: tuple[float, int, int] | None = None
        for ring_i, ring in enumerate(
            self.fog.transformed_layer_rings(self._fow_edit_layer)
        ):
            n = len(ring)
            if n < 3:
                continue
            screen_pts: list[QtCore.QPointF] = []
            for x, y in ring:
                pt = self._fow_screen_point(x, y)
                if pt is None:
                    screen_pts = []
                    break
                screen_pts.append(pt)
            if len(screen_pts) != n:
                continue
            for vert_i, pt in enumerate(screen_pts):
                dist = math.hypot(
                    pt.x() - screen_point.x(), pt.y() - screen_point.y()
                )
                if dist <= self._fow_vertex_hit_px and (
                    best_vertex is None or dist < best_vertex[0]
                ):
                    best_vertex = (dist, ring_i, vert_i)
            for edge_i in range(n):
                a = screen_pts[edge_i]
                b = screen_pts[(edge_i + 1) % n]
                dist, _t, _proj = self._point_segment_distance(screen_point, a, b)
                if dist <= self._fow_edge_hit_px and (
                    best_edge is None or dist < best_edge[0]
                ):
                    best_edge = (dist, ring_i, edge_i)
        if best_vertex is not None:
            return ("vertex", best_vertex[1], best_vertex[2])
        if best_edge is not None:
            return ("edge", best_edge[1], best_edge[2])
        return None

    @staticmethod
    def _point_segment_distance(
        point: QtCore.QPointF, a: QtCore.QPointF, b: QtCore.QPointF
    ) -> tuple[float, float, QtCore.QPointF]:
        ax, ay = a.x(), a.y()
        bx, by = b.x(), b.y()
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        if length_sq <= 1e-12:
            return math.hypot(point.x() - ax, point.y() - ay), 0.0, QtCore.QPointF(ax, ay)
        t = ((point.x() - ax) * dx + (point.y() - ay) * dy) / length_sq
        t = max(0.0, min(1.0, t))
        proj = QtCore.QPointF(ax + t * dx, ay + t * dy)
        return math.hypot(point.x() - proj.x(), point.y() - proj.y()), t, proj

    def _fow_begin_vertex_edit(self, ring_i: int, vert_i: int) -> None:
        self._fow_edit_ring = ring_i
        self._fow_edit_vertex = vert_i
        self._fow_edit_dragging = True
        self._fow_edit_drag_last_world = None
        self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)

    def _fow_insert_vertex_on_edge(
        self, ring_i: int, edge_i: int, screen_point: QtCore.QPointF
    ) -> bool:
        world = self.world_at_screen(screen_point)
        if world is None:
            return False
        layer = self._fow_edit_layer
        rings = [list(ring) for ring in self.fog.source_rings(layer)]
        if ring_i < 0 or ring_i >= len(rings):
            return False
        ring = rings[ring_i]
        insert_at = edge_i + 1
        ring.insert(
            insert_at,
            self.fog.layer_local_point(
                layer, float(world["x"]), float(world["y"])
            ),
        )
        self._fow_commit_rings(rings)
        self._fow_selected = {(ring_i, insert_at)}
        self._fow_begin_vertex_edit(ring_i, insert_at)
        self.fowLineDraftChanged.emit()
        self.update()
        return True

    def _fow_move_edit_vertex(self, screen_point: QtCore.QPointF) -> bool:
        if self._fow_edit_ring is None or self._fow_edit_vertex is None:
            return False
        world = self.world_at_screen(screen_point)
        if world is None:
            return False
        wx, wy = float(world["x"]), float(world["y"])
        layer = self._fow_edit_layer
        rings = [list(ring) for ring in self.fog.source_rings(layer)]
        selection = self._fow_selected or {
            (self._fow_edit_ring, self._fow_edit_vertex)
        }
        if self._fow_edit_drag_last_world is None:
            # First move: snap primary vertex to cursor; others keep relative offset.
            primary = (self._fow_edit_ring, self._fow_edit_vertex)
            if primary[0] < 0 or primary[0] >= len(rings):
                return False
            if primary[1] < 0 or primary[1] >= len(rings[primary[0]]):
                return False
            old_world = self.fog.layer_world_point(
                layer, *rings[primary[0]][primary[1]]
            )
            dx = wx - old_world[0]
            dy = wy - old_world[1]
        else:
            dx = wx - self._fow_edit_drag_last_world[0]
            dy = wy - self._fow_edit_drag_last_world[1]
        if abs(dx) + abs(dy) <= 1e-12:
            self._fow_edit_drag_last_world = (wx, wy)
            return True
        for ring_i, vert_i in selection:
            if ring_i < 0 or ring_i >= len(rings):
                continue
            if vert_i < 0 or vert_i >= len(rings[ring_i]):
                continue
            ox, oy = self.fog.layer_world_point(layer, *rings[ring_i][vert_i])
            rings[ring_i][vert_i] = self.fog.layer_local_point(
                layer, ox + dx, oy + dy
            )
        self._fow_edit_drag_last_world = (wx, wy)
        self._fow_commit_rings(rings)
        self.update()
        return True

    def _fow_finish_vertex_edit(self) -> None:
        self._fow_edit_ring = None
        self._fow_edit_vertex = None
        self._fow_edit_dragging = False
        self._fow_edit_drag_last_world = None
        self.fowLineDraftChanged.emit()
        if self._fow_line_tool:
            self.setCursor(QtCore.Qt.CursorShape.CrossCursor)

    def _fow_delete_vertex(self, ring_i: int, vert_i: int) -> bool:
        return self._fow_delete_vertices({(ring_i, vert_i)})

    def _fow_delete_vertices(self, victims: set[tuple[int, int]]) -> bool:
        if not victims:
            return False
        layer = self._fow_edit_layer
        rings = [list(ring) for ring in self.fog.source_rings(layer)]
        by_ring: dict[int, list[int]] = {}
        for ring_i, vert_i in victims:
            by_ring.setdefault(ring_i, []).append(vert_i)
        for ring_i in sorted(by_ring.keys(), reverse=True):
            if ring_i < 0 or ring_i >= len(rings):
                continue
            verts = sorted(set(by_ring[ring_i]), reverse=True)
            ring = rings[ring_i]
            for vert_i in verts:
                if 0 <= vert_i < len(ring):
                    ring.pop(vert_i)
            if len(ring) < 3:
                rings.pop(ring_i)
        self._fow_commit_rings(rings)
        self._fow_clear_edit_state()
        self.fowLineDraftChanged.emit()
        self.update()
        return True

    def _fow_select_marquee(self) -> None:
        if (
            self._fow_marquee_origin is None
            or self._fow_marquee_current is None
        ):
            return
        rect = QtCore.QRectF(self._fow_marquee_origin, self._fow_marquee_current).normalized()
        hits: set[tuple[int, int]] = set()
        for ring_i, ring in enumerate(
            self.fog.transformed_layer_rings(self._fow_edit_layer)
        ):
            for vert_i, (x, y) in enumerate(ring):
                pt = self._fow_screen_point(x, y)
                if pt is not None and rect.contains(pt):
                    hits.add((ring_i, vert_i))
        if self._fow_marquee_add:
            self._fow_selected |= hits
        else:
            self._fow_selected = hits
        self.fowLineDraftChanged.emit()

    def _fow_paint_marquee(self, painter: QtGui.QPainter) -> None:
        if (
            not self._fow_marquee_active
            or self._fow_marquee_origin is None
            or self._fow_marquee_current is None
        ):
            return
        rect = QtCore.QRectF(
            self._fow_marquee_origin, self._fow_marquee_current
        ).normalized()
        painter.save()
        pen = QtGui.QPen(QtGui.QColor(255, 220, 96, 220))
        pen.setWidthF(1.2)
        pen.setCosmetic(True)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtGui.QColor(255, 220, 96, 36))
        painter.drawRect(rect)
        painter.restore()

    def recenter(self) -> None:
        was_panned = self.view_center_world is not None or bool(self._follow_target_key)
        self.clear_follow()
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
        if self.map_texture is not None and not self._local_instance_mode():
            next_center = self.map_texture.clamp_world_center(*next_center)
        self.view_center_world = next_center
        self.panStateChanged.emit(True)
        self.update()

    def _pixels_per_metre(self) -> float:
        return self.ZOOM_REFERENCE_HEIGHT_PX / (2.0 * max(self.radius_m, 1.0))

    def _instance_state(self) -> dict[str, Any]:
        instance = self.state.get("instance", {}) if isinstance(self.state, dict) else {}
        return instance if isinstance(instance, dict) else {}

    def _local_instance_mode(self) -> bool:
        instance = self._instance_state()
        kind = str(instance.get("type") or "").strip().lower()
        return kind in {"dungeon", "rift", "instance"} or bool(instance.get("is_dungeon"))

    def _fog_hides_point(self, x: float, y: float) -> bool:
        if not self.fog.enabled or not self.fog.hide_markers:
            return False
        if not (math.isfinite(x) and math.isfinite(y)):
            return False
        return not self.fog.world_is_accessible(x, y)

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

    def player_at(self, point: QtCore.QPointF) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_distance = math.inf
        for hit_rect, player in self._player_hits:
            if not hit_rect.contains(point):
                continue
            center = hit_rect.center()
            distance = math.hypot(point.x() - center.x(), point.y() - center.y())
            if distance < best_distance:
                best_distance = distance
                best = player
        return dict(best) if best is not None else None

    def _register_player_hit(
        self,
        point: QtCore.QPointF,
        player: dict[str, Any],
        *,
        label_rect: QtCore.QRect | QtCore.QRectF | None = None,
        hit_radius: float | None = None,
    ) -> None:
        radius = self._player_hit_radius if hit_radius is None else float(hit_radius)
        hit = QtCore.QRectF(
            point.x() - radius,
            point.y() - radius,
            radius * 2.0,
            radius * 2.0,
        )
        if label_rect is not None:
            hit = hit.united(QtCore.QRectF(label_rect))
        self._player_hits.append((hit, dict(player)))

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

    def interactible_at(self, point: QtCore.QPointF) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_distance = math.inf
        for hit_rect, item in self._interactible_hits:
            if not hit_rect.contains(point):
                continue
            center = hit_rect.center()
            distance = math.hypot(point.x() - center.x(), point.y() - center.y())
            if distance < best_distance:
                best_distance = distance
                best = item
        return dict(best) if best is not None else None

    @staticmethod
    def _enemy_display_name(enemy: dict[str, Any]) -> str:
        kind = str(enemy.get("kind") or "").strip()
        if not kind:
            return "Enemy"
        # Creature ids arrive as HashLink identifiers like Crimson_Z2W_Sword_2.
        return " ".join(part for part in kind.replace("_", " ").split() if part)

    @staticmethod
    def _node_size_label(item: dict[str, Any]) -> str:
        """Return small/medium/large from live name or static POI name."""
        explicit = str(item.get("size") or "").strip().lower()
        if explicit in {"small", "medium", "large"}:
            return explicit
        blob = " ".join(
            str(item.get(key) or "") for key in ("name", "kind", "subkind")
        ).lower()
        if "small" in blob:
            return "small"
        if "medium" in blob:
            return "medium"
        if "large" in blob or "_big" in blob or " big" in blob:
            return "large"
        return ""

    def _ensure_prepared_pois(self) -> None:
        """Parse the static POI file into flat tuples once per POI/filter change.

        Only the parsing and the kind filters are cached here. Anything driven
        by telemetry — live-feed suppression, collected orbs, the view cull —
        stays in the paint loop.
        """
        filters = (
            tuple(sorted(self.poi_kind_visibility.items())),
            tuple(sorted(self.loot_kind_visibility.items())),
            tuple(sorted(self.loot_kind_icon_mode.items())),
            round(float(self.devicePixelRatioF() or 1.0), 3),
        )
        if self._prepared_source is self.pois and self._prepared_filters == filters:
            return
        self._prepared_source = self.pois
        self._prepared_filters = filters
        self._marker_sprite_cache.clear()

        enabled_poi_kinds = {
            kind for kind, enabled in self.poi_kind_visibility.items() if enabled
        }
        enabled_loot_kinds = {
            kind for kind, enabled in self.loot_kind_visibility.items() if enabled
        }
        all_poi_kinds_enabled = bool(self.poi_kind_visibility) and all(
            self.poi_kind_visibility.values()
        )
        gatherable_visible = bool(enabled_loot_kinds & {"plant", "ore"})

        prepared: list[tuple[Any, ...]] = []
        for poi in self.pois:
            if not isinstance(poi, dict):
                continue
            kind = str(poi.get("kind", "")).strip().lower()
            is_collectible = kind in _COLLECTIBLE_KINDS
            if is_collectible:
                visible = (
                    gatherable_visible
                    if kind == "gatherable"
                    else kind in enabled_loot_kinds
                )
                if not visible:
                    continue
            elif kind in self.poi_kind_visibility:
                if kind not in enabled_poi_kinds:
                    continue
            elif not all_poi_kinds_enabled:
                continue
            # Matches the legacy helpers: position falls back to the origin so a
            # malformed record still renders where it always did, while the fog
            # test is skipped when the coordinates are not finite.
            raw_x = safe_float(poi.get("x"), math.nan)
            raw_y = safe_float(poi.get("y"), math.nan)
            has_position = math.isfinite(raw_x) and math.isfinite(raw_y)
            x = raw_x if has_position else 0.0
            y = raw_y if has_position else 0.0
            subkind = str(poi.get("subkind", "")).strip()
            size = self._node_size_label(poi) if is_collectible else ""
            prepared.append(
                (
                    x,
                    y,
                    safe_float(poi.get("z"), math.nan),
                    kind,
                    size,
                    is_collectible,
                    has_position,
                    str(poi.get("id") or ""),
                    self._marker_sprite(kind, subkind, size),
                    poi,
                )
            )
        self._prepared_pois = prepared

        grid: dict[tuple[int, int], list[int]] = {}
        if prepared:
            origin_x = min(entry[0] for entry in prepared)
            origin_y = min(entry[1] for entry in prepared)
            for index, entry in enumerate(prepared):
                cell = (
                    int((entry[0] - origin_x) // _POI_GRID_CELL_M),
                    int((entry[1] - origin_y) // _POI_GRID_CELL_M),
                )
                grid.setdefault(cell, []).append(index)
            self._poi_grid_origin = (origin_x, origin_y)
        self._poi_grid = grid

    def _prepared_poi_candidates(
        self, center_x: float, center_y: float, half_w: float, half_h: float
    ) -> Any:
        """Indices into the prepared list worth testing against the view box."""
        prepared = self._prepared_pois
        grid = self._poi_grid
        if not prepared or not grid:
            return range(len(prepared))
        if not (
            math.isfinite(center_x)
            and math.isfinite(center_y)
            and math.isfinite(half_w)
            and math.isfinite(half_h)
        ):
            return range(len(prepared))
        origin_x, origin_y = self._poi_grid_origin
        first_col = int((center_x - half_w - origin_x) // _POI_GRID_CELL_M)
        last_col = int((center_x + half_w - origin_x) // _POI_GRID_CELL_M)
        first_row = int((center_y - half_h - origin_y) // _POI_GRID_CELL_M)
        last_row = int((center_y + half_h - origin_y) // _POI_GRID_CELL_M)
        spanned = (last_col - first_col + 1) * (last_row - first_row + 1)
        # Zoomed far out the view touches everything, so walking buckets would
        # cost more than a straight scan.
        if spanned >= len(grid):
            return range(len(prepared))
        candidates: list[int] = []
        for col in range(first_col, last_col + 1):
            for row in range(first_row, last_row + 1):
                bucket = grid.get((col, row))
                if bucket is not None:
                    candidates.extend(bucket)
        return candidates

    @classmethod
    def _interactible_display_name(cls, item: dict[str, Any]) -> str:
        name = str(item.get("name") or "").strip()
        kind = str(item.get("kind") or "").strip()
        parts = [
            part
            for part in name.replace("_", " ").split()
            if part and part.lower() != "generic"
        ]
        pretty = " ".join(parts) if parts else (kind.title() if kind else "Node")
        size = cls._node_size_label(item)
        if size and size not in pretty.lower():
            pretty = f"{pretty} ({size.title()})"
        return pretty

    def _view_half_extents(
        self,
        viewport: QtCore.QRectF,
        margin_pixels: float = 12.0,
    ) -> tuple[float, float]:
        pixels_per_metre = max(1e-9, self._pixels_per_metre())
        margin_m = margin_pixels / pixels_per_metre
        return (
            viewport.width() / (2.0 * pixels_per_metre) + margin_m,
            viewport.height() / (2.0 * pixels_per_metre) + margin_m,
        )

    def _world_in_view(
        self,
        obj: dict[str, Any],
        view_center: dict[str, Any],
        viewport: QtCore.QRectF,
        margin_pixels: float = 12.0,
        *,
        half_width_m: float | None = None,
        half_height_m: float | None = None,
    ) -> bool:
        if half_width_m is None or half_height_m is None:
            half_width_m, half_height_m = self._view_half_extents(
                viewport, margin_pixels
            )
        dx = abs(safe_float(obj.get("x")) - safe_float(view_center.get("x")))
        dy = abs(safe_float(obj.get("y")) - safe_float(view_center.get("y")))
        return dx <= half_width_m and dy <= half_height_m

    def _cancel_cursor_release_ease(self) -> None:
        self._cursor_release_generation += 1

    def _resting_cursor_for_point(
        self, point: QtCore.QPointF | None = None
    ) -> QtCore.Qt.CursorShape:
        if point is None:
            point = QtCore.QPointF(
                self.mapFromGlobal(QtGui.QCursor.pos())
            )
        if self.player_at(point) is not None:
            return QtCore.Qt.CursorShape.PointingHandCursor
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
        if self._fow_line_tool:
            point = QtCore.QPointF(event.pos())
            if self._fow_line_draft:
                self.fow_line_undo()
            elif self._fow_selected:
                self._fow_delete_vertices(set(self._fow_selected))
            else:
                hit = self._fow_hit_test(point)
                if hit is not None and hit[0] == "vertex":
                    self._fow_delete_vertex(hit[1], hit[2])
            event.accept()
            return
        point = QtCore.QPointF(event.pos())
        player = self.player_at(point)
        if player is not None and not player.get("is_self"):
            self.playerContextRequested.emit(player)
            event.accept()
            return
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
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            center = self._view_center()
            center_x = safe_float(center.get("x"), math.nan)
            center_y = safe_float(center.get("y"), math.nan)
            if math.isfinite(center_x) and math.isfinite(center_y):
                self._drag_started_panned = self.is_panned()
                self._drag_last = event.position()
                self._drag_active = True
                self._drag_moved = False
                self._cancel_cursor_release_ease()
                if self._follow_target_key:
                    self.clear_follow()
                self.view_center_world = (center_x, center_y)
                self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            center = self._view_center()
            center_x = safe_float(center.get("x"), math.nan)
            center_y = safe_float(center.get("y"), math.nan)
            if math.isfinite(center_x) and math.isfinite(center_y):
                self._drag_started_panned = self.is_panned()
                self._drag_last = event.position()
                self._drag_active = False
                self._drag_moved = False
                self._cancel_cursor_release_ease()
                if self._z4_drag_mode and self.fog.layer_enabled(self._fow_edit_layer):
                    world = self.world_at_screen(event.position())
                    if world is not None:
                        self._z4_dragging = True
                        self._z4_drag_last_world = (
                            float(world["x"]),
                            float(world["y"]),
                        )
                        self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
                        event.accept()
                        return
                if self._fow_line_tool:
                    # Edit existing rings when not drawing a new draft.
                    if not self._fow_line_draft:
                        hit = self._fow_hit_test(event.position())
                        if hit is not None:
                            kind, ring_i, index = hit
                            mods = event.modifiers()
                            multi = bool(
                                mods
                                & (
                                    QtCore.Qt.KeyboardModifier.ShiftModifier
                                    | QtCore.Qt.KeyboardModifier.ControlModifier
                                )
                            )
                            if kind == "vertex":
                                key = (ring_i, index)
                                if multi:
                                    if key in self._fow_selected:
                                        self._fow_selected.discard(key)
                                    else:
                                        self._fow_selected.add(key)
                                    self.fowLineDraftChanged.emit()
                                    self.update()
                                else:
                                    if key not in self._fow_selected:
                                        self._fow_selected = {key}
                                    self._fow_begin_vertex_edit(ring_i, index)
                                event.accept()
                                return
                            # Edge insert (no multi-toggle).
                            self._fow_insert_vertex_on_edge(
                                ring_i, index, event.position()
                            )
                            event.accept()
                            return
                    # Empty map: click places a draft vertex; drag = marquee.
                    self._drag_active = True
                    self._fow_marquee_origin = QtCore.QPointF(event.position())
                    self._fow_marquee_current = QtCore.QPointF(event.position())
                    self._fow_marquee_active = False
                    self._fow_marquee_add = bool(
                        event.modifiers()
                        & (
                            QtCore.Qt.KeyboardModifier.ShiftModifier
                            | QtCore.Qt.KeyboardModifier.ControlModifier
                        )
                    )
                    event.accept()
                    return
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._event_is_over_child_ui(event.globalPosition().toPoint()):
            event.accept()
            return
        if self._fow_edit_dragging:
            if abs(
                (event.position() - (self._drag_last or event.position())).manhattanLength()
            ) > 0.5 or self._drag_moved:
                self._drag_moved = True
            self._drag_last = event.position()
            self._fow_move_edit_vertex(event.position())
            event.accept()
            return
        if self._z4_dragging and self._z4_drag_last_world is not None:
            world = self.world_at_screen(event.position())
            if world is not None:
                dx = float(world["x"]) - self._z4_drag_last_world[0]
                dy = float(world["y"]) - self._z4_drag_last_world[1]
                if abs(dx) + abs(dy) > 1e-6:
                    self.fog.nudge_layer(
                        self._fow_edit_layer, dx, dy, persist=False
                    )
                    self._z4_drag_last_world = (
                        float(world["x"]),
                        float(world["y"]),
                    )
                    self.update()
            self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            event.accept()
            return
        if (
            self._drag_active
            and self._drag_last is not None
        ):
            delta = event.position() - self._drag_last
            self._drag_last = event.position()
            if abs(delta.x()) + abs(delta.y()) > 0.5:
                self._drag_moved = True
            if self._fow_line_tool and self._fow_marquee_origin is not None:
                self._fow_marquee_current = QtCore.QPointF(event.position())
                if not self._fow_marquee_active:
                    dist = math.hypot(
                        self._fow_marquee_current.x() - self._fow_marquee_origin.x(),
                        self._fow_marquee_current.y() - self._fow_marquee_origin.y(),
                    )
                    if dist >= self._fow_marquee_threshold_px:
                        self._fow_marquee_active = True
                        self._drag_moved = True
                if self._fow_marquee_active:
                    self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
                    self.update()
                event.accept()
                return
            pixels_per_metre = self._pixels_per_metre()
            if self._drag_moved and pixels_per_metre > 1e-9:
                if self.view_center_world is None:
                    center = self._view_center()
                    center_x = safe_float(center.get("x"), math.nan)
                    center_y = safe_float(center.get("y"), math.nan)
                    if not (math.isfinite(center_x) and math.isfinite(center_y)):
                        event.accept()
                        return
                    if self._follow_target_key:
                        self.clear_follow()
                    self.view_center_world = (center_x, center_y)
                if not self._fow_line_tool:
                    self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                center_x, center_y = self.view_center_world
                next_center = (
                    center_x - delta.x() / pixels_per_metre,
                    center_y - delta.y() / pixels_per_metre,
                )
                if self.map_texture is not None and not self._local_instance_mode():
                    next_center = self.map_texture.clamp_world_center(*next_center)
                self.view_center_world = next_center
                self.panStateChanged.emit(True)
                self.update()
            event.accept()
            return
        if self._fow_line_tool:
            world = self.world_at_screen(event.position())
            self._fow_line_cursor = (
                (float(world["x"]), float(world["y"])) if world is not None else None
            )
            self._fow_hover_ring = None
            self._fow_hover_vertex = None
            self._fow_hover_edge = None
            if not self._fow_line_draft:
                hit = self._fow_hit_test(event.position())
                if hit is not None:
                    kind, ring_i, index = hit
                    self._fow_hover_ring = ring_i
                    if kind == "vertex":
                        self._fow_hover_vertex = index
                        self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
                    else:
                        self._fow_hover_edge = index
                        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
                else:
                    self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            self.update()
            event.accept()
            return
        self._cancel_cursor_release_ease()
        waypoint = self.custom_waypoint_at(event.position())
        waypoint_id = safe_int(waypoint.get("id"), -1) if waypoint else None
        enemy = None if waypoint is not None else self.enemy_at(event.position())
        enemy_id = str(enemy.get("id") or "") if enemy is not None else None
        interactible = (
            None
            if waypoint is not None or enemy is not None
            else self.interactible_at(event.position())
        )
        interactible_id = (
            str(interactible.get("id") or "") if interactible is not None else None
        )
        hover_changed = (
            waypoint_id != self._hovered_custom_waypoint_id
            or enemy_id != self._hovered_enemy_id
            or interactible_id != self._hovered_interactible_id
        )
        if hover_changed:
            self._hovered_custom_waypoint_id = waypoint_id
            self._hovered_enemy_id = enemy_id
            self._hovered_interactible_id = interactible_id
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
            elif interactible is not None:
                player = self._player()
                distance = math.hypot(
                    safe_float(interactible.get("x")) - safe_float(player.get("x")),
                    safe_float(interactible.get("y")) - safe_float(player.get("y")),
                )
                kind = str(interactible.get("kind") or "").strip().title() or "Node"
                tooltip = (
                    f"{self._interactible_display_name(interactible)}\n"
                    f"{kind} · {distance:.1f} m"
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
        self._hovered_interactible_id = None
        self._fow_line_cursor = None
        self._fow_hover_ring = None
        self._fow_hover_vertex = None
        self._fow_hover_edge = None
        self._fow_clear_marquee()
        QtWidgets.QToolTip.hideText()
        if not self._drag_active and not self._fow_edit_dragging and not self._z4_dragging:
            if self._z4_drag_mode:
                self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            elif self._fow_line_tool:
                self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._event_is_over_child_ui(event.globalPosition().toPoint()):
            # A drag may begin on the map and end over an overlay. End the map
            # gesture cleanly without letting the release activate map UI.
            if event.button() == QtCore.Qt.MouseButton.MiddleButton and self._drag_active:
                self._drag_active = False
                self._drag_last = None
                self._drag_moved = False
                self._drag_started_panned = False
                if self._z4_drag_mode:
                    self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
                elif self._fow_line_tool:
                    self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
                else:
                    self._ease_cursor_from_drag(event.position())
                self.panStateChanged.emit(self.is_panned())
            elif event.button() == QtCore.Qt.MouseButton.LeftButton and (
                self._drag_active or self._fow_edit_dragging or self._z4_dragging
            ):
                if self._fow_edit_dragging:
                    self._fow_finish_vertex_edit()
                if self._z4_dragging:
                    self.fog.set_layer_transform(
                        self._fow_edit_layer,
                        self.fog.layer_transform(self._fow_edit_layer),
                        persist=True,
                    )
                    self._z4_dragging = False
                    self._z4_drag_last_world = None
                if self._fow_marquee_active:
                    self._fow_select_marquee()
                self._fow_clear_marquee()
                self._drag_active = False
                self._drag_last = None
                self._drag_moved = False
                self._drag_started_panned = False
                if self._z4_drag_mode:
                    self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
                elif self._fow_line_tool:
                    self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
                else:
                    self._ease_cursor_from_drag(event.position())
                self.panStateChanged.emit(self.is_panned())
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.MiddleButton and self._drag_active:
            self._drag_active = False
            self._drag_last = None
            self._drag_moved = False
            self._drag_started_panned = False
            if self._z4_drag_mode:
                self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            elif self._fow_line_tool:
                self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            else:
                self._ease_cursor_from_drag(event.position())
            self.panStateChanged.emit(self.is_panned())
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton and (
            self._drag_active or self._fow_edit_dragging or self._z4_dragging
        ):
            placed_vertex = False
            if self._z4_dragging:
                self.fog.set_layer_transform(
                    self._fow_edit_layer,
                    self.fog.layer_transform(self._fow_edit_layer),
                    persist=True,
                )
                self._z4_dragging = False
                self._z4_drag_last_world = None
            elif self._fow_edit_dragging:
                self._fow_finish_vertex_edit()
            elif self._fow_line_tool and self._fow_marquee_active:
                self._fow_select_marquee()
                self._fow_clear_marquee()
            elif self._fow_line_tool and not self._drag_moved:
                placed_vertex = self._fow_line_add_vertex_at(event.position())
                self._fow_clear_marquee()
            else:
                self._fow_clear_marquee()
            self._drag_active = False
            self._drag_last = None
            self._drag_moved = False
            self._drag_started_panned = False
            if self._z4_drag_mode:
                self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            elif self._fow_line_tool:
                self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            else:
                self._ease_cursor_from_drag(event.position())
            self.panStateChanged.emit(self.is_panned())
            if placed_vertex:
                event.accept()
                return
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._event_is_over_child_ui(event.globalPosition().toPoint()):
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._fow_line_tool:
                # Drop the extra click from the double-click pair, then close.
                if self._fow_line_draft:
                    self._fow_line_draft.pop()
                self.fow_line_close()
                event.accept()
                return
            self.recenter()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        if self._fow_line_tool:
            key = event.key()
            if key == QtCore.Qt.Key.Key_Escape:
                if self._fow_selected:
                    self._fow_selected.clear()
                    self.fowLineDraftChanged.emit()
                    self.update()
                elif self._fow_line_draft:
                    self._fow_line_draft.clear()
                    self._fow_line_cursor = None
                    self.fowLineDraftChanged.emit()
                    self.update()
                else:
                    self.set_fow_line_tool(False)
                event.accept()
                return
            if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                self.fow_line_close()
                event.accept()
                return
            if key in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
                if self._fow_selected and not self._fow_line_draft:
                    self._fow_delete_vertices(set(self._fow_selected))
                    event.accept()
                    return
                if key == QtCore.Qt.Key.Key_Backspace:
                    self.fow_line_undo()
                    event.accept()
                    return
            if key == QtCore.Qt.Key.Key_Z and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                self.fow_line_undo()
                event.accept()
                return
        super().keyPressEvent(event)

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

    def _player_arrow_icon(self) -> QtGui.QImage | None:
        asset_name = self.PLAYER_ARROW_ASSET
        if (
            self._player_arrow_icon_cache is not None
            and self._player_arrow_icon_asset == asset_name
        ):
            return self._player_arrow_icon_cache
        if (
            self._player_arrow_icon_missing
            and self._player_arrow_icon_asset == asset_name
        ):
            return None
        self._player_arrow_icon_cache = None
        self._player_arrow_icon_missing = False
        self._player_arrow_icon_asset = asset_name
        path = discover_project_asset(asset_name)
        if path is None:
            self._player_arrow_icon_missing = True
            return None
        reader = QtGui.QImageReader(str(path))
        reader.setAutoTransform(True)
        source = reader.read()
        if source.isNull():
            self._player_arrow_icon_missing = True
            return None
        icon = source.scaled(
            self.PLAYER_ARROW_SIZE,
            self.PLAYER_ARROW_SIZE,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        if icon.isNull():
            self._player_arrow_icon_missing = True
            return None
        self._player_arrow_icon_cache = icon
        return icon

    def icon_available_for_kind(self, kind: str) -> bool:
        normalized_kind = kind.strip().lower()
        if self._loose_kind_icon(normalized_kind) is not None:
            return True
        icon_index = self._poi_icon_index(normalized_kind, "")
        return icon_index is not None and self._waypoint_icon(icon_index) is not None

    def _marker_sprite(
        self, kind: str, subkind: str, size: str
    ) -> tuple[QtGui.QPixmap, float, float]:
        """Pre-rendered marker pixmap plus its centre offset in logical pixels."""
        dpr = float(self.devicePixelRatioF() or 1.0)
        key = (kind, subkind, size, round(dpr, 3))
        cached = self._marker_sprite_cache.get(key)
        if cached is not None:
            return cached
        entry = self._build_marker_sprite(kind, subkind, size, dpr)
        self._marker_sprite_cache[key] = entry
        return entry

    def _build_marker_sprite(
        self, kind: str, subkind: str, size: str, dpr: float
    ) -> tuple[QtGui.QPixmap, float, float]:
        normalized_kind = kind.strip().lower()
        size_key = size.strip().lower()
        if size_key == "small":
            scale = 0.72
            dot_radius = 2.5
        elif size_key == "large":
            scale = 1.28
            dot_radius = 5.0
        else:
            scale = 1.0
            dot_radius = 3.5

        icon: QtGui.QImage | None = None
        if self.loot_kind_icon_mode.get(normalized_kind, True):
            icon = self._loose_kind_icon(normalized_kind)
            if icon is None:
                icon_index = self._poi_icon_index(normalized_kind, subkind)
                icon = self._waypoint_icon(icon_index) if icon_index is not None else None

        # One pixel of slack keeps antialiased edges and ring strokes inside.
        margin = 1.0
        if icon is not None:
            width = icon.width() * scale
            height = icon.height() * scale
            half_w = width / 2.0
            half_h = height / 2.0
            if size_key == "large":
                ring_radius = max(width, height) * 0.55 + 0.7
                half_w = max(half_w, ring_radius)
                half_h = max(half_h, ring_radius)
        else:
            half_w = half_h = dot_radius + 0.5
            if size_key == "large":
                half_w = half_h = dot_radius + 2.2 + 0.65
        # Round the centre offset to whole device pixels so the snapped blit
        # below lands the marker centre exactly where the painter asked for it.
        half_w = math.ceil((half_w + margin) * dpr) / dpr
        half_h = math.ceil((half_h + margin) * dpr) / dpr

        pixmap = QtGui.QPixmap(
            max(1, round(half_w * 2.0 * dpr)),
            max(1, round(half_h * 2.0 * dpr)),
        )
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        centre = QtCore.QPointF(half_w, half_h)
        sprite_painter = QtGui.QPainter(pixmap)
        sprite_painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        sprite_painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        if icon is not None:
            sprite_painter.drawImage(
                QtCore.QRectF(
                    centre.x() - width / 2.0,
                    centre.y() - height / 2.0,
                    width,
                    height,
                ),
                icon,
            )
            if size_key == "large":
                # Soft ring so large nodes read clearly next to small ones.
                ring = QtGui.QColor(self._poi_color(normalized_kind))
                ring.setAlpha(160)
                sprite_painter.setPen(QtGui.QPen(ring, 1.4))
                sprite_painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                sprite_painter.drawEllipse(
                    centre, max(width, height) * 0.55, max(width, height) * 0.55
                )
        else:
            sprite_painter.setPen(QtGui.QPen(QtGui.QColor("#101318"), 1.0))
            sprite_painter.setBrush(self._poi_color(kind))
            sprite_painter.drawEllipse(centre, dot_radius, dot_radius)
            if size_key == "large":
                ring = QtGui.QColor(self._poi_color(normalized_kind))
                ring.setAlpha(170)
                sprite_painter.setPen(QtGui.QPen(ring, 1.3))
                sprite_painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                sprite_painter.drawEllipse(
                    centre, dot_radius + 2.2, dot_radius + 2.2
                )
        sprite_painter.end()
        return (pixmap, half_w, half_h)

    def _draw_poi_marker(
        self,
        painter: QtGui.QPainter,
        point: QtCore.QPointF,
        kind: str,
        subkind: str,
        *,
        size: str = "",
    ) -> None:
        pixmap, half_w, half_h = self._marker_sprite(kind, subkind, size)
        self._blit_marker_sprite(painter, point, pixmap, half_w, half_h)

    @staticmethod
    def _blit_marker_sprite(
        painter: QtGui.QPainter,
        point: QtCore.QPointF,
        pixmap: QtGui.QPixmap,
        half_w: float,
        half_h: float,
    ) -> None:
        # drawPixmap lands on whole device pixels, and the sprite's centre offset
        # is a whole number of them, so the marker centre snaps to round(point).
        painter.drawPixmap(
            QtCore.QPointF(point.x() - half_w, point.y() - half_h), pixmap
        )

    @staticmethod
    def _poi_color(kind: str) -> QtGui.QColor:
        return _POI_COLORS.get(kind, _POI_COLOR_FALLBACK)

    def _draw_z_indicator(
        self,
        painter: QtGui.QPainter,
        point: QtCore.QPointF,
        item_z: float,
        player_z: float,
        *,
        gap: float = 5.5,
        color: QtGui.QColor | None = None,
    ) -> None:
        """Tiny chevron above/below a marker when it sits on another floor."""
        if not (math.isfinite(item_z) and math.isfinite(player_z)):
            return
        delta = item_z - player_z
        if abs(delta) < self.z_indicator_threshold:
            return
        above = delta > 0.0
        fill = color if color is not None else QtGui.QColor("#e8eef5")
        outline = QtGui.QColor("#0b1117")
        size = 3.6
        # Screen Y grows downward: "above player" → chevron pointing up (toward top).
        if above:
            tip = point + QtCore.QPointF(0.0, -(gap + size))
            left = point + QtCore.QPointF(-size, -gap)
            right = point + QtCore.QPointF(size, -gap)
        else:
            tip = point + QtCore.QPointF(0.0, gap + size)
            left = point + QtCore.QPointF(-size, gap)
            right = point + QtCore.QPointF(size, gap)
        painter.setPen(QtGui.QPen(outline, 1.0))
        painter.setBrush(fill)
        painter.drawPolygon(QtGui.QPolygonF([tip, left, right]))

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
        elif icon == "crosshair":
            # Exact world-point marker for fog / map alignment.
            arm = 9.0
            gap = 2.0
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            for width, pen_color in ((3.0, outline), (1.25, color)):
                painter.setPen(
                    QtGui.QPen(
                        pen_color,
                        width,
                        QtCore.Qt.PenStyle.SolidLine,
                        QtCore.Qt.PenCapStyle.FlatCap,
                    )
                )
                painter.drawLine(
                    point + QtCore.QPointF(-arm, 0), point + QtCore.QPointF(-gap, 0)
                )
                painter.drawLine(
                    point + QtCore.QPointF(gap, 0), point + QtCore.QPointF(arm, 0)
                )
                painter.drawLine(
                    point + QtCore.QPointF(0, -arm), point + QtCore.QPointF(0, -gap)
                )
                painter.drawLine(
                    point + QtCore.QPointF(0, gap), point + QtCore.QPointF(0, arm)
                )
            painter.setPen(QtGui.QPen(outline, 1.0))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawEllipse(point, 4.0, 4.0)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRect(
                QtCore.QRectF(point.x() - 0.75, point.y() - 0.75, 1.5, 1.5)
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
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(outline)
            painter.drawRect(QtCore.QRectF(point.x() - 1.0, point.y() - 1.0, 2.0, 2.0))
        else:  # pin — tip sits on the exact world coordinate
            tip = point
            head = tip + QtCore.QPointF(0, -10)
            painter.drawEllipse(head, 6.0, 6.0)
            painter.drawPolygon(
                QtGui.QPolygonF(
                    [
                        tip + QtCore.QPointF(-4.5, -7),
                        tip + QtCore.QPointF(4.5, -7),
                        tip,
                    ]
                )
            )
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(outline)
            painter.drawEllipse(head, 2.0, 2.0)
            painter.setBrush(color.lighter(140))
            painter.drawRect(QtCore.QRectF(tip.x() - 0.75, tip.y() - 0.75, 1.5, 1.5))

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

    def _draw_player_marker(
        self,
        painter: QtGui.QPainter,
        player: dict[str, Any],
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, float],
    ) -> None:
        player_x = safe_float(player.get("x"), math.nan)
        player_y = safe_float(player.get("y"), math.nan)
        if not (math.isfinite(player_x) and math.isfinite(player_y)):
            return
        player_point = self._world_to_screen(
            player, center, pixels_per_metre, view_center
        )
        # Farever headings are rotated 90° clockwise relative to the Atlas
        # triangle forward axis — correct without changing map orientation.
        body_heading = safe_float(player.get("heading")) + (math.pi / 2.0)
        body_fx, body_fy = math.sin(body_heading), -math.cos(body_heading)
        body_sx, body_sy = -body_fy, body_fx

        camera_raw = safe_float(player.get("camera_heading"), math.nan)
        if math.isfinite(camera_raw):
            cam_heading = camera_raw + (math.pi / 2.0)
            cam_fx, cam_fy = math.sin(cam_heading), -math.cos(cam_heading)
            cam_sx, cam_sy = -cam_fy, cam_fx
            # Distinct cyan wedge for camera look (under the body arrow).
            cam_tip = player_point + QtCore.QPointF(cam_fx * 26.0, cam_fy * 26.0)
            cam_left = player_point + QtCore.QPointF(
                cam_fx * 5.0 + cam_sx * 11.0, cam_fy * 5.0 + cam_sy * 11.0
            )
            cam_right = player_point + QtCore.QPointF(
                cam_fx * 5.0 - cam_sx * 11.0, cam_fy * 5.0 - cam_sy * 11.0
            )
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(64, 210, 255, 110))
            painter.drawPolygon(QtGui.QPolygonF([player_point, cam_left, cam_tip, cam_right]))
            painter.setPen(QtGui.QPen(QtGui.QColor(120, 230, 255, 230), 2.0))
            painter.drawLine(player_point, cam_tip)

        arrow = self._player_arrow_icon()
        if arrow is not None:
            # Asset points +X; atan2(fy, fx) matches screen Y-down clockwise rotation.
            painter.save()
            painter.translate(player_point)
            painter.rotate(math.degrees(math.atan2(body_fy, body_fx)))
            painter.drawImage(
                QtCore.QRectF(
                    -arrow.width() / 2.0,
                    -arrow.height() / 2.0,
                    float(arrow.width()),
                    float(arrow.height()),
                ),
                arrow,
            )
            painter.restore()
            return

        tip = player_point + QtCore.QPointF(body_fx * 14.0, body_fy * 14.0)
        base = player_point - QtCore.QPointF(body_fx * 7.0, body_fy * 7.0)
        left = base + QtCore.QPointF(body_sx * 7.0, body_sy * 7.0)
        right = base - QtCore.QPointF(body_sx * 7.0, body_sy * 7.0)
        painter.setPen(QtGui.QPen(QtGui.QColor("#081016"), 1.5))
        painter.setBrush(QtGui.QColor("#f4f7fa"))
        painter.drawPolygon(QtGui.QPolygonF([tip, left, right]))

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
        self._interactible_hits = []
        self._player_hits = []

        map_drawn = False
        local_instance = self._local_instance_mode()
        draw_texture = (
            self.show_texture and self.map_texture is not None and not local_instance
        )
        if draw_texture:
            painter.save()
            if self.heading_up:
                painter.translate(center)
                painter.rotate(-map_heading_degrees(player.get("heading")))
                painter.translate(-center)
            painter.setOpacity(0.92)
            map_drawn = bool(
                self.map_texture.draw_view(
                    painter,
                    target_rect=viewport,
                    view_center=view_center,
                    pixels_per_metre=pixels_per_metre,
                )
            )
            if not map_drawn and not self.map_texture.image.isNull():
                # Never present a featureless black square when telemetry and the
                # calibration disagree. A dim full-zone texture makes the failure
                # explicit while the projection self-check waits for POIs.
                painter.setOpacity(0.38)
                painter.drawImage(viewport, self.map_texture.image)
            painter.restore()
            painter.fillPath(clip_shape, QtGui.QColor(0, 0, 0, 24))
            if map_drawn:
                self.fog.paint(
                    painter,
                    viewport=viewport,
                    center=center,
                    pixels_per_metre=pixels_per_metre,
                    view_center=view_center,
                    world_to_screen=self._world_to_screen,
                    draft_ring=self._fow_line_draft if self._fow_line_tool else None,
                    draft_cursor=self._fow_line_cursor if self._fow_line_tool else None,
                    show_custom_handles=bool(
                        self._fow_line_tool and not self._fow_line_draft
                    ),
                    handle_layer=self._fow_edit_layer,
                    selected_vertices=self._fow_selected if self._fow_line_tool else None,
                    hover_ring=self._fow_hover_ring,
                    hover_vertex=self._fow_hover_vertex,
                    hover_edge=self._fow_hover_edge,
                    active_ring=self._fow_edit_ring if self._fow_edit_dragging else None,
                    active_vertex=(
                        self._fow_edit_vertex if self._fow_edit_dragging else None
                    ),
                    map_texture=self.map_texture,
                )
                if self._fow_line_tool:
                    self._fow_paint_marquee(painter)
        elif local_instance:
            painter.fillPath(clip_shape, QtGui.QColor("#0a0f08"))
            instance = self._instance_state()
            label = str(instance.get("type") or "instance").strip() or "instance"
            map_id = str(instance.get("map_id") or "").strip()
            banner = label
            if map_id:
                banner = f"{banner} · {map_id}"
            painter.setPen(QtGui.QColor("#9ba7b4"))
            painter.drawText(
                viewport.adjusted(14, 12, -14, -14),
                QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
                banner,
            )

        # Player under all other markers so nearby dots stay readable.
        self._draw_player_marker(painter, player, center, pixels_per_metre, view_center)
        player_x = safe_float(player.get("x"), math.nan)
        player_y = safe_float(player.get("y"), math.nan)
        player_z = safe_float(player.get("z"), math.nan)
        view_half_w, view_half_h = self._view_half_extents(viewport, 12.0)
        view_half_w_wp, view_half_h_wp = self._view_half_extents(viewport, 24.0)
        view_half_w_party, view_half_h_party = self._view_half_extents(viewport, 28.0)
        view_half_w_names, view_half_h_names = self._view_half_extents(viewport, 28.0)
        view_half_w_players, view_half_h_players = self._view_half_extents(viewport, 14.0)

        enabled_poi_kinds = {
            kind for kind, enabled in self.poi_kind_visibility.items() if enabled
        }
        enabled_loot_kinds = {
            kind for kind, enabled in self.loot_kind_visibility.items() if enabled
        }
        completed_elements = self.state.get("completed_elements", [])
        completed_element_ids = {
            str(value) for value in completed_elements
        } if isinstance(completed_elements, list) else set()

        def _loot_kind_visible(kind: str) -> bool:
            if kind == "gatherable":
                return bool(enabled_loot_kinds & {"plant", "ore"})
            return kind in enabled_loot_kinds

        def _in_loot_live_range(px: float, py: float, pz: float) -> bool:
            if not (
                math.isfinite(player_x)
                and math.isfinite(player_y)
            ):
                return False
            if not (math.isfinite(px) and math.isfinite(py)):
                return False
            if math.hypot(px - player_x, py - player_y) > self.LOOT_LIVE_RANGE_M:
                return False
            if math.isfinite(pz) and math.isfinite(player_z):
                if abs(pz - player_z) > self.LOOT_LIVE_Z_CULL_M:
                    return False
            return True

        # Live gatherables/chests — world and local instance modes.
        live_nodes = (
            self.state.get("interactibles", []) if isinstance(self.state, dict) else []
        )
        if not isinstance(live_nodes, list):
            live_nodes = []
        if enabled_loot_kinds:
            for poi in live_nodes:
                if not isinstance(poi, dict):
                    continue
                kind = str(poi.get("kind", "")).strip().lower()
                if kind not in _COLLECTIBLE_KINDS or not _loot_kind_visible(kind):
                    continue
                if not self._world_in_view(
                    poi,
                    view_center,
                    viewport,
                    half_width_m=view_half_w,
                    half_height_m=view_half_h,
                ):
                    continue
                if self._fog_hides_point(
                    safe_float(poi.get("x"), math.nan),
                    safe_float(poi.get("y"), math.nan),
                ):
                    continue
                point = self._world_to_screen(poi, center, pixels_per_metre, view_center)
                draw_kind = "ore" if kind == "gatherable" else kind
                size = self._node_size_label(poi)
                self._draw_poi_marker(painter, point, draw_kind, "", size=size)
                self._draw_z_indicator(
                    painter,
                    point,
                    safe_float(poi.get("z"), math.nan),
                    player_z,
                    gap=6.0 if size == "large" else 5.0,
                )
                hit = self._interactible_hit_radius
                if size == "large":
                    hit += 3.0
                elif size == "small":
                    hit -= 1.0
                marker = dict(poi)
                marker["size"] = size
                self._interactible_hits.append(
                    (
                        QtCore.QRectF(
                            point.x() - hit, point.y() - hit, hit * 2.0, hit * 2.0
                        ),
                        marker,
                    )
                )

        # Static file markers. Landmarks always. Inside the live interactible
        # bubble, collectibles come only from the live feed — so collected /
        # missing nodes disappear until they respawn (empty feed keeps file
        # markers so a failed sweep does not blank the map).
        if (enabled_poi_kinds or enabled_loot_kinds) and not local_instance:
            live_feed_active = bool(live_nodes)
            # Kind filtering and field parsing are cached; everything below is
            # position- or telemetry-dependent and has to run every frame.
            self._ensure_prepared_pois()
            prepared = self._prepared_pois
            cull_x = safe_float(view_center.get("x"))
            cull_y = safe_float(view_center.get("y"))
            origin_x = center.x()
            origin_y = center.y()
            hit_base = self._interactible_hit_radius
            for index in self._prepared_poi_candidates(
                cull_x, cull_y, view_half_w, view_half_h
            ):
                (
                    world_x,
                    world_y,
                    world_z,
                    kind,
                    size,
                    is_collectible,
                    has_position,
                    poi_id,
                    sprite,
                    poi,
                ) = prepared[index]
                if (
                    abs(world_x - cull_x) > view_half_w
                    or abs(world_y - cull_y) > view_half_h
                ):
                    continue
                # Red orbs have no live bridge feed — always use the file.
                if (
                    is_collectible
                    and kind != "red_orb"
                    and live_feed_active
                    and has_position
                    and _in_loot_live_range(world_x, world_y, world_z)
                ):
                    continue
                if has_position and self._fog_hides_point(world_x, world_y):
                    continue
                point = QtCore.QPointF(
                    origin_x + (world_x - cull_x) * pixels_per_metre,
                    origin_y + (world_y - cull_y) * pixels_per_metre,
                )
                pixmap, sprite_half_w, sprite_half_h = sprite
                if kind == "red_orb" and poi_id in completed_element_ids:
                    painter.save()
                    painter.setOpacity(0.32)
                    self._blit_marker_sprite(
                        painter, point, pixmap, sprite_half_w, sprite_half_h
                    )
                    painter.restore()
                else:
                    self._blit_marker_sprite(
                        painter, point, pixmap, sprite_half_w, sprite_half_h
                    )
                    self._draw_z_indicator(
                        painter,
                        point,
                        world_z,
                        player_z,
                        gap=6.0 if size == "large" else 5.0,
                    )
                if is_collectible and kind != "red_orb":
                    hit = hit_base
                    if size == "large":
                        hit += 3.0
                    elif size == "small":
                        hit -= 1.0
                    marker = dict(poi)
                    marker["size"] = size
                    if not marker.get("id"):
                        marker["id"] = f"static:{kind}:{world_x:.1f}:{world_y:.1f}"
                    self._interactible_hits.append(
                        (
                            QtCore.QRectF(
                                point.x() - hit, point.y() - hit, hit * 2.0, hit * 2.0
                            ),
                            marker,
                        )
                    )

        player_x = safe_float(player.get("x"), math.nan)
        player_y = safe_float(player.get("y"), math.nan)
        gather_target = (
            self.active_gather_target
            if isinstance(self.active_gather_target, dict)
            else None
        )
        if (
            gather_target is not None
            and self.show_route_line
            and math.isfinite(player_x)
            and math.isfinite(player_y)
        ):
            gather_x = safe_float(gather_target.get("x"), math.nan)
            gather_y = safe_float(gather_target.get("y"), math.nan)
            if math.isfinite(gather_x) and math.isfinite(gather_y):
                player_point_for_route = self._world_to_screen(
                    player, center, pixels_per_metre, view_center
                )
                destination_point = self._world_to_screen(
                    gather_target, center, pixels_per_metre, view_center
                )
                route_color = QtGui.QColor(
                    self._poi_color(str(gather_target.get("kind") or "plant"))
                )
                route_color.setAlpha(160)
                painter.setPen(
                    QtGui.QPen(route_color, 1.8, QtCore.Qt.PenStyle.DashLine)
                )
                painter.drawLine(player_point_for_route, destination_point)
                self._draw_poi_marker(
                    painter,
                    destination_point,
                    str(gather_target.get("kind") or "plant"),
                    "",
                    size=str(gather_target.get("size") or ""),
                )

        active_waypoint: dict[str, Any] | None = None
        if self.show_custom_waypoints:
            for waypoint in self.custom_waypoints:
                if not isinstance(waypoint, dict):
                    continue
                if safe_int(waypoint.get("id"), -1) == self.active_custom_waypoint_id:
                    active_waypoint = waypoint
                    break

            if (
                gather_target is None
                and active_waypoint is not None
                and self.show_route_line
                and math.isfinite(player_x)
                and math.isfinite(player_y)
            ):
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
                if not self._world_in_view(
                    waypoint,
                    view_center,
                    viewport,
                    half_width_m=view_half_w_wp,
                    half_height_m=view_half_h_wp,
                ):
                    continue
                if self._fog_hides_point(
                    safe_float(waypoint.get("x"), math.nan),
                    safe_float(waypoint.get("y"), math.nan),
                ):
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
        if self.show_enemies and isinstance(enemies, list):
            for enemy in enemies:
                if not isinstance(enemy, dict):
                    continue
                enemy_x = safe_float(enemy.get("x"), math.nan)
                enemy_y = safe_float(enemy.get("y"), math.nan)
                if not (math.isfinite(enemy_x) and math.isfinite(enemy_y)):
                    continue
                if not self._world_in_view(
                    enemy,
                    view_center,
                    viewport,
                    half_width_m=view_half_w,
                    half_height_m=view_half_h,
                ):
                    continue
                if self._fog_hides_point(enemy_x, enemy_y):
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
                self._draw_z_indicator(
                    painter, point, enemy_z, player_z, gap=4.8, color=fill
                )
                hit = self._enemy_hit_radius
                self._enemy_hits.append(
                    (
                        QtCore.QRectF(
                            point.x() - hit, point.y() - hit, hit * 2.0, hit * 2.0
                        ),
                        dict(enemy),
                    )
                )

        nearby_players = (
            self.state.get("players", []) if isinstance(self.state, dict) else []
        )
        if self.show_players and isinstance(nearby_players, list):
            for other in nearby_players:
                if not isinstance(other, dict):
                    continue
                other_x = safe_float(other.get("x"), math.nan)
                other_y = safe_float(other.get("y"), math.nan)
                if not (math.isfinite(other_x) and math.isfinite(other_y)):
                    continue
                if self.show_player_names:
                    half_w, half_h = view_half_w_names, view_half_h_names
                else:
                    half_w, half_h = view_half_w_players, view_half_h_players
                if not self._world_in_view(
                    other,
                    view_center,
                    viewport,
                    half_width_m=half_w,
                    half_height_m=half_h,
                ):
                    continue
                if self._fog_hides_point(other_x, other_y):
                    continue
                point = self._world_to_screen(
                    other, center, pixels_per_metre, view_center
                )
                other_z = safe_float(other.get("z"), player_z)
                far = (
                    math.isfinite(other_z)
                    and math.isfinite(player_z)
                    and abs(other_z - player_z) > self.player_z_fade
                )
                # Amber diamond: distinct from red enemy dots and class-colored
                # party arrows.
                fill = QtGui.QColor("#E8B84A")
                if far:
                    fill.setAlpha(120)
                size = 4.2
                diamond = QtGui.QPolygonF(
                    [
                        point + QtCore.QPointF(0, -size),
                        point + QtCore.QPointF(size, 0),
                        point + QtCore.QPointF(0, size),
                        point + QtCore.QPointF(-size, 0),
                    ]
                )
                painter.setPen(QtGui.QPen(QtGui.QColor("#1a1408"), 1.0))
                painter.setBrush(fill)
                painter.drawPolygon(diamond)
                self._draw_z_indicator(
                    painter, point, other_z, player_z, gap=5.5, color=fill
                )
                name = str(other.get("name") or "").strip()
                label_rect: QtCore.QRect | None = None
                if self.show_player_names and name:
                    metrics = painter.fontMetrics()
                    label_rect = metrics.boundingRect(name).adjusted(-4, -2, 4, 2)
                    label_rect.moveLeft(round(point.x() + 10))
                    label_rect.moveBottom(round(point.y() - 3))
                    painter.setPen(QtGui.QPen(QtGui.QColor("#26333f"), 1.0))
                    painter.setBrush(QtGui.QColor(12, 18, 24, 218))
                    painter.drawRoundedRect(QtCore.QRectF(label_rect), 3.0, 3.0)
                    painter.setPen(QtGui.QColor("#f2f7fc"))
                    painter.drawText(
                        label_rect, QtCore.Qt.AlignmentFlag.AlignCenter, name
                    )
                self._register_player_hit(
                    point,
                    {
                        "name": name or "Unknown",
                        "uid": str(other.get("uid") or "").strip(),
                        "class": str(other.get("class") or "").strip(),
                        "level": safe_int(other.get("level"), 0),
                        "x": other.get("x"),
                        "y": other.get("y"),
                        "z": other.get("z"),
                        "in_party": False,
                        "is_self": False,
                    },
                    label_rect=label_rect,
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
            if not self._world_in_view(
                member,
                view_center,
                viewport,
                half_width_m=view_half_w_party,
                half_height_m=view_half_h_party,
            ):
                continue
            if self._fog_hides_point(member_x, member_y):
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
            self._draw_z_indicator(
                painter,
                point,
                safe_float(member.get("z"), math.nan),
                player_z,
                gap=8.0,
                color=QtGui.QColor(class_color),
            )

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
            label_rect = None
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
            self._register_player_hit(
                point,
                {
                    "name": name or "Unknown",
                    "uid": member_uid,
                    "class": str(member.get("class") or "").strip(),
                    "level": safe_int(member.get("level"), 0),
                    "x": member.get("x"),
                    "y": member.get("y"),
                    "z": member.get("z"),
                    "in_party": True,
                    "is_self": False,
                },
                label_rect=label_rect,
                hit_radius=14.0,
            )
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
            self._draw_z_indicator(
                painter,
                point,
                safe_float(target_obj.get("z"), math.nan),
                player_z,
                gap=8.5,
                color=QtGui.QColor("#ff6666"),
            )

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
