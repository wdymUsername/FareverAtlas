"""Per-layer FOW geometry overrides (user point-edit results)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ...config import PROJECT_ROOT

FOW_OVERRIDES_DIR = PROJECT_ROOT / "user_data" / "map"
FOW_OVERRIDES_PATH = FOW_OVERRIDES_DIR / "fow_overrides_siagarta.json"

Ring = list[tuple[float, float]]
Rings = list[Ring]


def fow_overrides_path() -> Path:
    return FOW_OVERRIDES_PATH


def _parse_rings(raw: Any) -> Rings:
    rings_out: Rings = []
    if not isinstance(raw, list):
        return rings_out
    for ring in raw:
        if not isinstance(ring, list) or len(ring) < 3:
            continue
        pts: Ring = []
        for pt in ring:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            try:
                pts.append((float(pt[0]), float(pt[1])))
            except (TypeError, ValueError):
                continue
        if len(pts) >= 3:
            rings_out.append(pts)
    return rings_out


def load_fow_overrides(
    path: Path | None = None,
) -> dict[str, tuple[tuple[tuple[float, float], ...], ...]]:
    target = path or FOW_OVERRIDES_PATH
    if not target.is_file():
        return {}
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw_layers = doc.get("layers") if isinstance(doc, dict) else None
    if not isinstance(raw_layers, dict):
        return {}
    out: dict[str, tuple[tuple[tuple[float, float], ...], ...]] = {}
    for key, entry in raw_layers.items():
        layer = str(key).strip()
        if not layer:
            continue
        rings_raw = entry.get("rings") if isinstance(entry, dict) else entry
        rings = _parse_rings(rings_raw)
        # Empty ring lists are valid (explicit clear of baked geometry).
        if isinstance(rings_raw, list) or rings:
            out[layer] = tuple(tuple(ring) for ring in rings)
    return out


def save_fow_overrides(
    layers: dict[str, tuple[tuple[tuple[float, float], ...], ...] | list[list[tuple[float, float]]]],
    path: Path | None = None,
) -> bool:
    target = path or FOW_OVERRIDES_PATH
    payload: dict[str, Any] = {
        "world": "w1_siagarta",
        "schema": 1,
        "source": "fow-point-edit",
        "layers": {},
    }
    for key, rings in layers.items():
        cleaned = [
            [[round(float(x), 3), round(float(y), 3)] for x, y in ring]
            for ring in rings
            if len(ring) >= 3
        ]
        # Persist empty overrides so a Cleared layer does not revive asset rings.
        payload["layers"][str(key)] = {"rings": cleaned}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


def simplify_ring(
    ring: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    *,
    max_points: int = 64,
    min_dist: float = 2.0,
) -> list[tuple[float, float]]:
    """Decimate a closed ring for editable point counts."""
    pts = [(float(x), float(y)) for x, y in ring]
    if len(pts) < 3:
        return pts
    # Drop near-duplicate consecutive points.
    spaced: list[tuple[float, float]] = [pts[0]]
    min_sq = min_dist * min_dist
    for point in pts[1:]:
        ox, oy = spaced[-1]
        if (point[0] - ox) ** 2 + (point[1] - oy) ** 2 >= min_sq:
            spaced.append(point)
    if len(spaced) >= 3:
        pts = spaced
    if len(pts) <= max_points:
        return pts
    # Even stride sample, always keep first point; ensure closed-ish count >= 3.
    step = max(1, int(math.ceil(len(pts) / float(max_points))))
    sampled = pts[::step]
    if sampled[0] != pts[0]:
        sampled.insert(0, pts[0])
    if len(sampled) < 3:
        return pts[:max_points]
    if len(sampled) > max_points:
        sampled = sampled[:max_points]
    return sampled


def simplify_rings(
    rings: list[list[tuple[float, float]]] | tuple[tuple[tuple[float, float], ...], ...],
    *,
    max_points: int = 64,
    min_dist: float = 2.0,
) -> list[list[tuple[float, float]]]:
    return [
        simplify_ring(ring, max_points=max_points, min_dist=min_dist)
        for ring in rings
        if len(ring) >= 3
    ]
