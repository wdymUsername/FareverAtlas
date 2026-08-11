"""NODE GUIDE mixin and panel: nearest node → route line → collect → next."""

from __future__ import annotations

import math
import time
from typing import Any

from PySide6 import QtCore, QtWidgets

from ...config import safe_float
from ...critter_spawns import critter_spawns
from ...cull_limits import DEFAULT_LOOT_XY_M, DEFAULT_LOOT_Z_M
from ...display_names import (
    chest_label_from_id,
    format_gatherable_tooltip_name,
    format_unit_tooltip_name,
    is_activity_linked_chest,
)
from ...toast import notify


GATHER_KINDS = (
    ("plant", "Plant"),
    ("ore", "Ore"),
    ("chest", "Chest"),
    ("red_orb", "Red Orb"),
    ("critter", "Critters"),
)

# Static-only kinds have no live interactible feed; completion / codex gates them.
_STATIC_GATHER_KINDS = frozenset({"red_orb"})
_SIZED_GATHER_KINDS = frozenset({"plant", "ore", "gatherable"})
_TYPED_GATHER_KINDS = frozenset({"plant", "ore", "chest", "critter"})

GATHER_SIZES = (
    ("", "Any size"),
    ("small", "Small"),
    ("medium", "Medium"),
    ("large", "Large"),
)

GATHER_COLLECTED = (
    ("yes", "Yes"),
    ("no", "No"),
)

# Default handoff radius when a spawn does not author roaming_range.
_CRITTER_SPAWN_HANDOFF_M = 60.0

# Family key → NODE GUIDE type label (Goat kinds read as "Ram" in game copy).
_CRITTER_FAMILY_LABELS = {
    "demondog": "Demon Dog",
    "frog": "Frog",
    "goat": "Ram",
    "ladybug": "Ladybug",
    "lizard": "Lizard",
    "rabbit": "Rabbit",
    "sheep": "Sheep",
    "squirrel": "Squirrel",
    "stinkbug": "Stink Bug",
    "turtle": "Turtle",
}

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
_ACTIVITY_CHEST_TYPES = frozenset(
    {"orbchest", "chestorb", "campchest", "vaultchest", "fightstone"}
)

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


def _owned_companion_ids(state: dict[str, Any] | None) -> set[str]:
    """Companion / Critter ids already unlocked (codex collection.pets).

    Matches ``codex-browse`` owned_collection_ids: accept both bare unit kinds
    and ``Critter_``-prefixed forms from the bridge payload.
    """
    if not isinstance(state, dict):
        return set()
    collection = state.get("collection")
    if not isinstance(collection, dict):
        return set()
    raw = collection.get("pets") or []
    owned: set[str] = set()
    if not isinstance(raw, list):
        return owned
    for value in raw:
        text = str(value).strip()
        if not text:
            continue
        owned.add(text)
        if text.startswith("Critter_"):
            owned.add(text.removeprefix("Critter_"))
        else:
            owned.add(f"Critter_{text}")
    return owned


def _critter_unit_owned(unit_kind: str, owned: set[str]) -> bool:
    text = str(unit_kind or "").strip()
    if not text or not owned:
        return False
    if text in owned:
        return True
    if text.startswith("Critter_"):
        return text.removeprefix("Critter_") in owned
    return f"Critter_{text}" in owned


def _critter_family_key(unit_kind: str) -> str:
    """Species family from a unit id (Sheep_Beige → sheep, Goat_* → goat)."""
    text = str(unit_kind or "").strip()
    if text.startswith("Critter_"):
        text = text.removeprefix("Critter_")
    if not text:
        return ""
    head = text.replace("-", "_").split("_", 1)[0]
    return head.lower()


def _critter_family_label(family: str) -> str:
    key = str(family or "").strip().lower()
    if not key:
        return "Unknown"
    return _CRITTER_FAMILY_LABELS.get(key, key.title())


def _spawn_kinds(spawn: dict[str, Any]) -> list[str]:
    raw = spawn.get("kinds")
    if isinstance(raw, list) and raw:
        return [str(item).strip() for item in raw if str(item).strip()]
    unit = str(spawn.get("unit") or "").strip()
    return [unit] if unit else []


