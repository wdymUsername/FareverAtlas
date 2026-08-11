#!/usr/bin/env python3
"""Extract in-game display labels for units and gatherables.

Reads ``extracted/res.light/data.cdb``:

  units       - unit.texts.name + unit.lvl
  gatherables - gatherable id → item display name (from desc [ItemId] / item
                sheet) and size token (Small / Medium / Large)
  dungeons    - POI / dungeon texts.name from English lang export
                (e.g. Lady Bee's Palace, Ratsar's Lair)

Usage:
    python tools/extract_display_names.py

Writes ``assets/data/display_names.json``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CDB_PATH = ROOT / "extracted" / "res.light" / "data.cdb"
CATALOG_PATH = ROOT / "assets" / "codex_catalog.json"
LANG_DIR = ROOT / "extracted" / "res" / "lang"
OUT_PATH = ROOT / "assets" / "data" / "display_names.json"

_ITEM_REF = re.compile(r"\[([A-Za-z0-9_]+)\]")
_SIZE_TOKENS = ("Small", "Medium", "Large", "Big")
_LANG_NAME = re.compile(
    r"<([A-Za-z][A-Za-z0-9_]*)>\s*<texts\.name>(.*?)</texts\.name>"
    r"(?:\s*<texts\.desc>(.*?)</texts\.desc>)?",
    re.S,
)


def sheet_lines(cdb: dict[str, Any], name: str) -> list[dict[str, Any]]:
    for sheet in cdb.get("sheets") or []:
        if isinstance(sheet, dict) and sheet.get("name") == name:
            lines = sheet.get("lines") or []
            return [line for line in lines if isinstance(line, dict)]
    return []


def size_from_id(node_id: str) -> str | None:
    for token in _SIZE_TOKENS:
        if node_id.endswith(f"_{token}") or node_id == token:
            return "Large" if token == "Big" else token
    return None


def split_ident(value: str) -> str:
    """Turn CamelCase / snake_case ids into spaced words."""
    text = value.replace("_", " ").strip()
    if not text:
        return ""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    return " ".join(part for part in text.split() if part)


def catalog_dungeon_ids() -> list[str]:
    if not CATALOG_PATH.is_file():
        return []
    try:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for region in catalog.get("regions") or []:
        if not isinstance(region, dict):
            continue
        for entry_id in region.get("dungeons") or []:
            value = str(entry_id)
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
    return out


def resolve_english_lang_export() -> Path | None:
    """Prefer an English (or English-source) lang dump for dungeon titles."""
    candidates = [
        LANG_DIR / "export_en.xml",
        LANG_DIR / "old" / "export_en_old.xml",
        # Pre-localization dumps keep English source strings.
        LANG_DIR / "old" / "export_de_old.xml",
        LANG_DIR / "old" / "export_fr_old.xml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _strip_markup(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[ \t]+\n", "\n", text).strip()


def resolve_desc_refs(
    desc: str,
    *,
    units: dict[str, dict[str, Any]],
    items: dict[str, str],
    lang_names: dict[str, str] | None = None,
) -> str:
    """Replace [UnitId]/[ItemId] refs with display names; strip light HTML."""
    lang_names = lang_names or {}

    def repl(match: re.Match[str]) -> str:
        ref = match.group(1)
        unit = units.get(ref)
        if isinstance(unit, dict) and unit.get("name"):
            return str(unit["name"])
        if ref in lang_names:
            return lang_names[ref]
        if ref in items:
            return items[ref]
        return split_ident(ref) or ref

    cleaned = _strip_markup(desc)
    return _ITEM_REF.sub(repl, cleaned)


def extract_lang_entries(path: Path) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    entries: dict[str, dict[str, str]] = {}
    for match in _LANG_NAME.finditer(text):
        entry_id = match.group(1)
        name = match.group(2).strip()
        if not entry_id or not name:
            continue
        entry = {"name": name}
        desc = match.group(3)
        if isinstance(desc, str) and desc.strip():
            entry["desc"] = desc.strip()
        entries[entry_id] = entry
    return entries


def main() -> int:
    if not CDB_PATH.is_file():
        print(f"missing CastleDB: {CDB_PATH}", file=sys.stderr)
        return 1

    cdb = json.loads(CDB_PATH.read_text(encoding="utf-8"))

    items: dict[str, str] = {}
    for line in sheet_lines(cdb, "item"):
        item_id = line.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        texts = line.get("texts") if isinstance(line.get("texts"), dict) else {}
        name = texts.get("name")
        if isinstance(name, str) and name.strip():
            items[item_id] = name.strip()

    units: dict[str, dict[str, Any]] = {}
    for line in sheet_lines(cdb, "unit"):
        unit_id = line.get("id")
        if not isinstance(unit_id, str) or not unit_id:
            continue
        texts = line.get("texts") if isinstance(line.get("texts"), dict) else {}
        name = texts.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        entry: dict[str, Any] = {"name": name.strip()}
        lvl = line.get("lvl")
        if isinstance(lvl, (int, float)) and int(lvl) > 0:
            entry["level"] = int(lvl)
        units[unit_id] = entry

    gatherables: dict[str, dict[str, Any]] = {}
    for line in sheet_lines(cdb, "gatherable"):
        gid = line.get("id")
        if not isinstance(gid, str) or not gid:
            continue
        texts = line.get("texts") if isinstance(line.get("texts"), dict) else {}
        gname = texts.get("name") if isinstance(texts.get("name"), str) else None
        desc = texts.get("desc") if isinstance(texts.get("desc"), str) else ""
        item_name: str | None = None
        for ref in _ITEM_REF.findall(desc):
            if ref in items:
                item_name = items[ref]
                break
            pretty = split_ident(ref)
            if pretty:
                item_name = pretty
                break
        size = size_from_id(gid)
        if not gname and not item_name and not size:
            continue
        entry = {}
        if isinstance(gname, str) and gname.strip():
            entry["name"] = gname.strip()
        if item_name:
            entry["item"] = item_name
        if size:
            entry["size"] = size
        gatherables[gid] = entry

    # Known chest Element.kind / prefab tokens (not a CastleDB sheet).
    chests = {
        "worldchest": "World Chest",
        "recipechest": "Recipe Chest",
        "orbchest": "Orb Chest",
        "vaultchest": "Vault Chest",
        "campchest": "Camp Chest",
        "chest": "Chest",
    }

    dungeons: dict[str, dict[str, str]] = {}
    lang_path = resolve_english_lang_export()
    if lang_path is not None:
        lang_entries = extract_lang_entries(lang_path)
        lang_names = {
            entry_id: entry["name"]
            for entry_id, entry in lang_entries.items()
            if entry.get("name")
        }
        # Alias stale lang unit refs used in dungeon blurbs.
        if "MunsterChuck" in units and "Kobold_Z1D_Boss" not in units:
            lang_names.setdefault(
                "Kobold_Z1D_Boss", str(units["MunsterChuck"]["name"])
            )
        for dungeon_id in catalog_dungeon_ids():
            entry = lang_entries.get(dungeon_id)
            if not entry:
                continue
            out = {"name": entry["name"]}
            raw_desc = entry.get("desc")
            if isinstance(raw_desc, str) and raw_desc.strip():
                out["desc"] = resolve_desc_refs(
                    raw_desc, units=units, items=items, lang_names=lang_names
                )
            dungeons[dungeon_id] = out
    else:
        print("warning: no lang export found for dungeon names", file=sys.stderr)

    payload = {
        "schema": 1,
        "units": dict(sorted(units.items())),
        "gatherables": dict(sorted(gatherables.items())),
        "items": dict(sorted(items.items())),
        "chests": dict(sorted(chests.items())),
        "dungeons": dict(sorted(dungeons.items())),
    }
    OUT_PATH.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {OUT_PATH.relative_to(ROOT)} "
        f"(units={len(units)}, gatherables={len(gatherables)}, "
        f"items={len(items)}, chests={len(chests)}, dungeons={len(dungeons)})"
    )
    if lang_path is not None:
        print(f"dungeon names from {lang_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
