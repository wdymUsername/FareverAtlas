"""Static Codex / Collection catalog loaded from assets."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ...config import (
    ASSET_ROOT,
    DISPLAY_NAMES_RELATIVE_PATH,
    discover_project_asset,
)


COLLECTION_CATEGORIES = (
    ("mounts", "Mount"),
    ("gliders", "Glider"),
    ("companions", "Companions"),
    ("appearances", "Appearance"),
)

CODEX_SUBCATEGORIES = (
    ("monsters", "Monsters"),
    ("activities", "Activities"),
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
    path = discover_project_asset(DISPLAY_NAMES_RELATIVE_PATH)
    if path is None:
        path = ASSET_ROOT / DISPLAY_NAMES_RELATIVE_PATH
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


@lru_cache(maxsize=1)
def _dungeon_portraits_payload() -> dict[str, Any]:
    path = discover_project_asset("dungeon_portraits.json")
    if path is None:
        path = ASSET_ROOT / "dungeon_portraits.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def load_dungeon_portraits() -> dict[str, str]:
    portraits = _dungeon_portraits_payload().get("portraits")
    if not isinstance(portraits, dict):
        return {}
    return {
        str(entry_id): str(rel)
        for entry_id, rel in portraits.items()
        if str(entry_id) and str(rel)
    }


@lru_cache(maxsize=1)
def load_dungeon_headers() -> dict[str, str]:
    headers = _dungeon_portraits_payload().get("headers")
    if not isinstance(headers, dict):
        return {}
    return {
        str(entry_id): str(rel)
        for entry_id, rel in headers.items()
        if str(entry_id) and str(rel)
    }


@lru_cache(maxsize=1)
def load_codex_drops() -> dict[str, Any]:
    path = discover_project_asset("codex_drops.json")
    if path is None:
        path = ASSET_ROOT / "codex_drops.json"
    if not path.is_file():
        return {"entries": {}, "items": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"entries": {}, "items": {}}
    entries = payload.get("entries") if isinstance(payload.get("entries"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), dict) else {}
    return {"entries": entries, "items": items}


def _normalize_drop_row(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, str) and entry:
        return {"id": entry}
    if not isinstance(entry, dict):
        return None
    item_id = str(entry.get("id") or "")
    if not item_id:
        return None
    row: dict[str, Any] = {"id": item_id}
    if "chance" in entry and entry.get("chance") is not None:
        try:
            row["chance"] = float(entry["chance"])
        except (TypeError, ValueError):
            pass
    return row


def drop_sections_for(entry_id: str) -> list[dict[str, Any]] | None:
    """Dungeon sectioned drops, or None when the entry is a flat monster list."""
    data = load_codex_drops()
    entries = data.get("entries") if isinstance(data.get("entries"), dict) else {}
    raw = entries.get(entry_id)
    if not isinstance(raw, dict):
        return None
    sections_raw = raw.get("sections")
    if not isinstance(sections_raw, list):
        return None
    sections: list[dict[str, Any]] = []
    for section in sections_raw:
        if not isinstance(section, dict):
            continue
        items_raw = section.get("items") if isinstance(section.get("items"), list) else []
        items = [
            row
            for row in (_normalize_drop_row(entry) for entry in items_raw)
            if row is not None
        ]
        if not items:
            continue
        out: dict[str, Any] = {
            "id": str(section.get("id") or ""),
            "label": str(section.get("label") or ""),
            "items": items,
        }
        note = str(section.get("note") or "").strip()
        if note:
            out["note"] = note
        faction = str(section.get("faction") or "").strip()
        if faction:
            out["faction"] = faction
        sections.append(out)
    return sections or None


def drop_rows_for(entry_id: str) -> list[dict[str, Any]]:
    """Drop rows for a codex entry: [{id, chance?}, ...] (legacy string ids ok)."""
    sections = drop_sections_for(entry_id)
    if sections is not None:
        rows: list[dict[str, Any]] = []
        for section in sections:
            rows.extend(section.get("items") or [])
        return rows

    data = load_codex_drops()
    entries = data.get("entries") if isinstance(data.get("entries"), dict) else {}
    raw = entries.get(entry_id) or []
    if not isinstance(raw, list):
        return []
    rows = [
        row
        for row in (_normalize_drop_row(entry) for entry in raw)
        if row is not None
    ]
    return rows


def drop_item_ids_for(entry_id: str) -> list[str]:
    return [str(row["id"]) for row in drop_rows_for(entry_id) if row.get("id")]


def drop_search_text_from_rows(rows: list[dict[str, Any]]) -> str:
    """Lowercase blob of drop item ids + display names for search matching."""
    parts: list[str] = []
    seen: set[str] = set()
    for row in rows:
        item_id = str(row.get("id") or "").strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        parts.append(item_id)
        meta = drop_item_meta(item_id)
        name = str(meta.get("name") or "").strip()
        if not name:
            name = display_name_for(item_id, kind="item")
        if name:
            parts.append(name)
    return " ".join(parts).lower()


def format_drop_chance(chance: float | None) -> str:
    if chance is None:
        return ""
    try:
        value = float(chance)
    except (TypeError, ValueError):
        return ""
    if value < 0:
        return ""
    pct = value * 100.0
    if pct >= 10:
        return f"{pct:.0f}%"
    if pct >= 1:
        return f"{pct:.1f}%"
    if pct >= 0.1:
        return f"{pct:.2f}%"
    if pct >= 0.01:
        return f"{pct:.3f}%"
    return f"{pct:.4f}%"


def drop_item_meta(item_id: str) -> dict[str, str]:
    data = load_codex_drops()
    items = data.get("items") if isinstance(data.get("items"), dict) else {}
    raw = items.get(item_id)
    if not isinstance(raw, dict):
        return {
            "rarity": "",
            "portrait": "",
            "type": "",
            "faction": "",
            "name": "",
        }
    return {
        "rarity": str(raw.get("rarity") or ""),
        "portrait": str(raw.get("portrait") or ""),
        "type": str(raw.get("type") or ""),
        "faction": str(raw.get("faction") or ""),
        "name": str(raw.get("name") or ""),
    }


# Codex drop filter chips (mock order).
DROP_FILTER_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("all", "All"),
    ("weapons", "Weapons"),
    ("armor", "Armor"),
    ("materials", "Materials"),
    ("misc", "Misc"),
)

_DROP_WEAPON_TYPES = frozenset(
    {
        "Sword",
        "Mace",
        "Axe",
        "DualSwords",
        "DualMaces",
        "DualAxes",
        "Daggers",
        "Fists",
        "GreatSword",
        "GreatAxe",
        "GreatMace",
        "Spear",
        "Crescent",
        "Staff",
        "Bow",
        "Book",
        "Halos",
        "Scepter",
        "Thrown",
        "Shield",
        "CaptureNet",
        "OHWeapon",
        "THWeapon",
        "DualWeapon",
        "LongWeapon",
        "MainhandWeapon",
        "OffhandWeapon",
        "Relic",
    }
)
_DROP_ARMOR_TYPES = frozenset(
    {
        "Armor",
        "Head",
        "Shoulders",
        "Chest",
        "Hands",
        "Waist",
        "Legs",
        "Feet",
        "Back",
        "Gear",
        "GearNeck",
        "GearFinger",
        "GearTrinket",
    }
)
_DROP_MATERIAL_TYPES = frozenset(
    {
        "CraftingComponent",
        "Ore",
        "Cloth",
        "Leather",
        "Misc",
        "Bag",
        "Soulstone",
    }
)
_DROP_MOUNT_TYPES = frozenset({"Mount"})
_DROP_GLIDER_TYPES = frozenset({"GearGlider"})
_DROP_CONSUMABLE_TYPES = frozenset(
    {
        "Food",
        "Consumable",
        "HealthPotion",
        "Potion",
        "Elixir",
        "SkillPointBook",
        "Mastery",
    }
)
_DROP_CURRENCY_TYPES = frozenset({"Currency"})
_DROP_RARITY_RANK = {
    "Legendary": 0,
    "Epic": 1,
    "Rare": 2,
    "Uncommon": 3,
    "Common": 4,
}
# Unfiltered (All) grid order: weapons → mounts → gliders → armor → …
_DROP_SORT_GROUP_RANK = {
    "weapons": 0,
    "mounts": 1,
    "gliders": 2,
    "armor": 3,
    "materials": 4,
    "consumables": 5,
    "currency": 6,
    "misc": 7,
}


def drop_filter_category(item_type: str) -> str:
    """Map CastleDB item.type → weapons | armor | materials | misc."""
    value = str(item_type or "")
    if value in _DROP_WEAPON_TYPES:
        return "weapons"
    if value in _DROP_ARMOR_TYPES:
        return "armor"
    if value in _DROP_MATERIAL_TYPES:
        return "materials"
    return "misc"


def drop_sort_group(item_type: str) -> str:
    """Finer group used to order the unfiltered All drops grid."""
    value = str(item_type or "")
    if value in _DROP_WEAPON_TYPES:
        return "weapons"
    if value in _DROP_MOUNT_TYPES:
        return "mounts"
    if value in _DROP_GLIDER_TYPES:
        return "gliders"
    if value in _DROP_ARMOR_TYPES:
        return "armor"
    if value in _DROP_MATERIAL_TYPES:
        return "materials"
    if value in _DROP_CONSUMABLE_TYPES:
        return "consumables"
    if value in _DROP_CURRENCY_TYPES:
        return "currency"
    return "misc"


def drop_sort_group_rank(item_type: str) -> int:
    return _DROP_SORT_GROUP_RANK.get(drop_sort_group(item_type), 99)


def drop_rarity_rank(rarity: str) -> int:
    return _DROP_RARITY_RANK.get(str(rarity or ""), 5)


def portrait_path_for(entry_id: str) -> Path | None:
    dungeon_portraits = load_dungeon_portraits()
    rel = dungeon_portraits.get(entry_id)
    if not rel:
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


def dungeon_header_path_for(entry_id: str) -> Path | None:
    rel = load_dungeon_headers().get(entry_id)
    if not rel:
        return None
    path = ASSET_ROOT / "portraits" / rel
    return path if path.is_file() else None


def dungeon_description_for(entry_id: str) -> str:
    names = _display_names()
    dungeons = names.get("dungeons") if isinstance(names.get("dungeons"), dict) else {}
    entry = dungeons.get(entry_id)
    if isinstance(entry, dict):
        desc = entry.get("desc")
        if isinstance(desc, str) and desc.strip():
            return desc.strip()
    return ""


def item_portrait_path_for(item_id: str) -> Path | None:
    meta = drop_item_meta(item_id)
    rel = meta.get("portrait") or ""
    if not rel:
        # Fall back to unit/collection portrait map (mounts, gliders, gear).
        return portrait_path_for(item_id)
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
    dungeons = names.get("dungeons") if isinstance(names.get("dungeons"), dict) else {}
    if kind in ("dungeon", "auto") and entry_id in dungeons:
        label = dungeons[entry_id]
        if isinstance(label, str) and label.strip():
            return label.strip()
        if isinstance(label, dict) and label.get("name"):
            return str(label["name"])
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


def all_dungeon_ids(catalog: dict[str, Any] | None = None) -> list[str]:
    """Merged dungeon list across all regions (deduped, catalog order)."""
    seen: set[str] = set()
    out: list[str] = []
    for region in regions(catalog):
        for entry_id in region.get("dungeons") or []:
            value = str(entry_id)
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
    return out


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
