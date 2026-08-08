"""User-drawn custom fog-of-war clear borders (line-tool polygons)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...config import PROJECT_ROOT

CUSTOM_FOW_DIR = PROJECT_ROOT / "user_data" / "map"
CUSTOM_FOW_FILE_NAME = "custom_fow_siagarta.json"
CUSTOM_FOW_PATH = CUSTOM_FOW_DIR / CUSTOM_FOW_FILE_NAME


def custom_fow_path() -> Path:
    return CUSTOM_FOW_PATH


def load_custom_fow_rings(path: Path | None = None) -> list[list[tuple[float, float]]]:
    target = path or CUSTOM_FOW_PATH
    if not target.is_file():
        return []
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rings_out: list[list[tuple[float, float]]] = []
    for ring in doc.get("rings") or []:
        if not isinstance(ring, list) or len(ring) < 3:
            continue
        pts: list[tuple[float, float]] = []
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


def save_custom_fow_rings(
    rings: list[list[tuple[float, float]]] | tuple[tuple[tuple[float, float], ...], ...],
    path: Path | None = None,
) -> bool:
    target = path or CUSTOM_FOW_PATH
    payload: dict[str, Any] = {
        "world": "w1_siagarta",
        "schema": 1,
        "source": "user-line-tool",
        "rings": [
            [[round(float(x), 3), round(float(y), 3)] for x, y in ring]
            for ring in rings
            if len(ring) >= 3
        ],
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True
