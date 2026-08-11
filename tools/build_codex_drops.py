#!/usr/bin/env python3
"""Build Codex drop lists + item portraits from extracted CDB / POI levels."""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CDB_PATH = ROOT / "extracted" / "res.light" / "data.cdb"
EXTRACTED_RES = ROOT / "extracted" / "res"
POI_ROOT = ROOT / "extracted" / "res.levels" / "Level" / "POI"
CATALOG_PATH = ROOT / "assets" / "codex_catalog.json"
OUT_DROPS = ROOT / "assets" / "codex_drops.json"
OUT_ITEM_MAP = ROOT / "assets" / "item_portraits.json"
OUT_DIR = ROOT / "assets" / "portraits"
SIZE = 64

# Catalog dungeon id -> POI level folder (relative to POI_ROOT).
DUNGEON_LEVELS: dict[str, str] = {
    "Bee_Hive": "Z1Levels/Z1_POI_Dungeon_BeeHive.dat",
    "Z1_POI_Dungeon_ManfishAbyss": "Z2Levels/Z2_POI_Dungeon_ManfishAbyss.dat",
    "R1_POI_AmaymonGoulp": "Z1Levels/Z1_POI_Dungeon_KoboldsMines.dat",
    "R1_POI_Boss_Ratsar": "Z1Levels/Z1_POI_Boss_Ratsar.dat",
    "R1_POI_CleodorasNest": "Z2Levels/Z2_POI_Boss_Cleodora.dat",
    "R1_POI_CrimsonSacristy": "Z3Levels/Z3_POI_Boss_Phrixes.dat",
    "R1_POI_Dungeon_AbbandonedMines": "Z2Levels/Z2_POI_Dungeon_AbbandonedMines.dat",
    "R1_POI_Dungeon_CrimsonBarraks_POI_Def": "Z3Levels/Z3_POI_Dungeon_CrimsonBarraks.dat",
    "R1_POI_Dungeon_Manfish_Ruins": "Z1Levels/Z1_POI_Dungeon_ManfishRuines.dat",
    "R1_POI_GorgonsHollow": "Z2Levels/Z2_POI_Boss_MunsterChuck.dat",
    "R1_POI_MokshisHivetree": "Z1Levels/Z1_POI_Boss_Mokshi.dat",
    "R1_POI_Nepsid_Boss": "Z1Levels/Z1_POI_Boss_Crabgantua.dat",
}

# Faction crates / activity tables layered onto dungeons (chest + activity loot).
TYPE_EXTRA_TABLES: dict[str, tuple[str, ...]] = {
    "Bee": ("BeeCrate", "BeeActivity"),
    "Manfish": ("ManfishCrate", "ManfishActivity"),
    "Kobold": ("KoboldCrate", "KoboldActivity"),
    "Crimson": ("CrimsonCrate", "CrimsonActivity"),
    "Crab": ("ManfishCrate", "ManfishActivity"),
    "Golem": ("DungeonCrate",),
    "Human": ("CrimsonCrate", "CrimsonActivity"),
    "FireGolems": ("DungeonCrate",),
    "EarthGolems": ("DungeonCrate",),
    "WaterGolems": ("DungeonCrate",),
    "WindGolems": ("DungeonCrate",),
}

# Prefer armor/weapon slots first when listing dungeon drops.
GEAR_TYPE_ORDER = (
    "Head",
    "Shoulders",
    "Back",
    "Chest",
    "Hands",
    "Waist",
    "Legs",
    "Feet",
    "Sword",
    "DualSwords",
    "Axe",
    "Mace",
    "GreatMace",
    "Spear",
    "Daggers",
    "Bow",
    "Staff",
    "Thrown",
    "Crescent",
    "GearTrinket",
)

# Runtime-only placeholders (no concrete item gfx) — drop from Codex lists.
_LOOT_PLACEHOLDERS = frozenset({"WorldLoot", "WorldLootWithAffinity"})
# Completion BossChest default when the instance has no lootTable override.
BOSS_CHEST_DEFAULT_TABLE = "UpgradeItems_Activity"
# Guaranteed / showcase currencies from the completion chest.
_BOSS_CHEST_ITEMS = frozenset({"UpgradeRare", "UpgradeAll"})
# Achievement name typos -> real unit id.
_BOSS_ALIASES = {"Splongeblob": "SpongeBlob"}

