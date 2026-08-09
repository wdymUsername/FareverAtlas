"""NODE GUIDE mixin and panel: nearest node → route line → collect → next."""

from __future__ import annotations

import math
import time
from typing import Any

from PySide6 import QtCore, QtWidgets

from ...config import safe_float
from ...cull_limits import DEFAULT_LOOT_XY_M, DEFAULT_LOOT_Z_M
from ...display_names import (
    chest_label_from_id,
    format_gatherable_tooltip_name,
    is_activity_linked_chest,
)
from ...toast import notify


GATHER_KINDS = (
    ("plant", "Plant"),
    ("ore", "Ore"),
    ("chest", "Chest"),
    ("red_orb", "Red Orb"),
    ("pet", "Pets"),
)

# Static-only kinds have no live interactible feed; completion / codex gates them.
_STATIC_GATHER_KINDS = frozenset({"red_orb", "pet"})
_SIZED_GATHER_KINDS = frozenset({"plant", "ore", "gatherable"})
_TYPED_GATHER_KINDS = frozenset({"plant", "ore", "chest"})

GATHER_SIZES = (
    ("", "Any size"),
    ("small", "Small"),
    ("medium", "Medium"),
    ("large", "Large"),
)

# Size / filler tokens only — do not strip "world" (WorldChest) or material words.
_SIZE_TYPE_TOKENS = frozenset(
    {"small", "medium", "large", "big", "generic"}
)

# Fallback labels when a type has not been seen in POIs yet.
_TYPE_LABELS = {
    "lavendula": "Lavendula",
    "madrigold": "Madrigold",
    "ancientthyme": "Ancient Thyme",
    "zealotus": "Zealotus",
    "copperore": "Copper",
    "tinore": "Tin",
    "tungstene": "Tungsten",
    "worldchest": "World Chest",
    "recipechest": "Recipe Chest",
    "orbchest": "Orb Chest",
    "vaultchest": "Vault Chest",
    "campchest": "Camp Chest",
}

# Activity-linked chests — found via quest/activity progression, not NODE GUIDE.
_ACTIVITY_CHEST_TYPES = frozenset({"orbchest", "chestorb", "campchest", "vaultchest"})

