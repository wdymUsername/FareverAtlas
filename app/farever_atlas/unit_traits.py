"""CastleDB `unit` trait kind lists for map classification.

Source: ``assets/unit_traits.json`` (rebuild with ``tools/extract_unit_traits.py``).
Critters / specials / Spark rares are still ``ent.Foe`` at runtime; classify by
kind id, not HashLink class.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .config import ASSET_ROOT

_TRAITS_FILE = ASSET_ROOT / "unit_traits.json"

_TraitSets = tuple[
    frozenset[str],
    frozenset[str],
    frozenset[str],
    frozenset[str],
    frozenset[str],
    frozenset[str],
]


def _kind_set(payload: dict[str, Any], key: str) -> frozenset[str]:
    raw = payload.get(key) or []
    return frozenset(str(item) for item in raw if isinstance(item, str) and item)


@lru_cache(maxsize=1)
def _load_traits() -> _TraitSets:
    path = _TRAITS_FILE
    if not path.is_file():
        empty: frozenset[str] = frozenset()
        return empty, empty, empty, empty, empty, empty
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        empty = frozenset()
        return empty, empty, empty, empty, empty, empty
    if not isinstance(payload, dict):
        empty = frozenset()
        return empty, empty, empty, empty, empty, empty
    return (
        _kind_set(payload, "critter"),
        _kind_set(payload, "spark"),
        _kind_set(payload, "elite"),
        _kind_set(payload, "boss"),
        _kind_set(payload, "miniboss"),
        _kind_set(payload, "unique"),
    )


def critter_kinds() -> frozenset[str]:
    return _load_traits()[0]


def spark_kinds() -> frozenset[str]:
    return _load_traits()[1]


def elite_kinds() -> frozenset[str]:
    return _load_traits()[2]


def boss_kinds() -> frozenset[str]:
    return _load_traits()[3]


def miniboss_kinds() -> frozenset[str]:
    return _load_traits()[4]


def unique_kinds() -> frozenset[str]:
    return _load_traits()[5]


def is_critter_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return kind in critter_kinds()


def is_spark_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return kind in spark_kinds()


def is_elite_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return kind in elite_kinds()


def is_boss_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return kind in boss_kinds()


def is_miniboss_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return kind in miniboss_kinds()


def is_unique_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return kind in unique_kinds()