_ARMOR_TYPES = frozenset(
    {
        "Head",
        "Shoulders",
        "Chest",
        "Hands",
        "Waist",
        "Legs",
        "Feet",
        "Back",
        "GearNeck",
        "GearFinger",
        "GearTrinket",
    }
)
_MOUNT_GLIDER_TYPES = frozenset({"Mount", "GearGlider"})
_WEAPON_TYPES = frozenset(
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
    }
)
# Unit.type -> faction armor pool (when not overridden per dungeon).
_TYPE_FACTION = {
    "Bee": "Bee",
    "Manfish": "Manfish",
    "Kobold": "Kobold",
    "Crimson": "Crimson",
    "Crab": "Manfish",
    "Human": "Crimson",
}
# Dungeons whose boss unit.type is ambiguous (e.g. Golem).
_DUNGEON_FACTION = {
    "Z1_POI_Dungeon_ManfishAbyss": "Manfish",
    "R1_POI_Dungeon_AbbandonedMines": "Kobold",
}
# item.flags bit: ActivityLoot (unique boss weapons).
_FLAG_ACTIVITY_LOOT = 8

_IGNORE_UNITS = frozenset({"World"})
_BOSS_RE = re.compile(r"Defeat \[([A-Za-z][A-Za-z0-9_]*)\]")
# HBSON: @lootTable <len u32 LE> @ <ascii id>
_HBSON_LOOT_TABLE = re.compile(
    rb"@lootTable\x00{0,4}.{0,4}@([A-Za-z][A-Za-z0-9_]{1,63})"
)


class BuildError(RuntimeError):
    pass


def _require_deps():
    try:
        from PIL import Image
    except ImportError as exc:
        raise BuildError(
            "Pillow required: tools/.venv/bin/pip install -r tools/requirements.txt"
        ) from exc
    try:
        import texture2ddecoder
    except ImportError as exc:
        raise BuildError(
            "texture2ddecoder required: tools/.venv/bin/pip install -r tools/requirements.txt"
        ) from exc
    return Image, texture2ddecoder


def decode_dds(path: Path, Image, texture2ddecoder):
    blob = path.read_bytes()
    if blob[:4] != b"DDS ":
        raise BuildError(f"not DDS: {path}")
    if len(blob) < 148:
        raise BuildError(f"truncated DDS: {path}")
    height, width = struct.unpack_from("<II", blob, 12)
    fourcc = blob[84:88]
    if fourcc != b"DX10":
        raise BuildError(f"unsupported DDS fourcc {fourcc!r}: {path}")
    (dxgi_format,) = struct.unpack_from("<I", blob, 128)
    if dxgi_format not in (98, 99):
        raise BuildError(f"unsupported DXGI {dxgi_format}: {path}")
    payload = blob[148:]
    expected = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 16
    if len(payload) < expected:
        raise BuildError(f"DDS payload too small: {path}")
    rgba = texture2ddecoder.decode_bc7(payload[:expected], width, height)
    return Image.frombytes("RGBA", (width, height), rgba, "raw", "BGRA")


def resolve_source(rel_png: str) -> Path | None:
    rel = Path(rel_png)
    dds = EXTRACTED_RES / rel.with_suffix(".dds")
    if dds.is_file():
        return dds
    png = EXTRACTED_RES / rel
    if png.is_file():
        return png
    return None


def asset_rel_for(gfx_file: str) -> str:
    rel = Path(gfx_file)
    parts = list(rel.parts)
    if len(parts) >= 3 and parts[0] == "UI" and parts[1] == "Portraits":
        parts = parts[2:]
    return Path(*parts).with_suffix(".webp").as_posix()


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _has_gfx(item_id: str, items: dict[str, dict]) -> bool:
    row = items.get(item_id)
    if not row:
        return False
    gfx = row.get("gfx")
    return isinstance(gfx, dict) and bool(gfx.get("file"))


def combine_chance(left: float | None, right: float | None) -> float | None:
    """P(at least one) for independent rolls."""
    if left is None:
        return right
    if right is None:
        return left
    return 1.0 - (1.0 - left) * (1.0 - right)