def _spawn_key(spawn: dict[str, Any]) -> str:
    x = safe_float(spawn.get("x"), math.nan)
    y = safe_float(spawn.get("y"), math.nan)
    tile = str(spawn.get("source_tile") or "").strip()
    if tile:
        return f"critter-spawn:{tile}:{x:.1f}:{y:.1f}"
    return f"critter-spawn:{x:.1f}:{y:.1f}"


def _spawn_handoff_m(spawn: dict[str, Any]) -> float:
    radius = safe_float(spawn.get("roaming_range"), math.nan)
    if math.isfinite(radius) and radius > 0:
        return float(radius)
    return _CRITTER_SPAWN_HANDOFF_M


def _spawn_matches_family(spawn: dict[str, Any], family: str) -> bool:
    wanted = str(family or "").strip().lower()
    if not wanted:
        return True
    for kind in _spawn_kinds(spawn):
        if _critter_family_key(kind) == wanted:
            return True
    return False


def _spawn_has_unowned_kind(spawn: dict[str, Any], owned: set[str]) -> bool:
    """True when ownership is unknown or any pool kind is still uncollected."""
    if not owned:
        return True
    kinds = _spawn_kinds(spawn)
    if not kinds:
        return True
    return any(not _critter_unit_owned(kind, owned) for kind in kinds)


def _discover_critter_types() -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    for spawn in critter_spawns():
        for kind in _spawn_kinds(spawn):
            family = _critter_family_key(kind)
            if not family:
                continue
            found.setdefault(family, _critter_family_label(family))
    return sorted(found.items(), key=lambda pair: pair[1].lower())


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
    critter = _CRITTER_FAMILY_LABELS.get(key)
    if critter:
        return critter
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


