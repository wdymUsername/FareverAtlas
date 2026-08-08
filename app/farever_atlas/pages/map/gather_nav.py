"""Gather-nav mixin and panel: nearest resource → route line → collect → next."""

from __future__ import annotations

import math
import time
from typing import Any

from PySide6 import QtCore, QtWidgets

from ...config import safe_float
from ...toast import notify


GATHER_KINDS = (
    ("plant", "Plant"),
    ("ore", "Ore"),
    ("chest", "Chest"),
)

GATHER_SIZES = (
    ("", "Any size"),
    ("small", "Small"),
    ("medium", "Medium"),
    ("large", "Large"),
)


def _node_size_label(item: dict[str, Any]) -> str:
    explicit = str(item.get("size") or "").strip().lower()
    if explicit in {"small", "medium", "large"}:
        return explicit
    blob = " ".join(
        str(item.get(key) or "") for key in ("name", "kind", "subkind", "source")
    ).lower()
    if "small" in blob:
        return "small"
    if "medium" in blob:
        return "medium"
    if "large" in blob or "_big" in blob or " big" in blob:
        return "large"
    return ""


def _display_name(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    kind = str(item.get("kind") or "").strip()
    parts = [
        part
        for part in name.replace("_", " ").split()
        if part and part.lower() != "generic"
    ]
    pretty = " ".join(parts) if parts else (kind.title() if kind else "Node")
    size = _node_size_label(item)
    if size and size not in pretty.lower():
        pretty = f"{pretty} ({size.title()})"
    return pretty


def _static_key(poi: dict[str, Any]) -> str:
    return (
        f"static:{str(poi.get('kind') or '').lower()}:"
        f"{safe_float(poi.get('x')):.1f}:"
        f"{safe_float(poi.get('y')):.1f}"
    )


def _live_key(item: dict[str, Any]) -> str:
    item_id = str(item.get("id") or "").strip()
    if item_id:
        return f"live:{item_id}"
    return (
        f"livepos:{str(item.get('kind') or '').lower()}:"
        f"{safe_float(item.get('x')):.1f}:"
        f"{safe_float(item.get('y')):.1f}"
    )


class GatherNavPanel(QtWidgets.QWidget):
    """Controls for gather navigation (sidebar tab or overlay)."""

    enabledChanged = QtCore.Signal(bool)
    filtersChanged = QtCore.Signal()
    skipRequested = QtCore.Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("gatherNavPanel")
        self._compact = bool(compact)

        root = QtWidgets.QVBoxLayout(self)
        if self._compact:
            root.setContentsMargins(0, 2, 0, 2)
            root.setSpacing(5)
        else:
            root.setContentsMargins(0, 8, 0, 0)
            root.setSpacing(10)

        if not self._compact:
            intro = QtWidgets.QLabel(
                "Pick the nearest matching resource, draw a route line, then "
                "advance when the live node disappears after you collect it."
            )
            intro.setObjectName("waypointOverlayBody")
            intro.setWordWrap(True)
            root.addWidget(intro)

        kind_label = QtWidgets.QLabel("RESOURCE")
        kind_label.setObjectName(
            "gatherNavFieldLabel" if self._compact else "waypointColumnHeader"
        )
        root.addWidget(kind_label)
        self.kind_combo = QtWidgets.QComboBox()
        self.kind_combo.setObjectName("gatherNavCombo")
        for kind, label in GATHER_KINDS:
            self.kind_combo.addItem(label, kind)
        root.addWidget(self.kind_combo)

        size_label = QtWidgets.QLabel("SIZE")
        size_label.setObjectName(
            "gatherNavFieldLabel" if self._compact else "waypointColumnHeader"
        )
        root.addWidget(size_label)
        self.size_combo = QtWidgets.QComboBox()
        self.size_combo.setObjectName("gatherNavCombo")
        for size, label in GATHER_SIZES:
            self.size_combo.addItem(label, size)
        large_index = self.size_combo.findData("large")
        if large_index >= 0:
            self.size_combo.setCurrentIndex(large_index)
        root.addWidget(self.size_combo)

        self.status_frame = QtWidgets.QFrame()
        self.status_frame.setObjectName("gatherNavStatus")
        status_layout = QtWidgets.QVBoxLayout(self.status_frame)
        status_layout.setContentsMargins(8 if self._compact else 12, 8, 8 if self._compact else 12, 8)
        status_layout.setSpacing(3)

        self.status_title = QtWidgets.QLabel("Idle")
        self.status_title.setObjectName("gatherNavStatusTitle")
        self.status_title.setWordWrap(True)
        status_layout.addWidget(self.status_title)

        self.status_detail = QtWidgets.QLabel(
            "Start to route to the closest matching node."
            if self._compact
            else "Enable gather nav to route to the closest matching node."
        )
        self.status_detail.setObjectName("gatherNavStatusDetail")
        self.status_detail.setWordWrap(True)
        status_layout.addWidget(self.status_detail)

        root.addWidget(self.status_frame)

        self.enable_button = QtWidgets.QToolButton()
        self.enable_button.setObjectName(
            "gatherNavSidebarButton" if self._compact else "waypointOverlayPrimaryButton"
        )
        self.enable_button.setText("Start")
        self.enable_button.setFixedHeight(26 if self._compact else 30)
        self.enable_button.setCheckable(True)
        self.enable_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        if self._compact:
            self.enable_button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )

        self.skip_button = QtWidgets.QToolButton()
        self.skip_button.setObjectName(
            "gatherNavSidebarButton" if self._compact else "waypointOverlaySecondaryButton"
        )
        self.skip_button.setText("Skip")
        self.skip_button.setFixedHeight(26 if self._compact else 30)
        self.skip_button.setEnabled(False)
        self.skip_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        if self._compact:
            self.skip_button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )

        if self._compact:
            root.addWidget(self.enable_button)
            root.addWidget(self.skip_button)
        else:
            controls = QtWidgets.QHBoxLayout()
            controls.setSpacing(8)
            controls.addWidget(self.enable_button)
            controls.addWidget(self.skip_button)
            controls.addStretch(1)
            root.addLayout(controls)
            root.addStretch(1)

        self.enable_button.toggled.connect(self._on_enabled_toggled)
        self.skip_button.clicked.connect(self.skipRequested.emit)
        self.kind_combo.currentIndexChanged.connect(self._on_filters_changed)
        self.size_combo.currentIndexChanged.connect(self._on_filters_changed)

    def _on_enabled_toggled(self, checked: bool) -> None:
        self.enable_button.setText("Stop" if checked else "Start")
        self.skip_button.setEnabled(bool(checked))
        self.enabledChanged.emit(bool(checked))

    def _on_filters_changed(self, _index: int = 0) -> None:
        self.filtersChanged.emit()

    def kind(self) -> str:
        return str(self.kind_combo.currentData() or "plant")

    def size(self) -> str:
        return str(self.size_combo.currentData() or "")

    def set_kind(self, kind: str) -> None:
        index = self.kind_combo.findData(kind)
        if index >= 0:
            self.kind_combo.setCurrentIndex(index)

    def set_size(self, size: str) -> None:
        index = self.size_combo.findData(size)
        if index >= 0:
            self.size_combo.setCurrentIndex(index)

    def set_enabled_checked(self, enabled: bool) -> None:
        if self.enable_button.isChecked() == bool(enabled):
            self.enable_button.setText("Stop" if enabled else "Start")
            self.skip_button.setEnabled(bool(enabled))
            return
        self.enable_button.blockSignals(True)
        self.enable_button.setChecked(bool(enabled))
        self.enable_button.blockSignals(False)
        self.enable_button.setText("Stop" if enabled else "Start")
        self.skip_button.setEnabled(bool(enabled))

    def set_status(self, title: str, detail: str) -> None:
        self.status_title.setText(title)
        self.status_detail.setText(detail)