_PLANT_TYPE_FALLBACKS = (
    "lavendula",
    "madrigold",
    "ancientthyme",
    "zealotus",
)
_ORE_TYPE_FALLBACKS = (
    "copperore",
    "tinore",
    "tungstene",
)
_CHEST_TYPE_FALLBACKS = (
    "worldchest",
    "recipechest",
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


def _source_prefab_stem(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "").strip().replace("\\", "/")
    if not source:
        return ""
    stem = source.rsplit("/", 1)[-1]
    if stem.lower().endswith(".prefab"):
        stem = stem[: -len(".prefab")]
    return stem


def _is_opaque_plant_code(name: str) -> bool:
    """POI export placeholders like R2Plant2 — not the in-game species name."""
    lowered = str(name or "").strip().lower().replace("-", "_")
    if not lowered:
        return False
    head = lowered.split("_", 1)[0]
    return head.startswith("r2plant") or head in {"r2plant2", "r2plant3", "r2plantrare"}


def _is_generic_chest_name(name: str) -> bool:
    """Bare 'Chest' name that hides OrbChest / CampChest / etc. in the source."""
    lowered = str(name or "").strip().lower().replace("-", "_")
    return lowered in {"", "chest"}


def _raw_node_name(item: dict[str, Any]) -> str:
    """Best species/material/chest id — prefer real prefab over export codes."""
    name = str(item.get("name") or "").strip()
    source_stem = _source_prefab_stem(item)
    kind = str(item.get("kind") or "").strip().lower()
    if source_stem and (
        not name
        or (
            _is_opaque_plant_code(name)
            and not _is_opaque_plant_code(source_stem)
        )
        or (
            kind == "chest"
            and _is_generic_chest_name(name)
            and not _is_generic_chest_name(source_stem)
        )
    ):
        return source_stem
    if name:
        return name
    return source_stem


def _type_key_from_raw(raw: str) -> str:
    if not raw:
        return ""
    parts = [
        part
        for part in raw.replace("-", "_").replace(" ", "_").split("_")
        if part and part.lower() not in _SIZE_TYPE_TOKENS
    ]
    return "".join(parts).lower() if parts else ""


def _node_type_key(item: dict[str, Any]) -> str:
    """Species / material key with size tokens stripped (lavendula, copperore)."""
    key = _type_key_from_raw(_raw_node_name(item))
    # Never surface opaque R2* export codes as selectable types.
    if _is_opaque_plant_code(key) or key.startswith("r2plant"):
        return ""
    return key


def _pretty_type_label(type_key: str, sample_name: str = "") -> str:
    key = str(type_key or "").strip().lower()
    if not key:
        return "Unknown"
    known = _TYPE_LABELS.get(key)
    if known:
        return known
    chest = chest_label_from_id(key) or chest_label_from_id(sample_name)
    if chest:
        return chest
    # Prefer a cleaned sample name (drop size tokens) when available.
    sample_parts = [
        part
        for part in str(sample_name or "").replace("-", "_").split("_")
        if part and part.lower() not in _SIZE_TYPE_TOKENS
    ]
    if sample_parts:
        return " ".join(sample_parts)
    if key.endswith("ore") and len(key) > 3:
        return f"{key[:-3].title()} Ore"
    return key.title()


def _discover_gather_types(
    items: list[dict[str, Any]], kind: str
) -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "").strip().lower() != kind:
            continue
        type_key = _node_type_key(item)
        if not type_key:
            continue
        if kind == "chest" and (
            type_key in _ACTIVITY_CHEST_TYPES
            or is_activity_linked_chest(
                item.get("name"),
                item.get("id"),
                item.get("source"),
                item.get("subkind"),
            )
        ):
            continue
        found.setdefault(type_key, _pretty_type_label(type_key, _raw_node_name(item)))
    return sorted(found.items(), key=lambda pair: pair[1].lower())


def _display_name(item: dict[str, Any]) -> str:
    raw = _raw_node_name(item)
    kind = str(item.get("kind") or "").strip()
    size = _node_size_label(item)
    return format_gatherable_tooltip_name(
        raw or None,
        kind=kind or None,
        size=size or None,
        fallback=raw or None,
        source=str(item.get("source") or "") or None,
        item_id=str(item.get("id") or "") or None,
    )


def _static_key(poi: dict[str, Any]) -> str:
    poi_id = str(poi.get("id") or "").strip()
    if poi_id:
        return f"static-id:{poi_id}"
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


def _completion_ids(state: dict[str, Any]) -> set[str]:
    raw = state.get("completed_elements", [])
    if not isinstance(raw, list):
        return set()
    return {str(value).strip() for value in raw if str(value).strip()}


def _element_completed(poi_id: str, completed: set[str]) -> bool:
    """Match character progress keys to POI ids (exact or path / suffix)."""
    needle = str(poi_id or "").strip()
    if not needle or not completed:
        return False
    if needle in completed:
        return True
    for key in completed:
        if key.endswith(needle) or key.rsplit("/", 1)[-1] == needle:
            return True
    return False


