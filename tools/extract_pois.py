#!/usr/bin/env python3
"""Refresh POI world coordinates from W1 Siagarta HBSON prefabs.

``assets/data/w1_siagarta/pois.json`` is the shipped static POI table (imported from
farever-minimap / game data). Prefab export issues this tool corrects:

  - Orb/Camp chests exported with parent-local offsets instead of world XYZ
  - Activity markers that sit on the activity root instead of the gameplay
    spot players actually go to (chest / fight stone / race start / …)
  - Missing Orb/Camp/Vault chest rows that exist in map prefabs

Activity snap targets (first matching child under the activity node):

  ChestOrb / WorldCamp     → OrbChest / CampChest (Heaps rotationZ)
  FightStone               → FightStone.prefab (standard rotationZ; matches live)
  TimerCollectRun          → TimerCollectOrbFirstOrb (start orb)
  Ascension                → Ascension_Start
  MountRush                → MountRush_Start
  WorldElite / WorldPlant  → activity root (no useful child offset)

FightStone interactibles disagree with the Heaps child transform used for
Orb/Camp chests — their live XY matches a standard CCW rotationZ instead.

Usage:
    python tools/extract_pois.py

Updates ``assets/data/w1_siagarta/pois.json`` in place. Prints a summary of fixes.
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
OUT_PATH = ROOT / "assets" / "data" / "w1_siagarta" / "pois.json"

# Ignore floating noise; treat larger deltas as real fixes.
_EPS = 0.05

_ACTIVITY_CHEST_SOURCES = frozenset(
    {
        "Gameplay/Elements/Activities/OrbChest.prefab",
        "Gameplay/Elements/Activities/CampChest.prefab",
    }
)
_VAULT_CHEST_SOURCE = "Gameplay/Elements/Activities/VaultChest.prefab"
_FIGHT_STONE_SOURCE = "Gameplay/Elements/Activities/FightStone.prefab"

# subkind (lower) → preferred child source paths, in priority order.
_ACTIVITY_ANCHOR_SOURCES: dict[str, tuple[str, ...]] = {
    "chestorb": ("Gameplay/Elements/Activities/OrbChest.prefab",),
    "worldcamp": ("Gameplay/Elements/Activities/CampChest.prefab",),
    "fightstone": (_FIGHT_STONE_SOURCE,),
    "timercollectrun": (
        "Gameplay/Elements/Activities/TimerCollectOrbFirstOrb.prefab",
    ),
    "ascension": ("Gameplay/Elements/Activities/Ascension_Start.prefab",),
    "mountrush": ("Gameplay/Elements/Activities/MountRush_Start.prefab",),
}


def round4(value: float) -> float:
    return round(float(value) * 10000.0) / 10000.0


def _ship_poi(poi: dict[str, Any]) -> dict[str, Any]:
    """Drop extract-only provenance fields from the shipped POI row."""
    shipped: dict[str, Any] = {}
    for key, value in poi.items():
        if key in ("source", "source_tile"):
            continue
        if key == "subkind" and (value is None or value == ""):
            continue
        shipped[key] = value
    return shipped


def _heaps_offset(lx: float, ly: float, rot: float) -> tuple[float, float]:
    """Farever/Heaps horizontal offset (matches Orb/Camp live positions)."""
    if not rot:
        return lx, ly
    angle = math.radians(rot)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return lx * sin_a - ly * cos_a, lx * cos_a + ly * sin_a


def _standard_offset(lx: float, ly: float, rot: float) -> tuple[float, float]:
    """Standard CCW rotationZ offset (matches live FightStone interactibles)."""
    if not rot:
        return lx, ly
    angle = math.radians(rot)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return lx * cos_a - ly * sin_a, lx * sin_a + ly * cos_a


def _pos_delta(poi: dict[str, Any], pref: dict[str, Any]) -> float:
    dx = float(poi.get("x") or 0.0) - float(pref["x"])
    dy = float(poi.get("y") or 0.0) - float(pref["y"])
    return math.hypot(dx, dy)


def _apply_pos(poi: dict[str, Any], pref: dict[str, Any]) -> bool:
    """Copy world XYZ (+ tile/zone when useful). Returns True if XYZ changed."""
    dz = abs(float(poi.get("z") or 0.0) - float(pref["z"]))
    changed = _pos_delta(poi, pref) > _EPS or dz > _EPS
    if changed:
        poi["x"] = pref["x"]
        poi["y"] = pref["y"]
        poi["z"] = pref["z"]
    if pref.get("source_tile"):
        poi["source_tile"] = pref["source_tile"]
    if pref.get("zone") and not poi.get("zone"):
        poi["zone"] = pref["zone"]
    # Prefer non-empty prefab source when the row has none — but never copy a
    # child prefab path onto an activity root (activities keep source empty).
    if (
        pref.get("source")
        and not poi.get("source")
        and str(poi.get("kind") or "").strip().lower() != "activity"
    ):
        poi["source"] = pref["source"]
    return changed


def collect_prefab_data() -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, list[dict[str, Any]]],
]:
    """Return (by_id, activity_roots, activity_id → child records)."""
    by_id: dict[str, dict[str, Any]] = {}
    activity_roots: dict[str, dict[str, Any]] = {}
    activity_children: dict[str, list[dict[str, Any]]] = {}

    for path in sorted(PREFAB_DIR.glob("*.prefab")):
        try:
            doc = read_hbson(path.read_bytes())
        except HbsonError as exc:
            print(f"skip {path.name}: {exc}", file=sys.stderr)
            continue
        tile = path.stem

        def visit(
            node: dict[str, Any],
            ox: float,
            oy: float,
            oz: float,
            rot: float,
            parent_activity: str | None,
        ) -> None:
            lx = float(node.get("x") or 0.0)
            ly = float(node.get("y") or 0.0)
            lz = float(node.get("z") or 0.0)
            # Tree walk stays on Heaps offsets (Orb/Camp + nested ids).
            dx, dy = _heaps_offset(lx, ly, rot)
            x = ox + dx
            y = oy + dy
            z = oz + lz

            props = node.get("props")
            props_d = props if isinstance(props, dict) else {}
            nid = props_d.get("id")
            source = node.get("source") if isinstance(node.get("source"), str) else ""
            zone = props_d.get("zoneBaked")
            zone_s = zone if isinstance(zone, str) else None
            name = props_d.get("name") or node.get("name")
            # Live FightStone chests use standard rotationZ on this child only.
            if source == _FIGHT_STONE_SOURCE:
                sdx, sdy = _standard_offset(lx, ly, rot)
                rec_x, rec_y = ox + sdx, oy + sdy
            else:
                rec_x, rec_y = x, y
            rec = {
                "x": round4(rec_x),
                "y": round4(rec_y),
                "z": round4(z),
                "source_tile": tile,
                "zone": zone_s,
                "source": source,
                "name": name if isinstance(name, str) else None,
                "id": nid if isinstance(nid, str) else None,
            }
            if isinstance(nid, str) and nid:
                by_id[nid] = rec

            activity_id = parent_activity
            if props_d.get("$cdbtype") == "activity" and isinstance(nid, str) and nid:
                activity_id = nid
                activity_roots[nid] = dict(rec)
                activity_children.setdefault(nid, [])

            if activity_id and activity_id != (nid if isinstance(nid, str) else None):
                # Record every descendant; anchors are chosen later by source.
                if source or nid:
                    activity_children.setdefault(activity_id, []).append(dict(rec))

            child_rot = rot + float(node.get("rotationZ") or 0.0)
            for child_node in node.get("children") or []:
                if isinstance(child_node, dict):
                    visit(child_node, x, y, z, child_rot, activity_id)

        for child in doc["root"].get("children") or []:
            if isinstance(child, dict):
                visit(child, 0.0, 0.0, 0.0, 0.0, None)

    return by_id, activity_roots, activity_children


def pick_activity_anchor(
    subkind: str,
    activity_id: str,
    root: dict[str, Any] | None,
    children: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Gameplay spot for the map marker, or None to keep / use the activity root."""
    sources = _ACTIVITY_ANCHOR_SOURCES.get(subkind)
    if not sources:
        return root
    for source in sources:
        hits = [child for child in children if child.get("source") == source]
        if not hits:
            continue
        if len(hits) == 1 or root is None:
            return hits[0]
        # Prefer the child nearest the authored activity root when several match.
        return min(
            hits,
            key=lambda child: math.hypot(
                float(child["x"]) - float(root["x"]),
                float(child["y"]) - float(root["y"]),
            ),
        )
    print(
        f"warn: no {sources[0].rsplit('/', 1)[-1]} child for {activity_id}",
        file=sys.stderr,
    )
    return root


