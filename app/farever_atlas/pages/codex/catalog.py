"""Static Codex / Collection catalog loaded from assets."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ...config import ASSET_ROOT, discover_project_asset


COLLECTION_CATEGORIES = (
    ("mounts", "Mount"),
    ("gliders", "Glider"),
    ("companions", "Companions"),
    ("appearances", "Appearance"),
)

CODEX_SUBCATEGORIES = (
    ("monsters", "Monsters"),
    ("activities", "Activities"),
    ("dungeons", "Dungeons"),
)

# Matches in-game filter chip order (Skover) then remaining types.
UNIT_TYPE_FILTER_ORDER = (
    "Crab",
    "Bee",
    "Kobold",
    "Slime",
    "Manfish",
    "Skunk",
    "Golem",
    "WaterGolems",
    "FireGolems",
    "WindGolems",
    "Demon",
    "Boar",
    "Crimson",
    "Wolf",
    "Coyote",
    "Sprouts",
    "Spirit",
    "Ogre",
    "Swarowl",
)

CODEX_STATUS_FILTERS = (
    ("unknown", "Unknown"),
    ("discovered", "Discovered"),
    ("completed", "Completed"),
    ("mastered", "Mastered"),
)

_ARMOR_PREFIXES = (
    "Head_",
    "Shoulders_",
    "Back_",
    "Chest_",
    "Hands_",
    "Waist_",
    "Legs_",
    "Feet_",
)


@lru_cache(maxsize=1)
def load_codex_catalog() -> dict[str, Any]:
    path = discover_project_asset("codex_catalog.json")
    if path is None:
        path = ASSET_ROOT / "codex_catalog.json"
    if not path.is_file():
        return {
            "schema": 1,
            "thresholds": {
                "elite": [1, 1, 1],
                "big": [1, 4, 10],
                "foe": [1, 8, 20],
            },
            "unit_sets": {"elite": [], "big": [], "unique": [], "no_codex": []},
            "collection": {
                "mounts": [],
                "gliders": [],
                "companions": [],
                "appearances": [],
            },
            "regions": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def _display_names() -> dict[str, Any]:
    path = discover_project_asset("display_names.json")
    if path is None:
        path = ASSET_ROOT / "display_names.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def load_unit_types() -> dict[str, Any]:
    path = discover_project_asset("unit_types.json")
    if path is None:
        path = ASSET_ROOT / "unit_types.json"
    if not path.is_file():
        return {"labels": {}, "units": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"labels": {}, "units": {}}


@lru_cache(maxsize=1)
def load_unit_portraits() -> dict[str, str]:
    path = discover_project_asset("unit_portraits.json")
    if path is None:
        path = ASSET_ROOT / "unit_portraits.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    portraits = payload.get("portraits")
    if not isinstance(portraits, dict):
        return {}
    return {
        str(entry_id): str(rel)
        for entry_id, rel in portraits.items()
        if str(entry_id) and str(rel)
    }


def portrait_path_for(entry_id: str) -> Path | None:
    portraits = load_unit_portraits()
    rel = portraits.get(entry_id)
    if not rel and not entry_id.startswith("Critter_"):
        rel = portraits.get(f"Critter_{entry_id}")
    if not rel and entry_id.startswith("Critter_"):
        rel = portraits.get(entry_id.removeprefix("Critter_"))
    if not rel:
        return None
    path = ASSET_ROOT / "portraits" / rel
    return path if path.is_file() else None


def unit_type_id(unit_id: str) -> str:
    data = load_unit_types()
    units = data.get("units") if isinstance(data.get("units"), dict) else {}
    value = units.get(unit_id)
    return str(value) if value else ""


def unit_type_label(type_id: str) -> str:
    if not type_id:
        return ""
    data = load_unit_types()
    labels = data.get("labels") if isinstance(data.get("labels"), dict) else {}
    return str(labels.get(type_id) or type_id)


def ordered_type_ids(type_ids: set[str] | list[str]) -> list[str]:
    present = {str(value) for value in type_ids if str(value)}
    ordered = [type_id for type_id in UNIT_TYPE_FILTER_ORDER if type_id in present]
    extras = sorted(present.difference(ordered), key=lambda tid: unit_type_label(tid).lower())
    return ordered + extras


def display_name_for(entry_id: str, *, kind: str = "auto") -> str:
    names = _display_names()
    units = names.get("units") if isinstance(names.get("units"), dict) else {}
    items = names.get("items") if isinstance(names.get("items"), dict) else {}
    if kind in ("monster", "auto") and entry_id in units:
        entry = units[entry_id]
        if isinstance(entry, dict) and entry.get("name"):
            return str(entry["name"])
    if kind in ("item", "collection", "auto") and entry_id in items:
        entry = items[entry_id]
        if isinstance(entry, dict) and entry.get("name"):
            return str(entry["name"])
        if isinstance(entry, str) and entry.strip():
            return entry
    # Critter ids in collection may omit the Critter_ prefix.
    if not entry_id.startswith("Critter_"):
        critter_id = f"Critter_{entry_id}"
        if critter_id in items:
            entry = items[critter_id]
            if isinstance(entry, dict) and entry.get("name"):
                return str(entry["name"])
    # Humanize activity / dungeon prefab ids when no nicer label exists.
    if "_" in entry_id and entry_id[:1].isupper():
        return entry_id.replace("_", " ")
    return entry_id


def unit_threshold_set(unit_id: str, catalog: dict[str, Any] | None = None) -> str:
    data = catalog or load_codex_catalog()
    sets = data.get("unit_sets") if isinstance(data.get("unit_sets"), dict) else {}
    elite = set(sets.get("elite") or [])
    unique = set(sets.get("unique") or [])
    big = set(sets.get("big") or [])
    # Unique / sparkling named variants use the same 1-kill track as elites.
    if unit_id in elite or unit_id in unique:
        return "elite"
    if unit_id in big:
        return "big"
    return "foe"


def unit_thresholds(unit_id: str, catalog: dict[str, Any] | None = None) -> list[int]:
    data = catalog or load_codex_catalog()
    thresholds = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
    key = unit_threshold_set(unit_id, data)
    raw = thresholds.get(key) or thresholds.get("foe") or [1, 8, 20]
    values = [int(value) for value in raw if int(value) > 0]
    return values or [1, 8, 20]


def unit_kill_max(unit_id: str, catalog: dict[str, Any] | None = None) -> int:
    return max(unit_thresholds(unit_id, catalog))


def unit_next_threshold(
    unit_id: str,
    kills: int,
    catalog: dict[str, Any] | None = None,
) -> int:
    """Next unreached milestone (matches in-game tile overlays like 6/8)."""
    thresholds = unit_thresholds(unit_id, catalog)
    for value in thresholds:
        if kills < value:
            return value
    return max(thresholds)


def unit_tile_progress(
    unit_id: str,
    kills: int,
    rank: int,
    catalog: dict[str, Any] | None = None,
) -> tuple[str, bool, bool]:
    """Return (overlay_text, complete, revealed) for a monster tile."""
    complete = is_monster_complete(unit_id, kills, rank, catalog)
    revealed = complete or kills > 0 or rank > 0
    if complete:
        return "", True, True
    if not revealed:
        return "", False, False
    next_threshold = unit_next_threshold(unit_id, kills, catalog)
    return f"{kills}/{next_threshold}", False, True


def collection_ids(category: str, catalog: dict[str, Any] | None = None) -> list[str]:
    data = catalog or load_codex_catalog()
    collection = data.get("collection") if isinstance(data.get("collection"), dict) else {}
    raw = collection.get(category) or []
    return [str(value) for value in raw if str(value)]


def regions(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = catalog or load_codex_catalog()
    raw = data.get("regions") or []
    return [entry for entry in raw if isinstance(entry, dict) and entry.get("id")]


def region_entry_ids(
    region_id: str,
    subcategory: str,
    catalog: dict[str, Any] | None = None,
) -> list[str]:
    for region in regions(catalog):
        if str(region.get("id")) != region_id:
            continue
        raw = region.get(subcategory) or []
        return [str(value) for value in raw if str(value)]
    return []


def owned_collection_ids(snapshot_state: dict[str, Any] | None, category: str) -> set[str]:
    if not isinstance(snapshot_state, dict):
        return set()
    collection = snapshot_state.get("collection")
    if not isinstance(collection, dict):
        return set()
    bridge_key = {
        "mounts": "mounts",
        "gliders": "gliders",
        "companions": "pets",
        "appearances": "gears",
    }.get(category, category)
    raw = collection.get(bridge_key) or []
    owned: set[str] = set()
    if isinstance(raw, list):
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


def codex_unit_progress(
    snapshot_state: dict[str, Any] | None,
    unit_id: str,
) -> tuple[int, int]:
    """Return (kills, rank) for a unit id."""
    if not isinstance(snapshot_state, dict):
        return 0, 0
    units = snapshot_state.get("codex_units")
    if not isinstance(units, dict):
        return 0, 0
    entry = units.get(unit_id)
    if not isinstance(entry, dict):
        return 0, 0
    try:
        kills = int(entry.get("kills") or 0)
    except (TypeError, ValueError):
        kills = 0
    try:
        rank = int(entry.get("rank") or 0)
    except (TypeError, ValueError):
        rank = 0
    return max(0, kills), max(0, rank)


def completed_activity_ids(snapshot_state: dict[str, Any] | None) -> set[str]:
    if not isinstance(snapshot_state, dict):
        return set()
    raw = snapshot_state.get("completed_activities") or []
    if not isinstance(raw, list):
        return set()
    return {str(value) for value in raw if str(value)}


def is_monster_complete(
    unit_id: str,
    kills: int,
    rank: int,
    catalog: dict[str, Any] | None = None,
) -> bool:
    thresholds = unit_thresholds(unit_id, catalog)
    if rank >= len(thresholds):
        return True
    return kills >= max(thresholds)


def unit_codex_status(
    unit_id: str,
    kills: int,
    rank: int,
    catalog: dict[str, Any] | None = None,
) -> str:
    """Map live progress to in-game status filter chips."""
    if is_monster_complete(unit_id, kills, rank, catalog):
        return "mastered"
    if rank <= 0 and kills <= 0:
        return "unknown"
    thresholds = unit_thresholds(unit_id, catalog)
    # CodexCompleted is the intermediate rank-up (2nd threshold), not mastery.
    if rank >= 2 or (len(thresholds) >= 2 and kills >= thresholds[1]):
        return "completed"
    return "discovered"


def looks_like_appearance_id(entry_id: str) -> bool:
    return entry_id.startswith(_ARMOR_PREFIXES)