def max_chance(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def merge_chance_maps(
    target: dict[str, float | None],
    incoming: dict[str, float | None],
    *,
    mode: str,
) -> None:
    merge = combine_chance if mode == "combine" else max_chance
    for item_id, chance in incoming.items():
        target[item_id] = merge(target.get(item_id), chance)


def flatten_loot_chances(
    table_id: str,
    tables: dict[str, dict],
    *,
    parent_p: float = 1.0,
    stack: tuple[str, ...] = (),
) -> dict[str, float | None]:
    """Resolve a loot table to item -> compounded drop chance."""
    if not table_id or table_id in stack:
        return {}
    row = tables.get(table_id)
    if not row:
        return {}
    path = stack + (table_id,)
    out: dict[str, float | None] = {}
    for entry in row.get("loot") or []:
        if not isinstance(entry, dict):
            continue
        try:
            proba = float(entry.get("proba") or 0.0)
        except (TypeError, ValueError):
            proba = 0.0
        if proba <= 0.0:
            continue
        path_p = parent_p * proba
        item = entry.get("item")
        if item:
            item_id = str(item)
            out[item_id] = combine_chance(out.get(item_id), path_p)
        nested = entry.get("lootTable")
        if nested:
            merge_chance_maps(
                out,
                flatten_loot_chances(
                    str(nested), tables, parent_p=path_p, stack=path
                ),
                mode="combine",
            )
    return out


def unit_drop_chances(
    unit_id: str,
    *,
    units: dict[str, dict],
    unit_types: dict[str, dict],
    tables: dict[str, dict],
) -> dict[str, float | None]:
    """All tables on a unit kill are rolled together -> combine chances."""
    unit = units.get(unit_id)
    if not unit:
        return {}
    out: dict[str, float | None] = {}
    type_id = str(unit.get("type") or "")
    type_row = unit_types.get(type_id) if type_id else None
    if type_row and type_row.get("lootTable"):
        merge_chance_maps(
            out,
            flatten_loot_chances(str(type_row["lootTable"]), tables),
            mode="combine",
        )
    props = unit.get("props") if isinstance(unit.get("props"), dict) else {}
    for key in ("lootTable", "bossLootTable"):
        table_id = props.get(key)
        if table_id:
            merge_chance_maps(
                out,
                flatten_loot_chances(str(table_id), tables),
                mode="combine",
            )
    return out


def chance_map_to_rows(
    chances: dict[str, float | None],
    items: dict[str, dict],
    *,
    dungeon: bool = False,
) -> list[dict]:
    concrete = {
        item_id: chance
        for item_id, chance in chances.items()
        if _has_gfx(item_id, items)
    }

    def sort_key(item_id: str) -> tuple:
        row = items.get(item_id) or {}
        type_id = str(row.get("type") or "")
        chance = concrete[item_id]
        has_faction = 0 if row.get("faction") else 1
        type_rank = (
            GEAR_TYPE_ORDER.index(type_id) if type_id in GEAR_TYPE_ORDER else 100
        )
        # Known chances first within group; higher chance first.
        chance_rank = 0 if chance is not None else 1
        chance_val = -(chance or 0.0)
        if dungeon:
            return (has_faction, type_rank, chance_rank, chance_val, type_id, item_id)
        return (chance_rank, chance_val, type_rank, type_id, item_id)

    rows: list[dict] = []
    for item_id in sorted(concrete, key=sort_key):
        chance = concrete[item_id]
        row: dict = {"id": item_id}
        if chance is not None:
            row["chance"] = round(float(chance), 8)
        rows.append(row)
    return rows


def boss_unit_for_dungeon(dungeon_id: str, ach_lines: list[dict]) -> str | None:
    for ach in ach_lines:
        blob = json.dumps(ach, ensure_ascii=False)
        if dungeon_id not in blob:
            continue
        desc = str(ach.get("desc") or "")
        match = _BOSS_RE.search(desc)
        if match:
            return match.group(1)
    return None


def _id_mentioned(data: bytes, entry_id: str) -> bool:
    """True if entry_id appears as its own token (not a path folder / prefix).

    Prefab paths like ``.../Hive/Mokshi/World_...`` must not count as unit Mokshi.
    """
    needle = entry_id.encode("ascii")
    start = 0
    while True:
        index = data.find(needle, start)
        if index < 0:
            return False
        before = data[index - 1 : index] if index > 0 else b""
        after = data[index + len(needle) : index + len(needle) + 1]
        # Path segment or dotted asset path.
        if before in (b"/", b"\\") or after in (b"/", b"\\", b"."):
            start = index + 1
            continue
        # Embedded in a longer identifier (Bees_Mokshi, Mokshi_Hexagonal, …).
        if before and (before.isalnum() or before == b"_"):
            start = index + 1
            continue
        if after and (after.isalnum() or after == b"_"):
            start = index + 1
            continue
        return True


def scan_level_ids(
    folder: Path,
    *,
    unit_ids: set[str],
    table_ids: set[str],
) -> tuple[set[str], set[str]]:
    found_units: set[str] = set()
    found_tables: set[str] = set()
    if not folder.is_dir():
        return found_units, found_tables
    # Longest first so we only need one pass per file for membership checks.
    unit_list = sorted(unit_ids - _IGNORE_UNITS, key=len, reverse=True)
    table_list = sorted(table_ids, key=len, reverse=True)
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".prefab", ".dat", ""}:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        for unit_id in unit_list:
            if unit_id not in found_units and _id_mentioned(data, unit_id):
                found_units.add(unit_id)
        for table_id in table_list:
            if table_id not in found_tables and _id_mentioned(data, table_id):
                found_tables.add(table_id)
    return found_units, found_tables


