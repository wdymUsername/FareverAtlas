#!/usr/bin/env python3
"""Extract in-game display labels for units and gatherables.

Reads ``extracted/res.light/data.cdb``:

  units       - unit.texts.name + unit.lvl
  gatherables - gatherable id → item display name (from desc [ItemId] / item
                sheet) and size token (Small / Medium / Large)

Usage:
    python tools/extract_display_names.py

Writes ``assets/display_names.json``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CDB_PATH = ROOT / "extracted" / "res.light" / "data.cdb"
OUT_PATH = ROOT / "assets" / "display_names.json"

_ITEM_REF = re.compile(r"\[([A-Za-z0-9_]+)\]")
_SIZE_TOKENS = ("Small", "Medium", "Large", "Big")


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

    payload = {
        "schema": 1,
        "units": dict(sorted(units.items())),
        "gatherables": dict(sorted(gatherables.items())),
        "items": dict(sorted(items.items())),
        "chests": dict(sorted(chests.items())),
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT_PATH.relative_to(ROOT)} "
        f"(units={len(units)}, gatherables={len(gatherables)}, "
        f"items={len(items)}, chests={len(chests)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
