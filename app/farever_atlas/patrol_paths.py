"""Static patrol polylines for ranked/spark and wild-critter spawners.

Source of truth: ``assets/data/w1_siagarta/patrol_paths.json``, rebuilt with
``python tools/extract_patrol_paths.py``. Paths are authored map splines;
the map only draws them when a live enemy/critter is associated.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .config import ASSET_ROOT, PATROL_PATHS_RELATIVE_PATH

_PATHS_FILE = ASSET_ROOT / PATROL_PATHS_RELATIVE_PATH


@lru_cache(maxsize=1)
def patrol_paths() -> tuple[dict[str, Any], ...]:
    path = _PATHS_FILE
    if not path.is_file():
        return ()
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return ()
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("paths") or []
    else:
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, dict))


@lru_cache(maxsize=1)
def patrol_paths_by_kind() -> dict[str, tuple[dict[str, Any], ...]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for path in patrol_paths():
        kinds = path.get("kinds") if isinstance(path.get("kinds"), list) else []
        for kind in kinds:
            if not isinstance(kind, str) or not kind:
                continue
            index.setdefault(kind, []).append(path)
    return {kind: tuple(paths) for kind, paths in index.items()}
