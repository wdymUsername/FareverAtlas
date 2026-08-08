#!/usr/bin/env python3
"""Rebuild assets/map/w1_siagarta_fow.json clear-hole layers from mogshapes.

Toggleable Z1–Z4 layers are edited in-app (move / stretch / invert). Custom FOW
borders live under user_data/map/custom_fow_siagarta.json and are ignored while
any tier layer is enabled.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZONE_DIR = ROOT / "extracted/res.map/Level/World/W1_Siagarta.dat/minimap/zones"
POI_PATH = ROOT / "assets/pois_W1_Siagarta.json"
OUT_JSON = ROOT / "assets/map/w1_siagarta_fow.json"
PATTERN_SRC = ROOT / "extracted/res/UI/Map/Pattern_fog_of_war_512.png"
PATTERN_DST = ROOT / "assets/map/pattern_fog_of_war_512.png"

REGIONS = (
    ("Z1_Primevalley", "Primevalley", "Z1"),
    ("Z1_Honeywoods", "Honeywoods", "Z1"),
    ("Z1_Meridion", "Meridion", "Z1"),
    ("Z1_Enripit", "Enripit", "Z1"),
    ("Z1_Bel_Etir", "Bel Etir", "Z1"),
    ("Z1_Slime", "Slime Island", "Z1"),
    ("Z2_Azuram", "Azuram", "Z2"),
    ("Z2_Krisomal", "Krisomal", "Z2"),
    ("Z2_Nescent", "Nescent", "Z2"),
    ("Z2_Eksod", "Eksod", "Z2"),
    ("CrimsonIsland_Region", "Crimson Island", "Z3"),
    ("Z4_Ebral", "Ebral", "Z4"),
)


def parse_rings(path: Path) -> list[list[tuple[int, int]]]:
    body = path.read_text(errors="ignore")
    ring: list[tuple[int, int]] = []
    rings: list[list[tuple[int, int]]] = []
    idx = 0
    for match in re.finditer(r"(?:xi|R1i)(-?\d+)(?:yi|R2i)(-?\d+)", body):
        chunk = body[idx : match.start()]
        if "ha" in chunk and ring:
            rings.append(ring)
            ring = []
        ring.append((int(match.group(1)), int(match.group(2))))
        idx = match.end()
    if ring:
        rings.append(ring)
    return [item for item in rings if len(item) >= 3]


def simplify(
    ring: list[tuple[int, int]], *, min_dist: float = 1.5
) -> list[tuple[int, int]]:
    if len(ring) < 4:
        return ring
    out = [ring[0]]
    for point in ring[1:]:
        ox, oy = out[-1]
        if (point[0] - ox) ** 2 + (point[1] - oy) ** 2 >= min_dist * min_dist:
            out.append(point)
    return out if len(out) >= 3 else ring


def linreg(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    count = len(xs)
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs) or 1.0
    scale = num / den
    offset = mean_y - scale * mean_x
    return scale, offset


def main() -> None:
    pois = json.loads(POI_PATH.read_text(encoding="utf-8"))
    pairs_x: list[tuple[float, float]] = []
    pairs_y: list[tuple[float, float]] = []
    for shape in sorted(ZONE_DIR.glob("*.mogshape")):
        zone_pois = [poi for poi in pois if poi.get("zone") == shape.stem]
        if len(zone_pois) < 5:
            continue
        rings = parse_rings(shape)
        if not rings:
            continue
        pts = [point for ring in rings for point in ring]
        shape_xs = [point[0] for point in pts]
        shape_ys = [point[1] for point in pts]
        world_xs = [float(poi["x"]) for poi in zone_pois]
        world_ys = [float(poi["y"]) for poi in zone_pois]
        pairs_x.append(
            (
                (min(world_xs) + max(world_xs)) / 2.0,
                (min(shape_xs) + max(shape_xs)) / 2.0,
            )
        )
        pairs_y.append(
            (
                (min(world_ys) + max(world_ys)) / 2.0,
                (min(shape_ys) + max(shape_ys)) / 2.0,
            )
        )

    scale_x, offset_x = linreg(pairs_x)
    scale_y, offset_y = linreg(pairs_y)
    inv_sx = 1.0 / scale_x
    inv_sy = 1.0 / scale_y

    def to_world(x: float, y: float) -> tuple[float, float]:
        return (x - offset_x) * inv_sx, (y - offset_y) * inv_sy

    regions = []
    # Preserve the release Baked clear zone across mogshape rebuilds.
    if OUT_JSON.is_file():
        try:
            old_doc = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old_doc = {}
        for entry in old_doc.get("regions") or []:
            if isinstance(entry, dict) and str(entry.get("id") or "") == "Baked":
                regions.append(entry)
                print("kept Baked release region")
                break

    for stem, label, tier in REGIONS:
        path = ZONE_DIR / f"{stem}.mogshape"
        if not path.is_file():
            print(f"missing {stem}")
            continue
        world_rings = []
        for ring in parse_rings(path):
            simplified = simplify(ring)
            world_rings.append(
                [
                    [round(wx, 2), round(wy, 2)]
                    for wx, wy in (to_world(x, y) for x, y in simplified)
                ]
            )
        regions.append(
            {
                "id": stem,
                "label": label,
                "tier": tier,
                "rings": world_rings,
            }
        )
        print(f"{stem}: {len(world_rings)} rings → {tier}")

    doc = {
        "world": "w1_siagarta",
        "schema": 1,
        "source": "mogshape",
        "shape_to_world": {
            "scale_x": scale_x,
            "offset_x": offset_x,
            "scale_y": scale_y,
            "offset_y": offset_y,
        },
        "note": (
            "Baked is the release FOW clear zone. Z1–Z4 are --dev edit layers; "
            "Z0 is user custom FOW."
        ),
        "defaults": {
            "enabled": True,
            "accessible_tiers": ["Baked"],
            "show_outlines": False,
        },
        "regions": regions,
    }
    OUT_JSON.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    if PATTERN_SRC.is_file():
        shutil.copy2(PATTERN_SRC, PATTERN_DST)
        print(f"copied {PATTERN_DST}")


if __name__ == "__main__":
    main()