def _gatherable_completed(item: dict[str, Any], completed: set[str]) -> bool:
    """True when a chest / red orb is already done for this character."""
    if not completed:
        return False
    for key in ("id", "name", "source"):
        value = str(item.get(key) or "").strip()
        if not value:
            continue
        if key == "source":
            value = value.replace("\\", "/").rsplit("/", 1)[-1]
            if value.lower().endswith(".prefab"):
                value = value[: -len(".prefab")]
        if _element_completed(value, completed):
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
        self._full_height_hint = 0

        root = QtWidgets.QVBoxLayout(self)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        if self._compact:
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(3)
        else:
            root.setContentsMargins(0, 8, 0, 0)
            root.setSpacing(8)

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

        self.collected_label = QtWidgets.QLabel("COLLECTED")
        self.collected_label.setObjectName(
            "gatherNavFieldLabel" if self._compact else "waypointColumnHeader"
        )
        root.addWidget(self.collected_label)
        self.collected_combo = QtWidgets.QComboBox()
        self.collected_combo.setObjectName("gatherNavCombo")
        for value, label in GATHER_COLLECTED:
            self.collected_combo.addItem(label, value)
        yes_index = self.collected_combo.findData("yes")
        if yes_index >= 0:
            self.collected_combo.setCurrentIndex(yes_index)
        root.addWidget(self.collected_combo)

        # Spare height sits between filters and status so Idle+actions pin bottom.
        root.addStretch(1)

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

        # Keep filters from stretching; spare height stays above status/actions.
        _fixed_v = QtWidgets.QSizePolicy.Policy.Fixed
        _pref_v = QtWidgets.QSizePolicy.Policy.Preferred
        for widget in (
            kind_label,
            self.kind_combo,
            self.type_label,
            self.type_combo,
            self.size_label,
            self.size_combo,
            self.collected_label,
            self.collected_combo,
            self.enable_button,
            self.skip_button,
        ):
            policy = widget.sizePolicy()
            policy.setVerticalPolicy(_fixed_v)
            widget.setSizePolicy(policy)
        status_policy = self.status_frame.sizePolicy()
        status_policy.setVerticalPolicy(_pref_v)
        status_policy.setVerticalStretch(0)
        self.status_frame.setSizePolicy(status_policy)

        self.enable_button.toggled.connect(self._on_enabled_toggled)
        self.skip_button.clicked.connect(self.skipRequested.emit)
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        self.type_combo.currentIndexChanged.connect(self._on_filters_changed)
        self.size_combo.currentIndexChanged.connect(self._on_filters_changed)
        self.collected_combo.currentIndexChanged.connect(self._on_filters_changed)
        self._type_options: list[tuple[str, str]] = []
        # Tallest real layout is TYPE+SIZE (plant/ore) or TYPE+COLLECTED
        # (critters) — never all three at once.
        self._full_height_hint = self._measure_stable_height()
        self._sync_filter_visibility()

    def _measure_stable_height(self) -> int:
        """Sidebar height for the tallest TARGET layout (no unused filter row)."""
        root = self.layout()
        optional = (
            self.type_label,
            self.type_combo,
            self.size_label,
            self.size_combo,
            self.collected_label,
            self.collected_combo,
        )
        configs = (
            # plant / ore: TYPE + SIZE
            (True, True, True, True, False, False),
            # chest / critter: TYPE + COLLECTED (critter) or TYPE only (chest)
            (True, True, False, False, True, True),
        )
        tallest = 0
        for visible in configs:
            for widget, show in zip(optional, visible):
                widget.setVisible(show)
            if root is not None:
                root.activate()
            tallest = max(tallest, max(0, self.sizeHint().height()))
        return tallest

    def full_content_height(self) -> int:
        """Stable height for the sidebar (tallest real filter stack)."""
        natural = max(0, self.sizeHint().height())
        return max(natural, int(self._full_height_hint or 0))

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
        collected = kind == "critter"
        self.collected_label.setVisible(collected)
        self.collected_combo.setVisible(collected)
        self.collected_combo.setEnabled(collected)

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

    def collected(self) -> str:
        if self.kind() != "critter":
            return "yes"
        value = str(self.collected_combo.currentData() or "yes").strip().lower()
        return value if value in {"yes", "no"} else "yes"

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

    def set_collected(self, collected: str) -> None:
        value = str(collected or "yes").strip().lower()
        if value not in {"yes", "no"}:
            value = "yes"
        index = self.collected_combo.findData(value)
        if index >= 0:
            self.collected_combo.blockSignals(True)
            self.collected_combo.setCurrentIndex(index)
            self.collected_combo.blockSignals(False)

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
    # Critter spawns may stream late; wait longer before skipping an empty pool.
    CRITTER_SPAWN_EMPTY_GRACE_S = 4.0

    def _init_gather_nav_state(self) -> None:
        self.gather_nav_enabled = False
        self.gather_nav_kind = "plant"
        self.gather_nav_type = ""
        self.gather_nav_size = "large"
        self.gather_nav_collected = "yes"
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
        if kind == "critter":
            options = _discover_critter_types()
            selected = self.gather_nav_type
            panel.set_type_options(options, selected=selected)
            self.gather_nav_type = panel.node_type()
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
        panel.set_collected(self.gather_nav_collected)
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
            if hasattr(self, "_stop_gather_sidebar_idle_timer_only"):
                self._stop_gather_sidebar_idle_timer_only()
            notify(self, "NODE GUIDE started")
            self._gather_nav_retarget(force=True)
        else:
            self._clear_gather_nav_target()
            notify(self, "NODE GUIDE stopped")
            self._refresh_gather_nav_panel()
            if hasattr(self, "_bump_gather_sidebar_idle"):
                self._bump_gather_sidebar_idle()

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
        self.gather_nav_collected = panel.collected()
        self._settings.setValue("map/gather_nav_kind", self.gather_nav_kind)
        self._settings.setValue("map/gather_nav_type", self.gather_nav_type)
        self._settings.setValue("map/gather_nav_size", self.gather_nav_size)
        self._settings.setValue(
            "map/gather_nav_collected", self.gather_nav_collected
        )
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
        if kind == "critter":
            button = getattr(self, "critters_filter", None)
        else:
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
        if hasattr(self, "_bump_gather_sidebar_idle"):
            self._bump_gather_sidebar_idle()

    def _gather_nav_tick(self, snapshot: Any = None) -> None:
        if not self.gather_nav_enabled:
            self._refresh_gather_nav_panel()
            return
        self._revive_depleted_from_live(snapshot)
        if self._gather_target_collected(snapshot):
            target = self.gather_nav_target
            forced_critter = self._is_forced_critter_target(target)
            if not forced_critter:
                self._mark_gather_depleted(self.gather_nav_target, snapshot)
            self._clear_gather_nav_target()
            if forced_critter:
                self._stop_forced_critter_nav()
                return
            self._gather_nav_retarget(force=True, snapshot=snapshot)
            return
        if self.gather_nav_target is None:
            self._gather_nav_retarget(force=False, snapshot=snapshot)
            return
        self._sync_gather_target_live(snapshot)
        self._push_gather_target_to_radar()
        self._refresh_gather_nav_panel()

    @staticmethod
    def _is_forced_critter_target(target: dict[str, Any] | None) -> bool:
        if not isinstance(target, dict):
            return False
        kind = str(target.get("kind") or "").strip().lower()
        return bool(target.get("forced")) and kind == "critter"

    def _stop_forced_critter_nav(self) -> None:
        """Disable NODE GUIDE after a force-pinned critter is collected."""
        self.gather_nav_enabled = False
        self._clear_gather_nav_target()
        panel = self._gather_nav_panel()
        if panel is not None:
            panel.set_enabled_checked(False)
        self._refresh_gather_nav_panel()
        if hasattr(self, "_bump_gather_sidebar_idle"):
            self._bump_gather_sidebar_idle()

    def force_navigate_to_critter(self, critter: dict[str, Any]) -> None:
        """Open NODE GUIDE and pin a specific live wild critter."""
        if not isinstance(critter, dict):
            return
        live_id = str(critter.get("id") or "").strip()
        if not live_id:
            return
        x = safe_float(critter.get("x"), math.nan)
        y = safe_float(critter.get("y"), math.nan)
        z = safe_float(critter.get("z"), 0.0)
        if not (math.isfinite(x) and math.isfinite(y)):
            return

        # Destination is exclusive with custom waypoint routing.
        if getattr(self, "active_custom_waypoint_id", None) is not None:
            self._set_active_custom_waypoint(None)

        self.gather_nav_enabled = True
        self.gather_nav_kind = "critter"
        if hasattr(self, "_stop_gather_sidebar_idle_timer_only"):
            self._stop_gather_sidebar_idle_timer_only()
        self._gather_missing_since = None
        self._gather_missing_key = None
        if hasattr(self, "_set_gather_sidebar_collapsed"):
            self._set_gather_sidebar_collapsed(False)
        self._ensure_gather_loot_filter_visible()
        panel = self._gather_nav_panel()
        if panel is not None:
            panel.set_kind("critter")
            self._refresh_gather_type_options()
            panel.set_collected(self.gather_nav_collected)
            panel.set_enabled_checked(True)
            self._settings.setValue("map/gather_nav_kind", "critter")

        unit_kind = str(critter.get("kind") or "").strip()
        name = (
            format_unit_tooltip_name(unit_kind) if unit_kind else "Critter"
        )
        player = self._gather_player_position()
        distance = (
            math.hypot(
                x - safe_float(player.get("x")),
                y - safe_float(player.get("y")),
            )
            if player is not None
            else math.nan
        )
        self.gather_nav_target = {
            "key": f"critter:{live_id}",
            "kind": "critter",
            "name": name,
            "x": x,
            "y": y,
            "z": z,
            "poi_id": None,
            "live_id": live_id,
            "distance": distance,
            "source": "live",
            "forced": True,
            "size": "",
            "family": _critter_family_key(unit_kind),
            "unit_kind": unit_kind,
        }
        self._push_gather_target_to_radar()
        self._refresh_gather_nav_panel()
        notify(self, f"Navigating to {name}", kind="info")

    def _gather_critters(self, snapshot: Any = None) -> list[dict[str, Any]]:
        state = self._gather_snapshot_state(snapshot)
        nodes = state.get("critters", [])
        if not isinstance(nodes, list):
            return []
        return [item for item in nodes if isinstance(item, dict)]

    def _gather_critter_candidates(
        self,
        player: dict[str, float],
        snapshot: Any = None,
    ) -> list[dict[str, Any]]:
        """Nearest matching critter spawn points for NODE GUIDE.

        Navigate to authored spawn positions first. When the player reaches the
        spawn's roaming range, ``_sync_gather_target_live`` hands off to the
        live wild critter. COLLECTED=No keeps shared spawn pools that still
        have at least one unowned kind.
        """
        px = safe_float(player.get("x"), math.nan)
        py = safe_float(player.get("y"), math.nan)
        if not (math.isfinite(px) and math.isfinite(py)):
            return []
        owned = _owned_companion_ids(self._gather_snapshot_state(snapshot))
        type_filter = str(self.gather_nav_type or "").strip().lower()
        include_collected = str(self.gather_nav_collected or "yes").strip().lower() != "no"
        candidates: list[dict[str, Any]] = []
        for spawn in critter_spawns():
            if not _spawn_matches_family(spawn, type_filter):
                continue
            if not include_collected and not _spawn_has_unowned_kind(spawn, owned):
                continue
            key = _spawn_key(spawn)
            if key in self.gather_nav_skipped or key in self.gather_nav_depleted:
                continue
            x = safe_float(spawn.get("x"), math.nan)
            y = safe_float(spawn.get("y"), math.nan)
            z = safe_float(spawn.get("z"), 0.0)
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            if self._is_gather_position_depleted(x, y):
                continue
            kinds = _spawn_kinds(spawn)
            family = ""
            if type_filter:
                family = type_filter
            elif kinds:
                family = _critter_family_key(kinds[0])
            label = _critter_family_label(family) if family else "Critter"
            if bool(spawn.get("spark")) and "spark" not in label.lower():
                label = f"Sparkling {label}"
            handoff_m = _spawn_handoff_m(spawn)
            distance = math.hypot(x - px, y - py)
            candidates.append(
                {
                    "key": key,
                    "kind": "critter",
                    "name": f"{label} spawn",
                    "size": "",
                    "x": x,
                    "y": y,
                    "z": z,
                    "poi_id": None,
                    "live_id": None,
                    "distance": distance,
                    "source": "spawn",
                    "spawn_key": key,
                    "spawn_x": x,
                    "spawn_y": y,
                    "handoff_m": handoff_m,
                    "family": family,
                    "pool_kinds": kinds,
                    "spark": bool(spawn.get("spark")),
                }
            )
        candidates.sort(
            key=lambda item: (
                safe_float(item.get("distance"), math.inf),
                0 if item.get("spark") else 1,
                str(item.get("name") or ""),
            )
        )
        return candidates

    def _critter_live_matches_filters(
        self,
        live: dict[str, Any],
        *,
        owned: set[str],
        family: str = "",
    ) -> bool:
        unit_kind = str(live.get("kind") or "").strip()
        if not unit_kind:
            return False
        type_filter = str(family or self.gather_nav_type or "").strip().lower()
        if type_filter and _critter_family_key(unit_kind) != type_filter:
            return False
        include_collected = (
            str(self.gather_nav_collected or "yes").strip().lower() != "no"
        )
        if not include_collected and _critter_unit_owned(unit_kind, owned):
            return False
        return True

    def _attach_live_critter_to_target(
        self,
        target: dict[str, Any],
        live: dict[str, Any],
        player: dict[str, float],
    ) -> None:
        live_id = str(live.get("id") or "").strip()
        unit_kind = str(live.get("kind") or "").strip()
        x = safe_float(live.get("x"), target.get("x"))
        y = safe_float(live.get("y"), target.get("y"))
        z = safe_float(live.get("z"), target.get("z"))
        name = format_unit_tooltip_name(unit_kind) if unit_kind else "Critter"
        if bool(live.get("spark")) and "spark" not in name.lower():
            name = f"Sparkling {name}"
        spawn_key = str(target.get("spawn_key") or target.get("key") or "")
        target.update(
            {
                "key": f"critter:{live_id}" if live_id else target.get("key"),
                "live_id": live_id or None,
                "x": x,
                "y": y,
                "z": z,
                "name": name,
                "source": "live",
                "unit_kind": unit_kind,
                "spawn_key": spawn_key or None,
                "distance": math.hypot(
                    x - safe_float(player.get("x")),
                    y - safe_float(player.get("y")),
                ),
            }
        )
        self._gather_missing_since = None
        self._gather_missing_key = None

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
        spawn_key = str(target.get("spawn_key") or "")
        if spawn_key:
            self.gather_nav_depleted.add(spawn_key)
        live_id = str(target.get("live_id") or "")
        if live_id:
            self.gather_nav_depleted.add(f"live:{live_id}")
        # Prefer authored spawn coords so the next retarget skips this pool.
        tx = safe_float(target.get("spawn_x"), math.nan)
        ty = safe_float(target.get("spawn_y"), math.nan)
        if not (math.isfinite(tx) and math.isfinite(ty)):
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
        revived_keys: set[str] = set()
        for poi in self._gather_pois(snapshot):
            key = _static_key(poi)
            if key not in self.gather_nav_depleted and not self._is_gather_position_depleted(
                safe_float(poi.get("x"), math.nan),
                safe_float(poi.get("y"), math.nan),
            ):
                continue
            if not all_live or self._live_covers(poi, all_live) is None:
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
        # Revive live-id marks that are present again (loot + wild critters).
        live_ids = {
            str(item.get("id") or "")
            for item in all_live
            if str(item.get("id") or "")
        }
        for critter in self._gather_critters(snapshot):
            critter_id = str(critter.get("id") or "").strip()
            if not critter_id:
                continue
            live_ids.add(critter_id)
            cx = safe_float(critter.get("x"), math.nan)
            cy = safe_float(critter.get("y"), math.nan)
            if math.isfinite(cx) and math.isfinite(cy):
                self.gather_nav_depleted_positions = [
                    (dx, dy)
                    for dx, dy in self.gather_nav_depleted_positions
                    if math.hypot(cx - dx, cy - dy) > self.LIVE_MATCH_M
                ]
        self.gather_nav_depleted = {
            key
            for key in self.gather_nav_depleted
            if not (
                (
                    key.startswith("live:")
                    and key.removeprefix("live:") in live_ids
                )
                or (
                    key.startswith("critter:")
                    and key.removeprefix("critter:") in live_ids
                )
            )
        }

    def _gather_candidates(
        self,
        player: dict[str, float],
        snapshot: Any = None,
    ) -> list[dict[str, Any]]:
        if self.gather_nav_kind == "critter":
            return self._gather_critter_candidates(player, snapshot)

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
            if kind not in {"plant", "ore", "chest", "gatherable", "red_orb"}:
                continue
            if not self._matches_gather_filters(poi):
                continue
            poi_id = str(poi.get("id") or "").strip()
            if kind in {"red_orb", "chest"} and _gatherable_completed(poi, completed):
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
                # Opened world/recipe chests stay in the live feed; skip completed.
                if str(live.get("kind") or "").strip().lower() == "chest" and (
                    _gatherable_completed(live, completed)
                ):
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
                "critter": "critter",
            }.get(self.gather_nav_kind, self.gather_nav_kind)
            type_note = ""
            if self.gather_nav_type:
                type_note = f" {_pretty_type_label(self.gather_nav_type)}"
            detail = (
                (
                    "No uncollected red orbs found for this character "
                    "(completed ones stay muted on the map)."
                    if self.gather_nav_kind == "red_orb"
                    else (
                        "No uncollected chests found for this character "
                        "(opened ones stay muted on the map)."
                        if self.gather_nav_kind == "chest"
                        else (
                            (
                                f"No matching{type_note} critter spawn points found."
                                if self.gather_nav_type
                                else "No matching critter spawn points found."
                            )
                            if self.gather_nav_kind == "critter"
                            else f"No matching{type_note} {label}{size_note} nodes found."
                        )
                    )
                )
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
        if kind == "critter" or self._is_forced_critter_target(target):
            live_id = str(target.get("live_id") or "")
            if live_id:
                for live in self._gather_critters(snapshot):
                    if str(live.get("id") or "") != live_id:
                        continue
                    target["x"] = safe_float(live.get("x"), target.get("x"))
                    target["y"] = safe_float(live.get("y"), target.get("y"))
                    target["z"] = safe_float(live.get("z"), target.get("z"))
                    unit_kind = str(live.get("kind") or "")
                    if unit_kind:
                        name = format_unit_tooltip_name(unit_kind)
                        if bool(live.get("spark")) and "spark" not in name.lower():
                            name = f"Sparkling {name}"
                        target["name"] = name
                    target["distance"] = math.hypot(
                        safe_float(target.get("x")) - safe_float(player.get("x")),
                        safe_float(target.get("y")) - safe_float(player.get("y")),
                    )
                    target["source"] = "live"
                    self._gather_missing_since = None
                    self._gather_missing_key = None
                    return
                # Live id missing — collected detection owns advance.
                target["distance"] = math.hypot(
                    safe_float(target.get("x")) - safe_float(player.get("x")),
                    safe_float(target.get("y")) - safe_float(player.get("y")),
                )
                return

            # Spawn target: stay locked on the spawn until the player arrives,
            # then hand off to a matching live critter near that spawn.
            spawn_x = safe_float(target.get("spawn_x"), target.get("x"))
            spawn_y = safe_float(target.get("spawn_y"), target.get("y"))
            handoff_m = safe_float(target.get("handoff_m"), _CRITTER_SPAWN_HANDOFF_M)
            if not math.isfinite(handoff_m) or handoff_m <= 0:
                handoff_m = _CRITTER_SPAWN_HANDOFF_M
            player_to_spawn = math.hypot(
                spawn_x - safe_float(player.get("x")),
                spawn_y - safe_float(player.get("y")),
            )
            target["distance"] = player_to_spawn
            target["x"] = spawn_x
            target["y"] = spawn_y
            if player_to_spawn > handoff_m:
                self._gather_missing_since = None
                self._gather_missing_key = None
                return

            owned = _owned_companion_ids(self._gather_snapshot_state(snapshot))
            family = str(target.get("family") or self.gather_nav_type or "")
            best: dict[str, Any] | None = None
            best_dist = handoff_m
            for live in self._gather_critters(snapshot):
                if not self._critter_live_matches_filters(
                    live, owned=owned, family=family
                ):
                    continue
                lx = safe_float(live.get("x"), math.nan)
                ly = safe_float(live.get("y"), math.nan)
                if not (math.isfinite(lx) and math.isfinite(ly)):
                    continue
                dist = math.hypot(lx - spawn_x, ly - spawn_y)
                if dist > best_dist:
                    continue
                best = live
                best_dist = dist
            if best is not None:
                self._attach_live_critter_to_target(target, best, player)
                return

            # Arrived at spawn but no matching live yet — deplete after grace.
            key = str(target.get("key") or "")
            now = time.monotonic()
            if self._gather_missing_key != key:
                self._gather_missing_key = key
                self._gather_missing_since = now
            elif (
                self._gather_missing_since is not None
                and now - self._gather_missing_since
                >= self.CRITTER_SPAWN_EMPTY_GRACE_S
            ):
                self._mark_gather_depleted(target, snapshot)
                self._clear_gather_nav_target()
                self._gather_nav_retarget(force=True, snapshot=snapshot)
            return
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
        if kind == "critter" or self._is_forced_critter_target(target):
            live_id = str(target.get("live_id") or "")
            if not live_id:
                return False
            for live in self._gather_critters(snapshot):
                if str(live.get("id") or "") == live_id:
                    self._gather_missing_since = None
                    self._gather_missing_key = None
                    return False
            key = f"critter-gone:{live_id}"
            now = time.monotonic()
            if self._gather_missing_key != key:
                self._gather_missing_key = key
                self._gather_missing_since = now
                return False
            return (
                self._gather_missing_since is not None
                and now - self._gather_missing_since >= self.DEPLETED_GRACE_S
            )
        if kind == "red_orb":
            completed = _completion_ids(self._gather_snapshot_state(snapshot))
            return _gatherable_completed(
                {
                    "id": str(target.get("poi_id") or ""),
                    "name": str(target.get("name") or ""),
                },
                completed,
            )
        if kind == "chest":
            completed = _completion_ids(self._gather_snapshot_state(snapshot))
            if _gatherable_completed(
                {
                    "id": str(target.get("poi_id") or ""),
                    "name": str(target.get("name") or ""),
                },
                completed,
            ):
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