def collect_catalog_ids(catalog: dict) -> tuple[list[str], list[str]]:
    monsters: list[str] = []
    dungeons: list[str] = []
    for region in catalog.get("regions") or []:
        if not isinstance(region, dict):
            continue
        monsters.extend(str(v) for v in (region.get("monsters") or []) if str(v))
        dungeons.extend(str(v) for v in (region.get("dungeons") or []) if str(v))
    return dedupe(monsters), dedupe(dungeons)


def item_meta_from_row(item_id: str, row: dict) -> dict[str, str]:
    texts = row.get("texts") if isinstance(row.get("texts"), dict) else {}
    return {
        "rarity": str(row.get("rarity") or ""),
        "type": str(row.get("type") or ""),
        "faction": str(row.get("faction") or ""),
        "name": str(texts.get("name") or ""),
    }


def scan_boss_chest_loot_table(folder: Path, *, known_tables: set[str]) -> str | None:
    """Return BossChest lootTable id from a dungeon POI folder, if present.

    Instances without an override use ``BOSS_CHEST_DEFAULT_TABLE``.
    """
    if not folder.is_dir():
        return None
    found_chest = False
    for path in folder.rglob("*.prefab"):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"BossChest" not in data and b"BossChest.prefab" not in data:
            if b"Gameplay/Elements/Activities/BossChest.prefab" not in data:
                continue
        found_chest = True
        # Prefer an explicit override that names a real loot table.
        for match in _HBSON_LOOT_TABLE.finditer(data):
            table_id = match.group(1).decode("ascii")
            if table_id in known_tables:
                return table_id
        # Fallback: first @lootTable followed by a known table id token.
        idx = 0
        while True:
            pos = data.find(b"@lootTable", idx)
            if pos < 0:
                break
            window = data[pos : pos + 96]
            for token in re.findall(rb"[A-Za-z][A-Za-z0-9_]{2,}", window):
                text = token.decode("ascii")
                if text == "lootTable":
                    continue
                if text in known_tables:
                    return text
            idx = pos + 1
    if found_chest:
        return BOSS_CHEST_DEFAULT_TABLE
    return None


def strip_loot_placeholders(chances: dict[str, float | None]) -> None:
    for key in _LOOT_PLACEHOLDERS:
        chances.pop(key, None)


def _item_has_activity_loot(row: dict) -> bool:
    flags = row.get("flags")
    if isinstance(flags, int):
        return bool(flags & _FLAG_ACTIVITY_LOOT)
    if isinstance(flags, list):
        return "ActivityLoot" in flags
    if isinstance(flags, str):
        return flags == "ActivityLoot"
    return False


def _is_boss_showcase_item(item_id: str, row: dict) -> bool:
    if item_id in _BOSS_CHEST_ITEMS:
        return True
    type_id = str(row.get("type") or "")
    if type_id in _MOUNT_GLIDER_TYPES or type_id in _WEAPON_TYPES:
        return True
    return _item_has_activity_loot(row)


