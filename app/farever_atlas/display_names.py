"""CastleDB in-game display labels for map tooltips.

Source of truth: ``assets/display_names.json``, rebuilt with
``python tools/extract_display_names.py``.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .config import ASSET_ROOT

_NAMES_FILE = ASSET_ROOT / "display_names.json"
_SIZE_TOKENS = ("Small", "Medium", "Large", "Big")

# Prefab / Element.kind tokens → in-game chest labels.
_CHEST_TYPE_LABELS = {
    "worldchest": "World Chest",
    "recipechest": "Recipe Chest",
    "orbchest": "Orb Chest",
    "chestorb": "Orb Chest",  # live/static zone ids: …ChestOrb_N_Chest
    "vaultchest": "Vault Chest",
    "campchest": "Camp Chest",
}

# Shown under the Activities POI chip, not the Chests loot chip.
# Include both prefab stems (OrbChest) and zone-id stems (ChestOrb / Camp_N_Chest).
_ACTIVITY_CHEST_KEYS = frozenset(
    {"orbchest", "chestorb", "campchest", "vaultchest"}
)
_ACTIVITY_CAMP_CHEST_RE = re.compile(r"camp\d*chest")


@lru_cache(maxsize=1)
def _payload() -> dict[str, Any]:
    path = _NAMES_FILE
    if not path.is_file():
        return {}
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def split_ident(value: str) -> str:
    text = value.replace("_", " ").strip()
    if not text:
        return ""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    return " ".join(part for part in text.split() if part and part.lower() != "generic")


def size_from_id(node_id: str) -> str | None:
    for token in _SIZE_TOKENS:
        if node_id.endswith(f"_{token}") or node_id == token:
            return "Large" if token == "Big" else token
    return None


def unit_label(kind: str | None) -> dict[str, Any] | None:
    if not kind:
        return None
    units = _payload().get("units")
    if not isinstance(units, dict):
        return None
    entry = units.get(kind)
    return entry if isinstance(entry, dict) else None


def gatherable_label(node_id: str | None) -> dict[str, Any] | None:
    if not node_id:
        return None
    gatherables = _payload().get("gatherables")
    if not isinstance(gatherables, dict):
        return None
    entry = gatherables.get(node_id)
    return entry if isinstance(entry, dict) else None


def item_name(item_id: str | None) -> str | None:
    if not item_id:
        return None
    items = _payload().get("items")
    if not isinstance(items, dict):
        return None
    name = items.get(item_id)
    return name if isinstance(name, str) and name.strip() else None


def chest_label_from_id(node_id: str | None) -> str | None:
    """Map WorldChest / Recipe_Chest / long zone ids to in-game chest names."""
    if not node_id:
        return None
    chests = _payload().get("chests")
    if isinstance(chests, dict):
        direct = chests.get(node_id)
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        # Also allow compact keys like worldchest.
        compact_direct = chests.get(re.sub(r"[^a-z0-9]", "", node_id.lower()))
        if isinstance(compact_direct, str) and compact_direct.strip():
            return compact_direct.strip()

    compact = re.sub(r"[^a-z0-9]", "", node_id.lower())
    if not compact:
        return None
    best_key = ""
    for key in _CHEST_TYPE_LABELS:
        if key in compact and len(key) > len(best_key):
            best_key = key
    if best_key:
        return _CHEST_TYPE_LABELS[best_key]
    if compact == "chest":
        return "Chest"
    return None


def is_activity_linked_chest(*parts: str | None) -> bool:
    """True for Vault / Orb / Camp chests (activity loot, not world chests)."""
    cleaned = [str(part).strip() for part in parts if part and str(part).strip()]
    if not cleaned:
        return False

    # Ignore live pointer ids like 0x7ff… so they don't pollute token matching.
    meaningful = [
        part
        for part in cleaned
        if not re.fullmatch(r"0x[0-9a-fA-F]+", part)
    ]
    if not meaningful:
        return False

    compact = re.sub(r"[^a-z0-9]", "", " ".join(meaningful).lower())
    if any(key in compact for key in ("worldchest", "recipechest")):
        return False
    if any(key in compact for key in _ACTIVITY_CHEST_KEYS):
        return True
    # Live/static camp loot ids look like …Camp_3_Chest_1 (no CampChest stem).
    if _ACTIVITY_CAMP_CHEST_RE.search(compact):
        return True
    return False


def resolve_chest_label(*parts: str | None) -> str | None:
    """Best chest label from name / id / source (prefers Vault/Orb/Camp/World)."""
    cleaned = [str(part).strip() for part in parts if part and str(part).strip()]
    if not cleaned:
        return None
    best_key = ""
    best_label: str | None = None
    chests = _payload().get("chests")
    for part in cleaned:
        if isinstance(chests, dict):
            direct = chests.get(part)
            if isinstance(direct, str) and direct.strip() and direct.strip() != "Chest":
                return direct.strip()
            compact_key = re.sub(r"[^a-z0-9]", "", part.lower())
            mapped = chests.get(compact_key) if compact_key else None
            if isinstance(mapped, str) and mapped.strip() and mapped.strip() != "Chest":
                return mapped.strip()
        compact = re.sub(r"[^a-z0-9]", "", part.lower())
        for key, label in _CHEST_TYPE_LABELS.items():
            if key in compact and len(key) > len(best_key):
                best_key = key
                best_label = label
    if best_label:
        return best_label
    combined = re.sub(r"[^a-z0-9]", "", "".join(cleaned).lower())
    for key, label in _CHEST_TYPE_LABELS.items():
        if key in combined and len(key) > len(best_key):
            best_key = key
            best_label = label
    if best_label:
        return best_label
    # …Camp_3_Chest_1 zone ids (no CampChest stem).
    if _ACTIVITY_CAMP_CHEST_RE.search(combined):
        return "Camp Chest"
    if combined == "chest":
        return "Chest"
    return None


def format_unit_tooltip_name(kind: str | None, *, fallback: str | None = None) -> str:
    """Return the in-game unit display name (no level prefix)."""
    label = unit_label(kind)
    if label is not None:
        name = str(label.get("name") or "").strip()
        if name:
            return name
    if fallback and fallback.strip():
        return fallback.strip()
    if kind:
        pretty = split_ident(kind)
        if pretty:
            return pretty
    return "Enemy"


def unit_level(kind: str | None) -> int | None:
    label = unit_label(kind)
    if label is None:
        return None
    level = label.get("level")
    if isinstance(level, int) and level > 0:
        return level
    return None


def format_gatherable_tooltip_name(
    node_id: str | None,
    *,
    kind: str | None = None,
    size: str | None = None,
    fallback: str | None = None,
    source: str | None = None,
    item_id: str | None = None,
) -> str:
    """Return ``Copper Ore · Large`` / ``World Chest`` style labels."""
    kind_l = (kind or "").strip().lower()
    raw = (node_id or fallback or "").strip()

    # Chests: collapse long prefab ids (Z1_…_WorldChest_34) to World Chest.
    if kind_l == "chest" or "chest" in re.sub(r"[^a-z0-9]", "", raw.lower()):
        chest_name = resolve_chest_label(raw, fallback, source, item_id)
        if chest_name:
            return chest_name
        if kind_l == "chest":
            return "Chest"

    label = gatherable_label(node_id)
    resolved_size = ""
    if isinstance(size, str) and size.strip():
        resolved_size = size.strip().title()
        if resolved_size.lower() == "big":
            resolved_size = "Large"
    if label is not None:
        if not resolved_size:
            raw_size = label.get("size")
            if isinstance(raw_size, str) and raw_size.strip():
                resolved_size = raw_size.strip()
        item = str(label.get("item") or "").strip()
        if item and resolved_size:
            return f"{item} · {resolved_size}"
        if item:
            return item
        name = str(label.get("name") or "").strip()
        if name and resolved_size and resolved_size.lower() not in name.lower():
            return f"{name} · {resolved_size}"
        if name:
            return name

    if not raw:
        return (kind or "Node").title() if kind else "Node"
    if not resolved_size:
        resolved_size = size_from_id(raw) or ""
    # Ore_Copper_Large → prefer Copper Ore when item sheet has it.
    parts = [part for part in raw.split("_") if part]
    if len(parts) >= 2 and parts[0].lower() == "ore":
        material = parts[1]
        candidate = item_name(f"{material}Ore") or item_name(material) or split_ident(
            material + "Ore"
        )
        if candidate and resolved_size:
            return f"{candidate} · {resolved_size}"
        if candidate:
            return candidate
    pretty = split_ident(raw)
    for token in _SIZE_TOKENS:
        pretty = re.sub(rf"\b{token}\b", "", pretty, flags=re.IGNORECASE)
    pretty = " ".join(pretty.split())
    if pretty and resolved_size:
        return f"{pretty} · {resolved_size}"
    return pretty or resolved_size or (kind or "Node").title()
