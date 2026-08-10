"""Static wild-critter spawn points extracted from world prefabs.

Source of truth: ``assets/data/w1_siagarta/critter_spawns.json``, rebuilt with
``python tools/extract_critter_spawns.py``. These are authored spawner
positions (and roaming pools), not live streamed entities.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .config import ASSET_ROOT, CRITTER_SPAWNS_RELATIVE_PATH

_SPAWNS_FILE = ASSET_ROOT / CRITTER_SPAWNS_RELATIVE_PATH


@lru_cache(maxsize=1)
def critter_spawns() -> tuple[dict[str, Any], ...]:
    path = _SPAWNS_FILE
    if not path.is_file():
        return ()
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return ()
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("spawns") or []
    else:
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, dict))