def _is_faction_armor_item(row: dict, *, faction: str) -> bool:
    if str(row.get("faction") or "") != faction:
        return False
    if str(row.get("rarity") or "") != "Rare":
        return False
    if _item_has_activity_loot(row):
        return False
    return str(row.get("type") or "") in _ARMOR_TYPES


def faction_for_dungeon(
    dungeon_id: str,
    *,
    boss: str | None,
    units: dict[str, dict],
    items: dict[str, dict],
    tables: dict[str, dict],
) -> str | None:
    override = _DUNGEON_FACTION.get(dungeon_id)
    if override:
        return override
    if not boss:
        return None
    unit = units.get(boss) or {}
    mapped = _TYPE_FACTION.get(str(unit.get("type") or ""))
    if mapped:
        return mapped
    # Majority faction on the boss weapon table (skip World / Craft).
    props = unit.get("props") if isinstance(unit.get("props"), dict) else {}
    counts: dict[str, int] = {}
    for key in ("bossLootTable", "lootTable"):
        table_id = props.get(key)
        if not table_id:
            continue
        for entry in (tables.get(str(table_id)) or {}).get("loot") or []:
            if not isinstance(entry, dict) or not entry.get("item"):
                continue
            item = items.get(str(entry["item"])) or {}
            fac = str(item.get("faction") or "")
            if fac and fac not in {"World", "Craft", "Starter"}:
                counts[fac] = counts.get(fac, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def faction_pool_note(faction: str) -> str:
    return f"Shared across all {faction} dungeons — not exclusive to this one."


def collect_entry_item_ids(entry: list | dict) -> list[str]:
    """Flatten item ids from a monster list or dungeon sections payload."""
    if isinstance(entry, list):
        return [
            str(row["id"])
            for row in entry
            if isinstance(row, dict) and row.get("id")
        ]
    if not isinstance(entry, dict):
        return []
    out: list[str] = []
    for section in entry.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for row in section.get("items") or []:
            if isinstance(row, dict) and row.get("id"):
                out.append(str(row["id"]))
    return out


def build_dungeon_sections(
    dungeon_id: str,
    *,
    units: dict[str, dict],
    unit_types: dict[str, dict],
    tables: dict[str, dict],
    items: dict[str, dict],
    ach_lines: list[dict],
) -> dict:
    """Boss showcase + faction armor pool + other materials for one dungeon."""
    boss = boss_unit_for_dungeon(dungeon_id, ach_lines)
    if boss:
        boss = _BOSS_ALIASES.get(boss, boss)
        if boss not in units:
            boss = None

    boss_chances: dict[str, float | None] = {}
    if boss:
        props = (units.get(boss) or {}).get("props")
        props = props if isinstance(props, dict) else {}
        for key in ("bossLootTable", "lootTable"):
            table_id = props.get(key)
            if table_id:
                merge_chance_maps(
                    boss_chances,
                    flatten_loot_chances(str(table_id), tables),
                    mode="max",
                )

    # Completion currency (Spark Shard). Some BossChest instances override the
    # table to a boss weapon list — still surface the default activity shards.
    chest_chances = flatten_loot_chances(BOSS_CHEST_DEFAULT_TABLE, tables)
    for item_id in _BOSS_CHEST_ITEMS:
        if item_id in chest_chances:
            boss_chances[item_id] = chest_chances[item_id]

    strip_loot_placeholders(boss_chances)
    boss_filtered = {
        item_id: chance
        for item_id, chance in boss_chances.items()
        if _is_boss_showcase_item(item_id, items.get(item_id) or {})
        and _has_gfx(item_id, items)
    }

    def boss_sort_key(item_id: str) -> tuple:
        row = items.get(item_id) or {}
        type_id = str(row.get("type") or "")
        if item_id in _BOSS_CHEST_ITEMS:
            group = 2
        elif type_id in _MOUNT_GLIDER_TYPES:
            group = 1
        else:
            group = 0
        type_rank = (
            GEAR_TYPE_ORDER.index(type_id) if type_id in GEAR_TYPE_ORDER else 100
        )
        chance = boss_filtered[item_id]
        chance_rank = 0 if chance is not None else 1
        return (group, type_rank, chance_rank, -(chance or 0.0), item_id)

    boss_rows = []
    for item_id in sorted(boss_filtered, key=boss_sort_key):
        row: dict = {"id": item_id}
        chance = boss_filtered[item_id]
        if chance is not None:
            row["chance"] = round(float(chance), 8)
        boss_rows.append(row)

    faction = faction_for_dungeon(
        dungeon_id, boss=boss, units=units, items=items, tables=tables
    )
    faction_rows: list[dict] = []
    if faction:
        armor_ids = [
            item_id
            for item_id, row in items.items()
            if _is_faction_armor_item(row, faction=faction) and _has_gfx(item_id, items)
        ]

        def armor_key(item_id: str) -> tuple:
            row = items.get(item_id) or {}
            type_id = str(row.get("type") or "")
            type_rank = (
                GEAR_TYPE_ORDER.index(type_id) if type_id in GEAR_TYPE_ORDER else 100
            )
            return (type_rank, type_id, item_id)

        faction_rows = [{"id": item_id} for item_id in sorted(armor_ids, key=armor_key)]

    other_chances: dict[str, float | None] = {}
    boss_type = str((units.get(boss) or {}).get("type") or "") if boss else ""
    type_row = unit_types.get(boss_type) if boss_type else None
    if type_row and type_row.get("lootTable"):
        merge_chance_maps(
            other_chances,
            flatten_loot_chances(str(type_row["lootTable"]), tables),
            mode="max",
        )
    for extra in TYPE_EXTRA_TABLES.get(boss_type, ()):
        merge_chance_maps(
            other_chances,
            flatten_loot_chances(extra, tables),
            mode="max",
        )
    strip_loot_placeholders(other_chances)

    boss_ids = {str(row["id"]) for row in boss_rows}
    faction_ids = {str(row["id"]) for row in faction_rows}
    for item_id in list(other_chances):
        row = items.get(item_id) or {}
        if item_id in boss_ids or item_id in faction_ids:
            other_chances.pop(item_id, None)
            continue
        if item_id in _BOSS_CHEST_ITEMS or _item_has_activity_loot(row):
            other_chances.pop(item_id, None)
            continue
        if faction and _is_faction_armor_item(row, faction=faction):
            other_chances.pop(item_id, None)
            continue
        type_id = str(row.get("type") or "")
        if type_id in _WEAPON_TYPES or type_id in _ARMOR_TYPES:
            # Keep weapons/armor out of "other"; boss/faction cover those.
            other_chances.pop(item_id, None)
    other_rows = chance_map_to_rows(other_chances, items, dungeon=False)

    sections: list[dict] = []
    if boss_rows:
        sections.append({"id": "boss", "label": "Boss drops", "items": boss_rows})
    if faction_rows and faction:
        sections.append(
            {
                "id": "faction",
                "label": "Possible faction rewards",
                "faction": faction,
                "note": faction_pool_note(faction),
                "items": faction_rows,
            }
        )
    if other_rows:
        sections.append({"id": "other", "label": "Other loot", "items": other_rows})
    return {"sections": sections}


def build_drops(
    cdb: dict, catalog: dict
) -> tuple[dict[str, list | dict], dict[str, dict[str, str]]]:
    sheets = {sheet["name"]: sheet for sheet in cdb["sheets"]}
    tables = {
        str(line["id"]): line
        for line in sheets["lootTable"]["lines"]
        if line.get("id")
    }
    units = {
        str(line["id"]): line
        for line in sheets["unit"]["lines"]
        if line.get("id")
    }
    unit_types = {
        str(line["id"]): line
        for line in sheets["unitType"]["lines"]
        if line.get("id")
    }
    items = {
        str(line["id"]): line
        for line in sheets["item"]["lines"]
        if line.get("id")
    }
    ach_lines = list(sheets.get("ach", {}).get("lines") or [])

    monsters, dungeons = collect_catalog_ids(catalog)
    drops: dict[str, list | dict] = {}
    item_meta: dict[str, dict[str, str]] = {}

    for unit_id in monsters:
        drops[unit_id] = chance_map_to_rows(
            unit_drop_chances(
                unit_id, units=units, unit_types=unit_types, tables=tables
            ),
            items,
            dungeon=False,
        )

    for dungeon_id in dungeons:
        drops[dungeon_id] = build_dungeon_sections(
            dungeon_id,
            units=units,
            unit_types=unit_types,
            tables=tables,
            items=items,
            ach_lines=ach_lines,
        )

    all_items = dedupe(
        [
            item_id
            for entry in drops.values()
            for item_id in collect_entry_item_ids(entry)
        ]
    )
    for item_id in all_items:
        item_meta[item_id] = item_meta_from_row(item_id, items.get(item_id) or {})

    return drops, item_meta


def convert_item_portraits(
    cdb: dict,
    item_ids: list[str],
    *,
    size: int,
) -> dict[str, str]:
    Image, texture2ddecoder = _require_deps()
    sheets = {sheet["name"]: sheet for sheet in cdb["sheets"]}
    items = {
        str(line["id"]): line
        for line in sheets["item"]["lines"]
        if line.get("id")
    }

    source_to_asset: dict[str, str] = {}
    entry_to_asset: dict[str, str] = {}
    converted = 0
    missing = 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for item_id in item_ids:
        row = items.get(item_id)
        if not row:
            missing += 1
            continue
        gfx = row.get("gfx")
        gfx_file = None
        if isinstance(gfx, dict) and gfx.get("file"):
            gfx_file = str(gfx["file"])
        if not gfx_file:
            missing += 1
            continue
        asset_rel = asset_rel_for(gfx_file)
        entry_to_asset[item_id] = asset_rel
        out_path = OUT_DIR / asset_rel
        if out_path.is_file() and gfx_file in source_to_asset:
            continue
        if out_path.is_file():
            source_to_asset[gfx_file] = asset_rel
            continue
        if gfx_file in source_to_asset:
            continue
        source = resolve_source(gfx_file)
        if source is None:
            missing += 1
            print(f"MISS  {item_id} <- {gfx_file}", file=sys.stderr)
            entry_to_asset.pop(item_id, None)
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".dds":
            image = decode_dds(source, Image, texture2ddecoder)
        else:
            image = Image.open(source).convert("RGBA")
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        image.save(out_path, "WEBP", quality=82, method=4)
        source_to_asset[gfx_file] = asset_rel
        converted += 1

    entry_to_asset = {
        key: value
        for key, value in entry_to_asset.items()
        if (OUT_DIR / value).is_file()
    }
    print(
        f"item_portraits entries={len(entry_to_asset)} converted={converted} missing={missing}"
    )
    return entry_to_asset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=SIZE)
    parser.add_argument(
        "--skip-portraits",
        action="store_true",
        help="Only rebuild codex_drops.json (reuse existing item webps).",
    )
    args = parser.parse_args()

    if not CDB_PATH.is_file():
        raise BuildError(f"missing {CDB_PATH}")
    if not CATALOG_PATH.is_file():
        raise BuildError(f"missing {CATALOG_PATH}")

    cdb = json.loads(CDB_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    drops, item_meta = build_drops(cdb, catalog)

    all_items = dedupe(
        [
            item_id
            for entry in drops.values()
            for item_id in collect_entry_item_ids(entry)
        ]
    )
    portraits: dict[str, str] = {}
    if not args.skip_portraits:
        portraits = convert_item_portraits(cdb, all_items, size=args.size)
        OUT_ITEM_MAP.write_text(
            json.dumps(
                {"schema": 1, "size": args.size, "portraits": portraits},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        if OUT_ITEM_MAP.is_file():
            payload = json.loads(OUT_ITEM_MAP.read_text(encoding="utf-8"))
            raw = payload.get("portraits") if isinstance(payload, dict) else {}
            if isinstance(raw, dict):
                portraits = {str(k): str(v) for k, v in raw.items()}

    items_payload = {}
    for item_id in all_items:
        meta = dict(item_meta.get(item_id) or {})
        meta["portrait"] = portraits.get(item_id) or ""
        items_payload[item_id] = meta
    payload = {
        "schema": 2,
        "entries": drops,
        "items": items_payload,
    }
    OUT_DROPS.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with_drops = sum(1 for entry in drops.values() if collect_entry_item_ids(entry))
    print(
        f"drops entries={len(drops)} with_items={with_drops} "
        f"unique_items={len(all_items)} -> {OUT_DROPS}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
