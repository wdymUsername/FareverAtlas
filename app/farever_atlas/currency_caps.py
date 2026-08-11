"""Resolve live currency caps from CastleDB-derived assets + bridge counters."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import CURRENCY_CAPS_RELATIVE_PATH, discover_project_asset


def _caps_path() -> Path | None:
    return discover_project_asset(CURRENCY_CAPS_RELATIVE_PATH)


@lru_cache(maxsize=1)
def load_currency_caps() -> dict[str, dict[str, Any]]:
    path = _caps_path()
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(kind): entry
        for kind, entry in payload.items()
        if isinstance(kind, str) and isinstance(entry, dict)
    }


def resolve_currency_max(
    kind: str,
    counters: dict[str, int] | None = None,
) -> int | None:
    """Return the current cap for ``kind``, or None when uncapped / unknown."""
    entry = load_currency_caps().get(kind)
    if not entry:
        return None
    if "max" in entry:
        try:
            return int(entry["max"])
        except (TypeError, ValueError):
            return None
    tiers = entry.get("max_tiers")
    if not isinstance(tiers, list) or not tiers:
        return None
    counter_name = entry.get("capacity_counter")
    index = 0
    if isinstance(counter_name, str) and counters:
        try:
            index = int(counters.get(counter_name, 0) or 0)
        except (TypeError, ValueError):
            index = 0
    index = max(0, min(index, len(tiers) - 1))
    try:
        return int(tiers[index])
    except (TypeError, ValueError, IndexError):
        return None


def enrich_currencies(
    currencies: list[Any],
    counters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Attach resolved ``max`` onto bridge currency rows."""
    normalized_counters: dict[str, int] = {}
    if isinstance(counters, dict):
        for key, value in counters.items():
            try:
                normalized_counters[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
    out: list[dict[str, Any]] = []
    for entry in currencies or []:
        if not isinstance(entry, dict) or entry.get("kind") is None:
            continue
        kind = str(entry.get("kind"))
        try:
            amount = int(entry.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0
        row: dict[str, Any] = {"kind": kind, "amount": amount}
        maximum = resolve_currency_max(kind, normalized_counters)
        if maximum is not None:
            row["max"] = maximum
        out.append(row)
    return out