class GatherNavPanel(QtWidgets.QWidget):
    """Controls for NODE GUIDE navigation (floating map overlay)."""

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
                "Route to the nearest matching node, then advance when it is "
                "collected or completed for this character."
            )
            intro.setObjectName("waypointOverlayBody")
            intro.setWordWrap(True)
            root.addWidget(intro)

        kind_label = QtWidgets.QLabel("TARGET")
        kind_label.setObjectName(
            "gatherNavFieldLabel" if self._compact else "waypointColumnHeader"
        )
        root.addWidget(kind_label)
        self.kind_combo = QtWidgets.QComboBox()
        self.kind_combo.setObjectName("gatherNavCombo")
        for kind, label in GATHER_KINDS:
            self.kind_combo.addItem(label, kind)
        root.addWidget(self.kind_combo)

        self.type_label = QtWidgets.QLabel("TYPE")
        self.type_label.setObjectName(
            "gatherNavFieldLabel" if self._compact else "waypointColumnHeader"
        )
        root.addWidget(self.type_label)
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setObjectName("gatherNavCombo")
        self.type_combo.addItem("Any type", "")
        root.addWidget(self.type_combo)

        self.size_label = QtWidgets.QLabel("SIZE")
        self.size_label.setObjectName(
            "gatherNavFieldLabel" if self._compact else "waypointColumnHeader"
        )
        root.addWidget(self.size_label)
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
            else "Start NODE GUIDE to find the closest matching node."
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
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        self.type_combo.currentIndexChanged.connect(self._on_filters_changed)
        self.size_combo.currentIndexChanged.connect(self._on_filters_changed)
        self._type_options: list[tuple[str, str]] = []
        self._sync_filter_visibility()

    def _on_enabled_toggled(self, checked: bool) -> None:
        self.enable_button.setText("Stop" if checked else "Start")
        self.skip_button.setEnabled(bool(checked))
        self.enabledChanged.emit(bool(checked))

    def _on_kind_changed(self, _index: int = 0) -> None:
        self._sync_filter_visibility()
        self.filtersChanged.emit()

    def _on_filters_changed(self, _index: int = 0) -> None:
        self.filtersChanged.emit()

    def _sync_filter_visibility(self) -> None:
        kind = self.kind()
        typed = kind in _TYPED_GATHER_KINDS
        self.type_label.setVisible(typed)
        self.type_combo.setVisible(typed)
        self.type_combo.setEnabled(typed)
        sized = kind in _SIZED_GATHER_KINDS
        self.size_label.setVisible(sized)
        self.size_combo.setVisible(sized)
        self.size_combo.setEnabled(sized)

    def kind(self) -> str:
        return str(self.kind_combo.currentData() or "plant")

    def node_type(self) -> str:
        if self.kind() not in _TYPED_GATHER_KINDS:
            return ""
        return str(self.type_combo.currentData() or "")

    def size(self) -> str:
        if self.kind() not in _SIZED_GATHER_KINDS:
            return ""
        return str(self.size_combo.currentData() or "")

    def set_kind(self, kind: str) -> None:
        index = self.kind_combo.findData(kind)
        if index >= 0:
            self.kind_combo.blockSignals(True)
            self.kind_combo.setCurrentIndex(index)
            self.kind_combo.blockSignals(False)
        self._sync_filter_visibility()

    def set_type_options(
        self, options: list[tuple[str, str]], selected: str = ""
    ) -> None:
        """Populate TYPE choices as (key, label); always includes Any type."""
        selected = str(selected or "")
        normalized = [("", "Any type")]
        seen = {""}
        for key, label in options:
            key = str(key or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            normalized.append((key, str(label or _pretty_type_label(key))))
        self._type_options = normalized
        current = self.node_type() if selected == "" else selected
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        for key, label in normalized:
            self.type_combo.addItem(label, key)
        index = self.type_combo.findData(current)
        if index < 0:
            index = 0
        self.type_combo.setCurrentIndex(index)
        self.type_combo.blockSignals(False)
        self._sync_filter_visibility()

    def set_type(self, type_key: str) -> None:
        index = self.type_combo.findData(str(type_key or ""))
        if index >= 0:
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentIndex(index)
            self.type_combo.blockSignals(False)

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
    """Nearest-node collect routing driven by live interactibles + static POIs."""

    LIVE_MATCH_M = 12.0
    DEPLETED_GRACE_S = 0.75

    def _init_gather_nav_state(self) -> None:
        self.gather_nav_enabled = False
        self.gather_nav_kind = "plant"
        self.gather_nav_type = ""
        self.gather_nav_size = "large"
        self.gather_nav_target: dict[str, Any] | None = None
        self.gather_nav_skipped: set[str] = set()
        self.gather_nav_depleted: set[str] = set()
        self.gather_nav_depleted_positions: list[tuple[float, float]] = []
        self._gather_missing_since: float | None = None
        self._gather_missing_key: str | None = None
        self.LIVE_RANGE_M = float(DEFAULT_LOOT_XY_M)
        self.LIVE_Z_CULL_M = float(DEFAULT_LOOT_Z_M)

    def _gather_nav_panel(self) -> GatherNavPanel | None:
        panel = getattr(self, "gather_panel", None)
        return panel if isinstance(panel, GatherNavPanel) else None

    def _refresh_gather_type_options(self) -> None:
        panel = self._gather_nav_panel()
        if panel is None:
            return
        kind = self.gather_nav_kind
        if kind not in _TYPED_GATHER_KINDS:
            panel.set_type_options([], selected="")
            return
        options = _discover_gather_types(self._gather_pois(), kind)
        # Keep known species/materials/chest families visible if POIs are thin.
        if kind == "plant":
            fallback_keys = _PLANT_TYPE_FALLBACKS
        elif kind == "ore":
            fallback_keys = _ORE_TYPE_FALLBACKS
        elif kind == "chest":
            fallback_keys = _CHEST_TYPE_FALLBACKS
        else:
            fallback_keys = ()
        known = {
            key: _TYPE_LABELS[key]
            for key in fallback_keys
            if key in _TYPE_LABELS
        }
        merged = {**known, **dict(options)}
        selected = self.gather_nav_type
        if selected in _ACTIVITY_CHEST_TYPES:
            selected = ""
        panel.set_type_options(
            sorted(merged.items(), key=lambda pair: pair[1].lower()),
            selected=selected,
        )
        self.gather_nav_type = panel.node_type()

    def _wire_gather_nav_panel(self) -> None:
        panel = self._gather_nav_panel()
        if panel is None:
            return
        panel.set_kind(self.gather_nav_kind)
        self._refresh_gather_type_options()
        panel.set_type(self.gather_nav_type)
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
            if hasattr(self, "_set_gather_sidebar_collapsed"):
                self._set_gather_sidebar_collapsed(False)
            notify(self, "NODE GUIDE started")
            self._gather_nav_retarget(force=True)
        else:
            self._clear_gather_nav_target()
            notify(self, "NODE GUIDE stopped")
            self._refresh_gather_nav_panel()

    def _on_gather_nav_filters_changed(self) -> None:
        panel = self._gather_nav_panel()
        if panel is None:
            return
        previous_kind = self.gather_nav_kind
        self.gather_nav_kind = panel.kind()
        if self.gather_nav_kind != previous_kind:
            self._refresh_gather_type_options()
        self.gather_nav_type = panel.node_type()
        self.gather_nav_size = panel.size()
        self._settings.setValue("map/gather_nav_kind", self.gather_nav_kind)
        self._settings.setValue("map/gather_nav_type", self.gather_nav_type)
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
        if kind != wanted:
            return False
        # Orb / camp / vault chests are activity rewards — skip in NODE GUIDE.
        if wanted == "chest" and is_activity_linked_chest(
            item.get("name"),
            item.get("id"),
            item.get("source"),
            item.get("subkind"),
        ):
            return False
        return True

    def _matches_gather_filters(
        self,
        item: dict[str, Any],
        *,
        allow_unknown_size: bool = False,
    ) -> bool:
        if not self._matches_gather_kind(item):
            return False
        kind = str(item.get("kind") or "").strip().lower()
        if kind in _STATIC_GATHER_KINDS or self.gather_nav_kind in _STATIC_GATHER_KINDS:
            return True
        type_filter = str(self.gather_nav_type or "").strip().lower()
        if type_filter in _ACTIVITY_CHEST_TYPES:
            type_filter = ""
        if type_filter and self.gather_nav_kind in _TYPED_GATHER_KINDS:
            item_type = _node_type_key(item)
            if item_type != type_filter:
                return False
        size_filter = self.gather_nav_size
        if not size_filter:
            return True
        size = _node_size_label(item)
        if not size:
            # Chests / untagged live names: allow when requested.
            if kind == "chest":
                return True
            return bool(allow_unknown_size)
        return size == size_filter

    def _live_covers(
        self,
        poi: dict[str, Any],
        live_nodes: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        poi_kind = str(poi.get("kind") or "").strip().lower()
        if poi_kind in _STATIC_GATHER_KINDS:
            return None
        px = safe_float(poi.get("x"), math.nan)
        py = safe_float(poi.get("y"), math.nan)
        if not (math.isfinite(px) and math.isfinite(py)):
            return None
        best: dict[str, Any] | None = None
        best_dist = self.LIVE_MATCH_M
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
        if self.gather_nav_kind == "pet":
            # Placeholder for the future pet Codex / map markers.
            return []

        state = self._gather_snapshot_state(snapshot)
        completed = _completion_ids(state)
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
        static_only = self.gather_nav_kind in _STATIC_GATHER_KINDS

        for poi in self._gather_pois(snapshot):
            kind = str(poi.get("kind") or "").strip().lower()
            if kind not in {"plant", "ore", "chest", "gatherable", "red_orb", "pet"}:
                continue
            if not self._matches_gather_filters(poi):
                continue
            poi_id = str(poi.get("id") or "").strip()
            if kind in {"red_orb", "chest"} and _element_completed(poi_id, completed):
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
            if not static_only and self._in_live_range(player, poi):
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
                    "poi_id": poi_id or None,
                    "live_id": str((live or {}).get("id") or "") or None,
                    "distance": distance,
                    "source": "live" if live else "static",
                }
            )

        if not static_only:
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
                        "poi_id": None,
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
        if self.gather_nav_kind == "pet":
            self._clear_gather_nav_target()
            self._refresh_gather_nav_panel(
                title="Pets soon",
                detail=(
                    "Pet markers and Codex completion will plug in here — "
                    "routing is not available yet."
                ),
            )
            return
        self._revive_depleted_from_live(snapshot)
        candidates = self._gather_candidates(player, snapshot)
        if not candidates:
            self._clear_gather_nav_target()
            size_note = (
                f" {self.gather_nav_size}" if self.gather_nav_size else ""
            )
            label = {
                "red_orb": "red orb",
                "plant": "plant",
                "ore": "ore",
                "chest": "chest",
            }.get(self.gather_nav_kind, self.gather_nav_kind)
            type_note = ""
            if self.gather_nav_type:
                type_note = f" {_pretty_type_label(self.gather_nav_type)}"
            detail = (
                "No uncollected red orbs found for this character "
                "(completed ones stay muted on the map)."
                if self.gather_nav_kind == "red_orb"
                else f"No matching{type_note} {label}{size_note} nodes found."
            )
            self._refresh_gather_nav_panel(title="No nodes", detail=detail)
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
        kind = str(target.get("kind") or self.gather_nav_kind).strip().lower()
        if kind in _STATIC_GATHER_KINDS:
            target["distance"] = math.hypot(
                safe_float(target.get("x")) - safe_float(player.get("x")),
                safe_float(target.get("y")) - safe_float(player.get("y")),
            )
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
        kind = str(target.get("kind") or self.gather_nav_kind).strip().lower()
        if kind == "red_orb":
            poi_id = str(target.get("poi_id") or "").strip()
            if not poi_id:
                return False
            completed = _completion_ids(self._gather_snapshot_state(snapshot))
            return _element_completed(poi_id, completed)
        if kind == "chest":
            poi_id = str(target.get("poi_id") or "").strip()
            if poi_id:
                completed = _completion_ids(self._gather_snapshot_state(snapshot))
                if _element_completed(poi_id, completed):
                    return True
            # Live-only orphans (or progress not refreshed yet) fall through.

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
                "name": str(target.get("name") or "Node target"),
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
                "Start to route to the closest matching node.",
            )
            return
        target = self.gather_nav_target
        if target is None:
            panel.set_status(
                "Searching…",
                "Looking for the next matching node.",
            )
            return
        distance = safe_float(target.get("distance"), math.nan)
        distance_text = f"{distance:.1f} m" if math.isfinite(distance) else "—"
        source = str(target.get("source") or "static")
        panel.set_status(
            str(target.get("name") or "Node target"),
            f"{distance_text} · {source} · route line active",
        )