def main() -> int:
    if not PREFAB_DIR.is_dir():
        print(f"missing prefab dir: {PREFAB_DIR}", file=sys.stderr)
        return 1
    if not OUT_PATH.is_file():
        print(f"missing POI table: {OUT_PATH}", file=sys.stderr)
        return 1

    pois: list[dict[str, Any]] = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(pois, list):
        print("pois file must be a JSON array", file=sys.stderr)
        return 1

    by_id, activity_roots, activity_children = collect_prefab_data()
    fixed = 0
    snapped = 0
    matched = 0
    added = 0
    unmatched: list[str] = []

    # 1) Patch non-activity POI rows whose id exists in prefabs.
    for poi in pois:
        pid = poi.get("id")
        if not isinstance(pid, str) or not pid:
            continue
        if str(poi.get("kind") or "").strip().lower() == "activity":
            continue
        pref = by_id.get(pid)
        if pref is None:
            unmatched.append(pid)
            continue
        matched += 1
        old = (poi.get("x"), poi.get("y"), poi.get("z"))
        if _apply_pos(poi, pref):
            print(f"fix {pid}: {old} -> ({pref['x']}, {pref['y']}, {pref['z']})")
            fixed += 1

    # 2) Place every activity on its gameplay anchor (or prefab root).
    for poi in pois:
        if str(poi.get("kind") or "").strip().lower() != "activity":
            continue
        aid = poi.get("id")
        if not isinstance(aid, str) or not aid:
            continue
        matched += 1
        sub = str(poi.get("subkind") or "").strip().lower()
        root = activity_roots.get(aid) or by_id.get(aid)
        children = activity_children.get(aid) or []
        anchor = pick_activity_anchor(sub, aid, root, children)
        if anchor is None:
            unmatched.append(aid)
            print(f"warn: activity {aid} missing from prefabs", file=sys.stderr)
            continue
        old = (poi.get("x"), poi.get("y"), poi.get("z"))
        moved = _apply_pos(poi, anchor)
        # Activity rows are markers, not prefab instances — keep source empty.
        source_cleared = bool(poi.get("source"))
        poi["source"] = ""
        if not moved and not source_cleared:
            continue
        via = anchor.get("id") or (anchor.get("source") or "").rsplit("/", 1)[-1] or "root"
        label = "snap" if sub in _ACTIVITY_ANCHOR_SOURCES else "fix"
        if moved:
            print(
                f"{label} {aid} ({poi.get('name')}): {old} -> "
                f"({anchor['x']}, {anchor['y']}, {anchor['z']}) via {via}"
            )
            if label == "snap":
                snapped += 1
            else:
                fixed += 1
        elif source_cleared:
            fixed += 1

    # 3) Upsert Orb/Camp/Vault chests that exist in prefabs but not the table.
    poi_ids = {p.get("id") for p in pois if isinstance(p.get("id"), str)}
    for nid, pref in sorted(by_id.items()):
        source = pref.get("source") or ""
        if source not in _ACTIVITY_CHEST_SOURCES and source != _VAULT_CHEST_SOURCE:
            continue
        if nid in poi_ids:
            continue
        name = pref.get("name") if isinstance(pref.get("name"), str) else "Chest"
        pois.append(
            {
                "kind": "chest",
                "subkind": None,
                "name": name,
                "id": nid,
                "zone": pref.get("zone"),
                "x": pref["x"],
                "y": pref["y"],
                "z": pref["z"],
                "source": source,
                "source_tile": pref.get("source_tile"),
            }
        )
        poi_ids.add(nid)
        added += 1
        print(f"add chest {nid} @ ({pref['x']}, {pref['y']}, {pref['z']})")

    changed = fixed + snapped + added
    shipped = [_ship_poi(poi) if isinstance(poi, dict) else poi for poi in pois]
    OUT_PATH.write_text(
        json.dumps(shipped, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    if changed:
        print(
            f"wrote {OUT_PATH.relative_to(ROOT)}: matched={matched} fixed={fixed} "
            f"snapped={snapped} added={added} unmatched_ids={len(unmatched)} "
            f"prefab_ids={len(by_id)}"
        )
    else:
        print(
            f"rewrote ship form {OUT_PATH.relative_to(ROOT)}: matched={matched} "
            f"fixed=0 snapped=0 added=0 unmatched_ids={len(unmatched)} "
            f"prefab_ids={len(by_id)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