class GatherNavMixin:
    """Nearest-resource gather routing driven by live interactibles + static POIs."""

    LIVE_RANGE_M = 600.0
    LIVE_Z_CULL_M = 80.0
    LIVE_MATCH_M = 12.0
    DEPLETED_GRACE_S = 0.75

    def _init_gather_nav_state(self) -> None:
        self.gather_nav_enabled = False
        self.gather_nav_kind = "plant"
        self.gather_nav_size = "large"
        self.gather_nav_target: dict[str, Any] | None = None
        self.gather_nav_skipped: set[str] = set()
        self.gather_nav_depleted: set[str] = set()
        self.gather_nav_depleted_positions: list[tuple[float, float]] = []
        self._gather_missing_since: float | None = None
        self._gather_missing_key: str | None = None

    def _gather_nav_panel(self) -> GatherNavPanel | None:
        panel = getattr(self, "gather_panel", None)
        return panel if isinstance(panel, GatherNavPanel) else None

    def _wire_gather_nav_panel(self) -> None:
        panel = self._gather_nav_panel()
        if panel is None:
            return
        panel.set_kind(self.gather_nav_kind)
        panel.set_size(self.gather_nav_size)
        panel.set_enabled_checked(self.gather_nav_enabled)
        panel.enabledChanged.connect(self._set_gather_nav_enabled)
        panel.filtersChanged.connect(self._on_gather_nav_filters_changed)
        panel.skipRequested.connect(self._skip_gather_nav_target)
        self._refresh_gather_nav_panel()

    def _set_gather_nav_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.gather_nav_enabled:
            return
        self.gather_nav_enabled = enabled
        if enabled:
            # Destination is exclusive with custom waypoint routing.
            if getattr(self, "active_custom_waypoint_id", None) is not None:
                self._set_active_custom_waypoint(None)
            self.gather_nav_skipped.clear()
            self.gather_nav_depleted.clear()
            self.gather_nav_depleted_positions.clear()
            self._gather_missing_since = None
            self._gather_missing_key = None
            self._ensure_gather_loot_filter_visible()
            notify(self, "Gather nav started")
            self._gather_nav_retarget(force=True)
        else:
            self._clear_gather_nav_target()
            notify(self, "Gather nav stopped")
            self._refresh_gather_nav_panel()

    def _on_gather_nav_filters_changed(self) -> None:
        panel = self._gather_nav_panel()
        if panel is None:
            return
        self.gather_nav_kind = panel.kind()
        self.gather_nav_size = panel.size()
        self._settings.setValue("map/gather_nav_kind", self.gather_nav_kind)
        self._settings.setValue("map/gather_nav_size", self.gather_nav_size)
        if self.gather_nav_enabled:
            self.gather_nav_skipped.clear()
            self.gather_nav_depleted.clear()
            self.gather_nav_depleted_positions.clear()
            self._gather_missing_since = None
            self._gather_missing_key = None
            self._ensure_gather_loot_filter_visible()
            self._gather_nav_retarget(force=True)
        else:
            self._refresh_gather_nav_panel()

    def _ensure_gather_loot_filter_visible(self) -> None:
        kind = self.gather_nav_kind
        button = getattr(self, "loot_filters", {}).get(kind)
        if button is None or button.isChecked():
            return
        button.blockSignals(True)
        button.setChecked(True)
        button.blockSignals(False)
        if hasattr(self, "_controls_changed"):
            self._controls_changed()

    def _skip_gather_nav_target(self) -> None:
        target = self.gather_nav_target
        if target is None:
            return
        self._mark_gather_depleted(target)
        key = str(target.get("key") or "")
        if key:
            self.gather_nav_skipped.add(key)
        self._clear_gather_nav_target()
        self._gather_nav_retarget(force=True)

    def _clear_gather_nav_target(self) -> None:
        self.gather_nav_target = None
        self._gather_missing_since = None
        self._gather_missing_key = None
        radar = getattr(self, "radar", None)
        if radar is not None and hasattr(radar, "set_gather_target"):
            radar.set_gather_target(None)

    def _stop_gather_nav_for_waypoint(self) -> None:
        if not self.gather_nav_enabled:
            return
        self.gather_nav_enabled = False
        self._clear_gather_nav_target()
        panel = self._gather_nav_panel()
        if panel is not None:
            panel.set_enabled_checked(False)
        self._refresh_gather_nav_panel()

    def _gather_nav_tick(self, snapshot: Any = None) -> None:
        if not self.gather_nav_enabled:
            self._refresh_gather_nav_panel()
            return
        self._revive_depleted_from_live(snapshot)
        if self._gather_target_collected(snapshot):
            self._mark_gather_depleted(self.gather_nav_target, snapshot)
            self._clear_gather_nav_target()
            self._gather_nav_retarget(force=True, snapshot=snapshot)
            return
        if self.gather_nav_target is None:
            self._gather_nav_retarget(force=False, snapshot=snapshot)
            return
        self._sync_gather_target_live(snapshot)
        self._push_gather_target_to_radar()
        self._refresh_gather_nav_panel()

    def _gather_player_position(self) -> dict[str, float] | None:
        getter = getattr(self, "_current_player_position", None)
        if callable(getter):
            player = getter()
            if isinstance(player, dict):
                return player
        return None

    def _gather_snapshot_state(self, snapshot: Any = None) -> dict[str, Any]:
        snap = snapshot if snapshot is not None else getattr(self, "latest_snapshot", None)
        state = getattr(snap, "state", None) if snap is not None else None
        if isinstance(state, dict):
            return state
        return {}

    def _gather_pois(self, snapshot: Any = None) -> list[dict[str, Any]]:
        snap = snapshot if snapshot is not None else getattr(self, "latest_snapshot", None)
        pois = getattr(snap, "pois", None) if snap is not None else None
        if isinstance(pois, list):
            return [item for item in pois if isinstance(item, dict)]
        radar = getattr(self, "radar", None)
        if radar is not None and isinstance(getattr(radar, "pois", None), list):
            return [item for item in radar.pois if isinstance(item, dict)]
        return []

    def _gather_live_nodes(self, snapshot: Any = None) -> list[dict[str, Any]]:
        state = self._gather_snapshot_state(snapshot)
        nodes = state.get("interactibles", [])
        if not isinstance(nodes, list):
            return []
        return [item for item in nodes if isinstance(item, dict)]

    def _matches_gather_kind(self, item: dict[str, Any]) -> bool:
        kind = str(item.get("kind") or "").strip().lower()
        wanted = self.gather_nav_kind
        if kind == "gatherable":
            return wanted in {"plant", "ore"}
        return kind == wanted

    def _matches_gather_filters(
        self,
        item: dict[str, Any],
        *,
        allow_unknown_size: bool = False,
    ) -> bool:
        if not self._matches_gather_kind(item):
            return False
        size_filter = self.gather_nav_size
        if not size_filter:
            return True
        size = _node_size_label(item)
        if not size:
            # Chests / untagged live names: allow when requested.
            if str(item.get("kind") or "").strip().lower() == "chest":
                return True
            return bool(allow_unknown_size)
        return size == size_filter

    def _live_covers(
        self,
        poi: dict[str, Any],
        live_nodes: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        px = safe_float(poi.get("x"), math.nan)
        py = safe_float(poi.get("y"), math.nan)
        if not (math.isfinite(px) and math.isfinite(py)):
            return None
        best: dict[str, Any] | None = None
        best_dist = self.LIVE_MATCH_M
        poi_kind = str(poi.get("kind") or "").strip().lower()
        for live in live_nodes:
            live_kind = str(live.get("kind") or "").strip().lower()
            if live_kind == poi_kind:
                pass
            elif live_kind == "gatherable" and poi_kind in {"plant", "ore"}:
                pass
            elif poi_kind == "gatherable" and live_kind in {"plant", "ore"}:
                pass
            else:
                continue
            lx = safe_float(live.get("x"), math.nan)
            ly = safe_float(live.get("y"), math.nan)
            if not (math.isfinite(lx) and math.isfinite(ly)):
                continue
            dist = math.hypot(lx - px, ly - py)
            if dist <= best_dist:
                best = live
                best_dist = dist
        return best

    def _in_live_range(
        self,
        player: dict[str, float],
        item: dict[str, Any],
    ) -> bool:
        px = safe_float(player.get("x"), math.nan)
        py = safe_float(player.get("y"), math.nan)
        pz = safe_float(player.get("z"), math.nan)
        x = safe_float(item.get("x"), math.nan)
        y = safe_float(item.get("y"), math.nan)
        z = safe_float(item.get("z"), math.nan)
        if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(x) and math.isfinite(y)):
            return False
        if math.hypot(x - px, y - py) > self.LIVE_RANGE_M:
            return False
        if math.isfinite(pz) and math.isfinite(z) and abs(z - pz) > self.LIVE_Z_CULL_M:
            return False
        return True

    def _mark_gather_depleted(self, target: dict[str, Any] | None, snapshot: Any = None) -> None:
        if not isinstance(target, dict):
            return
        key = str(target.get("key") or "")
        if key:
            self.gather_nav_depleted.add(key)
        live_id = str(target.get("live_id") or "")
        if live_id:
            self.gather_nav_depleted.add(f"live:{live_id}")
        tx = safe_float(target.get("x"), math.nan)
        ty = safe_float(target.get("y"), math.nan)
        if not (math.isfinite(tx) and math.isfinite(ty)):
            return
        self.gather_nav_depleted_positions.append((tx, ty))
        # Also deplete the matching static POI so a live-only key does not leave
        # the same node selectable via its file marker.
        for poi in self._gather_pois(snapshot):
            if not self._matches_gather_kind(poi):
                continue
            px = safe_float(poi.get("x"), math.nan)
            py = safe_float(poi.get("y"), math.nan)
            if not (math.isfinite(px) and math.isfinite(py)):
                continue
            if math.hypot(px - tx, py - ty) <= self.LIVE_MATCH_M:
                self.gather_nav_depleted.add(_static_key(poi))

    def _is_gather_position_depleted(self, x: float, y: float) -> bool:
        if not (math.isfinite(x) and math.isfinite(y)):
            return False
        for dx, dy in self.gather_nav_depleted_positions:
            if math.hypot(x - dx, y - dy) <= self.LIVE_MATCH_M:
                return True
        return False

    def _revive_depleted_from_live(self, snapshot: Any = None) -> None:
        """Drop depleted marks once a live node covers that static again."""
        if not self.gather_nav_depleted and not self.gather_nav_depleted_positions:
            return
        all_live = [
            item
            for item in self._gather_live_nodes(snapshot)
            if self._matches_gather_kind(item)
        ]
        if not all_live:
            return
        revived_keys: set[str] = set()
        for poi in self._gather_pois(snapshot):
            key = _static_key(poi)
            if key not in self.gather_nav_depleted and not self._is_gather_position_depleted(
                safe_float(poi.get("x"), math.nan),
                safe_float(poi.get("y"), math.nan),
            ):
                continue
            if self._live_covers(poi, all_live) is None:
                continue
            revived_keys.add(key)
            px = safe_float(poi.get("x"), math.nan)
            py = safe_float(poi.get("y"), math.nan)
            if math.isfinite(px) and math.isfinite(py):
                self.gather_nav_depleted_positions = [
                    (dx, dy)
                    for dx, dy in self.gather_nav_depleted_positions
                    if math.hypot(px - dx, py - dy) > self.LIVE_MATCH_M
                ]
        if revived_keys:
            self.gather_nav_depleted -= revived_keys
        # Revive live-id marks that are present again.
        live_ids = {
            str(item.get("id") or "")
            for item in all_live
            if str(item.get("id") or "")
        }
        self.gather_nav_depleted = {
            key
            for key in self.gather_nav_depleted
            if not (
                key.startswith("live:")
                and key.removeprefix("live:") in live_ids
            )
        }

    def _gather_candidates(
        self,
        player: dict[str, float],
        snapshot: Any = None,
    ) -> list[dict[str, Any]]:
        all_live = self._gather_live_nodes(snapshot)
        live_feed_active = bool(all_live)
        # Cover checks are kind-only so untagged live names still match a sized
        # static POI. Size is enforced on the static (or soft-matched on orphans).
        kind_live = [
            item for item in all_live if self._matches_gather_kind(item)
        ]
        sized_live = [
            item
            for item in kind_live
            if self._matches_gather_filters(item, allow_unknown_size=True)
        ]
        covered_live_ids: set[str] = set()
        candidates: list[dict[str, Any]] = []
        px = safe_float(player.get("x"), math.nan)
        py = safe_float(player.get("y"), math.nan)

        for poi in self._gather_pois(snapshot):
            kind = str(poi.get("kind") or "").strip().lower()
            if kind not in {"plant", "ore", "chest", "gatherable"}:
                continue
            if not self._matches_gather_filters(poi):
                continue
            key = _static_key(poi)
            if key in self.gather_nav_skipped or key in self.gather_nav_depleted:
                continue
            if self._is_gather_position_depleted(
                safe_float(poi.get("x"), math.nan),
                safe_float(poi.get("y"), math.nan),
            ):
                continue
            live = None
            if self._in_live_range(player, poi):
                live = self._live_covers(poi, kind_live)
                # Inside the live bubble, only route to nodes that currently
                # exist as interactibles — otherwise we jump past nearer
                # farmed spots to a far static outside the bubble.
                if live is None and live_feed_active:
                    continue
                if live is not None:
                    live_id = str(live.get("id") or "")
                    if live_id:
                        covered_live_ids.add(live_id)
            x = safe_float(live.get("x") if live else poi.get("x"), math.nan)
            y = safe_float(live.get("y") if live else poi.get("y"), math.nan)
            z = safe_float(live.get("z") if live else poi.get("z"), 0.0)
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(px) and math.isfinite(py)):
                continue
            if self._is_gather_position_depleted(x, y):
                continue
            distance = math.hypot(x - px, y - py)
            candidates.append(
                {
                    "key": key,
                    "kind": kind if kind != "gatherable" else self.gather_nav_kind,
                    "name": _display_name(live or poi),
                    "size": _node_size_label(live or poi),
                    "x": x,
                    "y": y,
                    "z": z,
                    "live_id": str((live or {}).get("id") or "") or None,
                    "distance": distance,
                    "source": "live" if live else "static",
                }
            )

        for live in sized_live:
            live_id = str(live.get("id") or "")
            if live_id and live_id in covered_live_ids:
                continue
            key = _live_key(live)
            if key in self.gather_nav_skipped or key in self.gather_nav_depleted:
                continue
            x = safe_float(live.get("x"), math.nan)
            y = safe_float(live.get("y"), math.nan)
            z = safe_float(live.get("z"), 0.0)
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(px) and math.isfinite(py)):
                continue
            if self._is_gather_position_depleted(x, y):
                continue
            distance = math.hypot(x - px, y - py)
            candidates.append(
                {
                    "key": key,
                    "kind": str(live.get("kind") or self.gather_nav_kind),
                    "name": _display_name(live),
                    "size": _node_size_label(live),
                    "x": x,
                    "y": y,
                    "z": z,
                    "live_id": live_id or None,
                    "distance": distance,
                    "source": "live",
                }
            )

        # Nearest first; prefer live when distances tie.
        candidates.sort(
            key=lambda item: (
                safe_float(item.get("distance"), math.inf),
                0 if item.get("source") == "live" else 1,
                str(item.get("name") or ""),
            )
        )
        return candidates

    def _gather_nav_retarget(self, *, force: bool, snapshot: Any = None) -> None:
        player = self._gather_player_position()
        if player is None:
            self._clear_gather_nav_target()
            self._refresh_gather_nav_panel(
                title="Waiting",
                detail="Player coordinates unavailable — wait for the bridge.",
            )
            return
        self._revive_depleted_from_live(snapshot)
        candidates = self._gather_candidates(player, snapshot)
        if not candidates:
            self._clear_gather_nav_target()
            size_note = (
                f" {self.gather_nav_size}" if self.gather_nav_size else ""
            )
            self._refresh_gather_nav_panel(
                title="No nodes",
                detail=(
                    f"No matching {self.gather_nav_kind}{size_note} resources "
                    "found (live or static)."
                ),
            )
            return
        next_target = candidates[0]
        current = self.gather_nav_target
        if (
            not force
            and current is not None
            and str(current.get("key")) == str(next_target.get("key"))
        ):
            self.gather_nav_target = {
                **current,
                **next_target,
                "distance": next_target.get("distance"),
            }
        else:
            self.gather_nav_target = dict(next_target)
            self._gather_missing_since = None
            self._gather_missing_key = None
        self._push_gather_target_to_radar()
        self._refresh_gather_nav_panel()

    def _sync_gather_target_live(self, snapshot: Any = None) -> None:
        target = self.gather_nav_target
        player = self._gather_player_position()
        if target is None or player is None:
            return
        kind_live = [
            item
            for item in self._gather_live_nodes(snapshot)
            if self._matches_gather_kind(item)
        ]
        live_feed_active = bool(self._gather_live_nodes(snapshot))
        live_id = str(target.get("live_id") or "")
        if live_id:
            for live in kind_live:
                if str(live.get("id") or "") == live_id:
                    target["x"] = safe_float(live.get("x"), target.get("x"))
                    target["y"] = safe_float(live.get("y"), target.get("y"))
                    target["z"] = safe_float(live.get("z"), target.get("z"))
                    target["name"] = _display_name(live)
                    target["distance"] = math.hypot(
                        safe_float(target.get("x")) - safe_float(player.get("x")),
                        safe_float(target.get("y")) - safe_float(player.get("y")),
                    )
                    target["source"] = "live"
                    return
            return

        if not self._in_live_range(player, target):
            target["distance"] = math.hypot(
                safe_float(target.get("x")) - safe_float(player.get("x")),
                safe_float(target.get("y")) - safe_float(player.get("y")),
            )
            return

        live = self._live_covers(target, kind_live)
        if live is not None:
            target["live_id"] = str(live.get("id") or "") or None
            target["x"] = safe_float(live.get("x"), target.get("x"))
            target["y"] = safe_float(live.get("y"), target.get("y"))
            target["z"] = safe_float(live.get("z"), target.get("z"))
            target["name"] = _display_name(live)
            target["source"] = "live"
            target["distance"] = math.hypot(
                safe_float(target.get("x")) - safe_float(player.get("x")),
                safe_float(target.get("y")) - safe_float(player.get("y")),
            )
            self._gather_missing_since = None
            self._gather_missing_key = None
            return

        if not live_feed_active:
            target["distance"] = math.hypot(
                safe_float(target.get("x")) - safe_float(player.get("x")),
                safe_float(target.get("y")) - safe_float(player.get("y")),
            )
            return

        # Entered live range but node is gone — treat as depleted after grace.
        key = str(target.get("key") or "")
        now = time.monotonic()
        if self._gather_missing_key != key:
            self._gather_missing_key = key
            self._gather_missing_since = now
        elif (
            self._gather_missing_since is not None
            and now - self._gather_missing_since >= self.DEPLETED_GRACE_S
        ):
            self._mark_gather_depleted(target, snapshot)
            self._clear_gather_nav_target()
            self._gather_nav_retarget(force=True, snapshot=snapshot)

    def _gather_target_collected(self, snapshot: Any = None) -> bool:
        target = self.gather_nav_target
        if target is None:
            return False
        live_id = str(target.get("live_id") or "")
        if not live_id:
            return False
        live_nodes = self._gather_live_nodes(snapshot)
        for live in live_nodes:
            if str(live.get("id") or "") == live_id:
                self._gather_missing_since = None
                self._gather_missing_key = None
                return False
        # Live id gone. Confirm with a short grace so a single missed sweep
        # does not skip ahead; empty-feed detach uses the same grace.
        key = f"live-gone:{live_id}"
        now = time.monotonic()
        if self._gather_missing_key != key:
            self._gather_missing_key = key
            self._gather_missing_since = now
            return False
        if (
            self._gather_missing_since is not None
            and now - self._gather_missing_since >= self.DEPLETED_GRACE_S
        ):
            return True
        return False

    def _push_gather_target_to_radar(self) -> None:
        radar = getattr(self, "radar", None)
        if radar is None or not hasattr(radar, "set_gather_target"):
            return
        target = self.gather_nav_target
        if target is None:
            radar.set_gather_target(None)
            return
        radar.set_gather_target(
            {
                "x": safe_float(target.get("x")),
                "y": safe_float(target.get("y")),
                "z": safe_float(target.get("z")),
                "name": str(target.get("name") or "Gather target"),
                "kind": str(target.get("kind") or self.gather_nav_kind),
                "size": str(target.get("size") or ""),
            }
        )

    def _refresh_gather_nav_panel(
        self,
        *,
        title: str | None = None,
        detail: str | None = None,
    ) -> None:
        panel = self._gather_nav_panel()
        if panel is None:
            return
        if title is not None and detail is not None:
            panel.set_status(title, detail)
            return
        if not self.gather_nav_enabled:
            panel.set_status(
                "Idle",
                "Enable gather nav to route to the closest matching node.",
            )
            return
        target = self.gather_nav_target
        if target is None:
            panel.set_status(
                "Searching…",
                "Looking for the next matching resource.",
            )
            return
        distance = safe_float(target.get("distance"), math.nan)
        distance_text = f"{distance:.1f} m" if math.isfinite(distance) else "—"
        source = str(target.get("source") or "static")
        panel.set_status(
            str(target.get("name") or "Gather target"),
            f"{distance_text} · {source} · route line active",
        )
