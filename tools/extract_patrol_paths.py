#!/usr/bin/env python3
"""Extract authored patrol polylines for ranked/spark spawners (W1 Siagarta).

Spawner nodes in ``gameplayData/*.prefab`` may set ``props.patrol.path`` to a
named spline id. Spline nodes (``type: "spline"``) store world-space
``samples`` used for drawing. Only spawners whose unit / unitGroup resolves to
at least one Spark / Elite / Boss / Miniboss / Unique kind are kept.

Usage:
    python tools/extract_patrol_paths.py

Writes ``assets/patrol_paths_W1_Siagarta.json``.
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
OUT_PATH = ROOT / "assets" / f"patrol_paths_{WORLD}.json"

# Cap polyline density for map draw; always keep endpoints.
_MAX_POLY_POINTS = 48


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


def highest_rank(
    kinds: list[str],
    *,
    spark_set: set[str],
    elite_set: set[str],
    boss_set: set[str],
    miniboss_set: set[str],
    unique_set: set[str],
) -> str:
    if any(kind in boss_set for kind in kinds):
        return "boss"
    if any(kind in miniboss_set for kind in kinds):
        return "miniboss"
    if any(kind in unique_set for kind in kinds):
        return "unique"
    if any(kind in elite_set for kind in kinds):
        return "elite"
    if any(kind in spark_set for kind in kinds):
        return "spark"
    return ""


def decimate_samples(samples: list[dict[str, Any]]) -> list[list[float]]:
    """World XYZ from spline samples, thinned for map polylines."""
    coords: list[list[float]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        try:
            x = float(sample["x"])
            y = float(sample["y"])
            z = float(sample.get("z") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(v) for v in (x, y, z)):
            continue
        coords.append([round4(x), round4(y), round4(z)])
    if len(coords) <= _MAX_POLY_POINTS:
        return coords
    step = max(1, math.ceil((len(coords) - 1) / (_MAX_POLY_POINTS - 1)))
    out = coords[::step]
    if out[-1] != coords[-1]:
        out.append(coords[-1])
    return out[:_MAX_POLY_POINTS] if len(out) > _MAX_POLY_POINTS else out


def patrol_path_ref(props: dict[str, Any]) -> str | None:
    nested = props.get("props")
    if isinstance(nested, dict):
        patrol = nested.get("patrol")
        if isinstance(patrol, dict):
            path = patrol.get("path")
            if isinstance(path, str) and path.strip():
                return path.strip()
    spline = props.get("patrolSpline")
    if isinstance(spline, str) and spline.strip():
        return spline.strip()
    return None


def main() -> int:
    if not PREFAB_DIR.is_dir():
        print(f"missing prefab dir: {PREFAB_DIR}", file=sys.stderr)
        return 1
    traits = json.loads(TRAITS_PATH.read_text(encoding="utf-8"))
    spark_set = {str(k) for k in (traits.get("spark") or []) if isinstance(k, str) and k}
    elite_set = {str(k) for k in (traits.get("elite") or []) if isinstance(k, str) and k}
    boss_set = {str(k) for k in (traits.get("boss") or []) if isinstance(k, str) and k}
    miniboss_set = {
        str(k) for k in (traits.get("miniboss") or []) if isinstance(k, str) and k
    }
    unique_set = {
        str(k) for k in (traits.get("unique") or []) if isinstance(k, str) and k
    }
    ranked_set = spark_set | elite_set | boss_set | miniboss_set | unique_set
    if not ranked_set:
        print("assets/unit_traits.json has no ranked/spark kinds", file=sys.stderr)
        return 1

    cdb = json.loads(CDB_PATH.read_text(encoding="utf-8"))
    unit_groups = {
        str(line["id"]): line
        for line in sheet_lines(cdb, "unitGroup")
        if isinstance(line.get("id"), str)
    }

    splines: dict[str, dict[str, Any]] = {}
    spawners: list[dict[str, Any]] = []

    for path in sorted(PREFAB_DIR.glob("*.prefab")):
        try:
            doc = read_hbson(path.read_bytes())
        except HbsonError as exc:
            print(f"skip {path.name}: {exc}", file=sys.stderr)
            continue
        tile = path.stem

        def on_node(node: dict[str, Any], x: float, y: float, z: float) -> None:
            if node.get("type") == "spline":
                props = node.get("props") if isinstance(node.get("props"), dict) else {}
                sid = props.get("id") if isinstance(props.get("id"), str) else None
                if not sid:
                    sid = node.get("name") if isinstance(node.get("name"), str) else None
                samples = node.get("samples")
                if not sid or not isinstance(samples, list) or not samples:
                    return
                points = decimate_samples(samples)
                if len(points) < 2:
                    return
                splines[sid] = {
                    "id": sid,
                    "name": node.get("name") if isinstance(node.get("name"), str) else sid,
                    "origin": [round4(x), round4(y), round4(z)],
                    "points": points,
                    "source_tile": tile,
                }
                return

            props = node.get("props")
            if not isinstance(props, dict) or props.get("$cdbtype") != "spawner":
                return
            path_ref = patrol_path_ref(props)
            if not path_ref:
                return
            unit = (
                props.get("unit")
                if isinstance(props.get("unit"), str) and props.get("unit")
                else None
            )
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

            kinds: list[str] = []
            seen: set[str] = set()
            for member in members:
                kind = member.get("unit")
                if not isinstance(kind, str) or not kind or kind in seen:
                    continue
                seen.add(kind)
                kinds.append(kind)
            if not any(kind in ranked_set for kind in kinds):
                return

            rank = highest_rank(
                kinds,
                spark_set=spark_set,
                elite_set=elite_set,
                boss_set=boss_set,
                miniboss_set=miniboss_set,
                unique_set=unique_set,
            )
            zone = props.get("zoneBaked")
            spawners.append(
                {
                    "path_id": path_ref,
                    "x": round4(x),
                    "y": round4(y),
                    "z": round4(z),
                    "zone": zone if isinstance(zone, str) else None,
                    "unit": unit,
                    "unit_group": unit_group,
                    "kinds": kinds,
                    "spark": any(kind in spark_set for kind in kinds),
                    "elite": any(kind in elite_set for kind in kinds),
                    "boss": any(kind in boss_set for kind in kinds),
                    "miniboss": any(kind in miniboss_set for kind in kinds),
                    "unique": any(kind in unique_set for kind in kinds),
                    "rank": rank,
                    "source_tile": tile,
                }
            )

        walk_nodes(doc["root"], on_node)

    paths: list[dict[str, Any]] = []
    missing: list[str] = []
    for spawn in spawners:
        path_id = str(spawn["path_id"])
        spline = splines.get(path_id)
        if spline is None:
            missing.append(path_id)
            continue
        paths.append(
            {
                "id": path_id,
                "x": spawn["x"],
                "y": spawn["y"],
                "z": spawn["z"],
                "zone": spawn["zone"],
                "unit": spawn["unit"],
                "unit_group": spawn["unit_group"],
                "kinds": spawn["kinds"],
                "spark": spawn["spark"],
                "elite": spawn["elite"],
                "boss": spawn["boss"],
                "miniboss": spawn["miniboss"],
                "unique": spawn["unique"],
                "rank": spawn["rank"],
                "points": spline["points"],
                "source_tile": spawn["source_tile"],
            }
        )

    paths.sort(
        key=lambda item: (
            float(item["y"]),
            float(item["x"]),
            str(item.get("id") or ""),
        )
    )
    payload = {
        "schema": 1,
        "world": WORLD,
        "count": len(paths),
        "paths": paths,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(paths)} patrol paths -> {OUT_PATH}")
    if missing:
        print(f"missing splines ({len(set(missing))}): {sorted(set(missing))}")

    by_rank: dict[str, int] = {}
    for item in paths:
        rank = str(item.get("rank") or "?")
        by_rank[rank] = by_rank.get(rank, 0) + 1
    for rank, count in sorted(by_rank.items(), key=lambda pair: (-pair[1], pair[0])):
        print(f"  {count}\t{rank}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
