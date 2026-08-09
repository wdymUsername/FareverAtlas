#!/usr/bin/env python3
"""Extract wild companion-critter spawn points from W1 Siagarta HBSON prefabs.

Spawns live in ``gameplayData/*.prefab`` as ``$cdbtype: "spawner"`` nodes. Most
companions are named only via ``unitGroup`` (weighted pools in ``data.cdb``); a
few (e.g. ``Sheep_Spark``) are a direct unit. World XYZ comes from
``walk_nodes`` — tile names are provenance only.

Usage:
    python tools/extract_critter_spawns.py

Writes ``assets/critter_spawns_W1_Siagarta.json``.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

from hbson import HbsonError, read_hbson, walk_nodes

ROOT = Path(__file__).resolve().parents[1]
WORLD = "W1_Siagarta"
PREFAB_DIR = ROOT / "extracted" / "res.map" / "Level" / "World" / f"{WORLD}.dat" / "gameplayData"
CDB_PATH = ROOT / "extracted" / "res.light" / "data.cdb"
TRAITS_PATH = ROOT / "assets" / "unit_traits.json"
OUT_PATH = ROOT / "assets" / f"critter_spawns_{WORLD}.json"


def round4(value: float) -> float:
    return round(float(value) * 10000.0) / 10000.0


def sheet_lines(cdb: dict[str, Any], name: str) -> list[dict[str, Any]]:
    for sheet in cdb.get("sheets") or []:
        if isinstance(sheet, dict) and sheet.get("name") == name:
            lines = sheet.get("lines") or []
            return [line for line in lines if isinstance(line, dict)]
    return []


def group_members(
    unit_groups: dict[str, dict[str, Any]],
    group_id: str,
    depth: int = 0,
) -> list[dict[str, Any]]:
    group = unit_groups.get(group_id)
    if not group or depth > 3:
        return []
    out: list[dict[str, Any]] = []
    for comp in group.get("composition") or []:
        if not isinstance(comp, dict):
            continue
        weight = comp.get("weight", 1)
        try:
            weight_f = float(weight)
        except (TypeError, ValueError):
            weight_f = 1.0
        for entry in comp.get("group") or []:
            if not isinstance(entry, dict):
                continue
            unit = entry.get("unit")
            nested_group = entry.get("unitGroup")
            if isinstance(unit, str) and unit:
                out.append({"unit": unit, "weight": weight_f})
            elif isinstance(nested_group, str) and nested_group:
                for nested in group_members(unit_groups, nested_group, depth + 1):
                    out.append(
                        {
                            "unit": nested["unit"],
                            "weight": weight_f * float(nested["weight"]),
                        }
                    )
    return out


def roaming_range(props: dict[str, Any]) -> float | None:
    nested = props.get("props")
    if isinstance(nested, dict) and nested.get("roamingRange") is not None:
        try:
            return float(nested["roamingRange"])
        except (TypeError, ValueError):
            return None
    if props.get("roamingRange") is not None:
        try:
            return float(props["roamingRange"])
        except (TypeError, ValueError):
            return None
    return None


def main() -> int:
    if not PREFAB_DIR.is_dir():
        print(f"missing prefab dir: {PREFAB_DIR}", file=sys.stderr)
        return 1
    traits = json.loads(TRAITS_PATH.read_text(encoding="utf-8"))
    critter_set = {str(k) for k in (traits.get("critter") or []) if isinstance(k, str) and k}
    spark_set = {str(k) for k in (traits.get("spark") or []) if isinstance(k, str) and k}
    if not critter_set:
        print("assets/unit_traits.json has no critter kinds", file=sys.stderr)
        return 1

    cdb = json.loads(CDB_PATH.read_text(encoding="utf-8"))
    unit_groups = {
        str(line["id"]): line
        for line in sheet_lines(cdb, "unitGroup")
        if isinstance(line.get("id"), str)
    }

    spawns: list[dict[str, Any]] = []
    for path in sorted(PREFAB_DIR.glob("*.prefab")):
        try:
            doc = read_hbson(path.read_bytes())
        except HbsonError as exc:
            print(f"skip {path.name}: {exc}", file=sys.stderr)
            continue
        tile = path.stem

        def on_node(node: dict[str, Any], x: float, y: float, z: float) -> None:
            props = node.get("props")
            if not isinstance(props, dict) or props.get("$cdbtype") != "spawner":
                return
            unit = props.get("unit") if isinstance(props.get("unit"), str) and props.get("unit") else None
            unit_group = (
                props.get("unitGroup")
                if isinstance(props.get("unitGroup"), str) and props.get("unitGroup")
                else None
            )
            if not unit and not unit_group:
                return

            members: list[dict[str, Any]] = []
            if unit:
                members.append({"unit": unit, "weight": 1.0})
            if unit_group:
                members.extend(group_members(unit_groups, unit_group))

            weight_by_kind: dict[str, float] = {}
            for member in members:
                kind = member.get("unit")
                if not isinstance(kind, str) or kind not in critter_set:
                    continue
                weight_by_kind[kind] = weight_by_kind.get(kind, 0.0) + float(
                    member.get("weight") or 1.0
                )
            if not weight_by_kind:
                return

            kinds = sorted(weight_by_kind)
            spark_kinds = [kind for kind in kinds if kind in spark_set]
            range_value = roaming_range(props)
            zone = props.get("zoneBaked")
            spawns.append(
                {
                    "x": round4(x),
                    "y": round4(y),
                    "z": round4(z),
                    "zone": zone if isinstance(zone, str) else None,
                    "unit": unit,
                    "unit_group": unit_group,
                    "kinds": kinds,
                    "spark_kinds": spark_kinds,
                    "spark": bool(spark_kinds),
                    "roaming_range": range_value if range_value is not None and math.isfinite(range_value) else None,
                    "source_tile": tile,
                }
            )

        walk_nodes(doc["root"], on_node)

    spawns.sort(
        key=lambda item: (
            float(item["y"]),
            float(item["x"]),
            str(item.get("unit_group") or item.get("unit") or ""),
        )
    )
    payload = {
        "schema": 1,
        "world": WORLD,
        "count": len(spawns),
        "spawns": spawns,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(spawns)} critter spawns -> {OUT_PATH}")

    groups: dict[str, int] = {}
    for spawn in spawns:
        key = str(spawn.get("unit_group") or spawn.get("unit") or "?")
        groups[key] = groups.get(key, 0) + 1
    for key, count in sorted(groups.items(), key=lambda pair: (-pair[1], pair[0])):
        print(f"  {count}\t{key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
