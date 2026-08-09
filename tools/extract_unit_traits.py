#!/usr/bin/env python3
"""Extract CastleDB unit trait kind lists into assets/unit_traits.json.

Reads ``extracted/res.light/data.cdb`` ``unit`` sheet:

  critter   - unit.type == Critter (excludes Base_Critter template)
  spark     - Spark flag
  elite     - Elite flag
  boss      - Boss flag
  miniboss  - Miniboss flag
  unique    - Unique flag

Flag bit indices are resolved from the flags column typeStr, not hardcoded.

Usage:
    python tools/extract_unit_traits.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CDB_PATH = ROOT / "extracted" / "res.light" / "data.cdb"
OUT_PATH = ROOT / "assets" / "unit_traits.json"

NEEDED_FLAGS = ("Spark", "Elite", "Boss", "Miniboss", "Unique")


def sheet_by_name(cdb: dict[str, Any], name: str) -> dict[str, Any] | None:
    for sheet in cdb.get("sheets") or []:
        if isinstance(sheet, dict) and sheet.get("name") == name:
            return sheet
    return None


def flag_bits(unit_sheet: dict[str, Any]) -> dict[str, int]:
    for column in unit_sheet.get("columns") or []:
        if not isinstance(column, dict) or column.get("name") != "flags":
            continue
        type_str = column.get("typeStr")
        if not isinstance(type_str, str) or ":" not in type_str:
            continue
        names = type_str.split(":", 1)[-1].split(",")
        return {name: index for index, name in enumerate(names) if name}
    return {}


def main() -> int:
    if not CDB_PATH.is_file():
        print(f"missing CastleDB: {CDB_PATH}", file=sys.stderr)
        return 1

    cdb = json.loads(CDB_PATH.read_text(encoding="utf-8"))
    unit_sheet = sheet_by_name(cdb, "unit")
    if unit_sheet is None:
        print("data.cdb has no unit sheet", file=sys.stderr)
        return 1

    bits = flag_bits(unit_sheet)
    missing = [name for name in NEEDED_FLAGS if name not in bits]
    if missing:
        print(f"unit flags column missing bits: {', '.join(missing)}", file=sys.stderr)
        return 1

    buckets: dict[str, list[str]] = {
        "critter": [],
        "spark": [],
        "elite": [],
        "boss": [],
        "miniboss": [],
        "unique": [],
    }

    for line in unit_sheet.get("lines") or []:
        if not isinstance(line, dict):
            continue
        uid = line.get("id")
        if not isinstance(uid, str) or not uid or uid == "Base_Critter":
            continue
        flags = line.get("flags")
        flags_i = flags if isinstance(flags, int) else 0

        if line.get("type") == "Critter":
            buckets["critter"].append(uid)
        if (flags_i >> bits["Spark"]) & 1:
            buckets["spark"].append(uid)
        if (flags_i >> bits["Elite"]) & 1:
            buckets["elite"].append(uid)
        if (flags_i >> bits["Boss"]) & 1:
            buckets["boss"].append(uid)
        if (flags_i >> bits["Miniboss"]) & 1:
            buckets["miniboss"].append(uid)
        if (flags_i >> bits["Unique"]) & 1:
            buckets["unique"].append(uid)

    payload = {key: sorted(values) for key, values in buckets.items()}
    # One id per line (stable diffs); trailing commas omitted for strict JSON.
    chunks: list[str] = ["{"]
    keys = list(payload.keys())
    for key_index, key in enumerate(keys):
        chunks.append(f'"{key}": [')
        values = payload[key]
        for value_index, value in enumerate(values):
            suffix = "," if value_index < len(values) - 1 else ""
            chunks.append(f'"{value}"{suffix}')
        chunks.append("]" if key_index == len(keys) - 1 else "],")
    chunks.append("}")
    OUT_PATH.write_text("\n".join(chunks) + "\n", encoding="utf-8")
    counts = ", ".join(f"{key}={len(values)}" for key, values in payload.items())
    print(f"wrote {OUT_PATH.relative_to(ROOT)} ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
