"""Companion / Spark kind lists from CastleDB `unit` traits.

Mirrors `usefull/BrudrbearFareverMeter/analysis_out/unit_traits.json`.
Critters are `ent.Foe` at runtime; classify by kind id, not HL class.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .config import ASSET_ROOT

_TRAITS_FILE = ASSET_ROOT / "unit_traits.json"


@lru_cache(maxsize=1)
def _load_traits() -> tuple[frozenset[str], frozenset[str]]:
    path = _TRAITS_FILE
    if not path.is_file():
        return frozenset(), frozenset()
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return frozenset(), frozenset()
    if not isinstance(payload, dict):
        return frozenset(), frozenset()
    critter = payload.get("critter") or []
    spark = payload.get("spark") or []
    critter_kinds = frozenset(
        str(item) for item in critter if isinstance(item, str) and item
    )
    spark_kinds = frozenset(
        str(item) for item in spark if isinstance(item, str) and item
    )
    return critter_kinds, spark_kinds


def critter_kinds() -> frozenset[str]:
    return _load_traits()[0]


def spark_kinds() -> frozenset[str]:
    return _load_traits()[1]


def is_critter_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return kind in critter_kinds()


def is_spark_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return kind in spark_kinds()
