"""Stream-aligned map cull ceilings and defaults.

Maxima match native_bridge / game interest bounds so Settings cannot ask for
data the live feed will never contain. ``0`` means Off (no extra Atlas filter)
where noted in settings keys.
"""

from __future__ import annotations

# Enemy + critter stream (bridge re-culls enemies; critters are game-streamed).
ENEMY_XY_MAX_M = 500
ENEMY_Z_MAX_M = 120
CRITTER_XY_MAX_M = 500
CRITTER_Z_MAX_M = 120

# Interactibles / NODE GUIDE.
LOOT_XY_MAX_M = 500
LOOT_Z_MAX_M = 160

# Patrol path claim vs live units.
PATROL_XY_MAX_M = 500
PATROL_Z_MAX_M = 120
PATROL_LEASH_MAX_M = 200

# Defaults preserve pre-settings hardcodes.
DEFAULT_ENEMY_XY_M = 500
DEFAULT_ENEMY_Z_M = 30
DEFAULT_CRITTER_XY_M = 500
DEFAULT_CRITTER_Z_M = 30
DEFAULT_PATROL_XY_M = 500
DEFAULT_PATROL_Z_M = 120
DEFAULT_PATROL_LEASH_M = 65
DEFAULT_LOOT_XY_M = 500
DEFAULT_LOOT_Z_M = 160

CULL_SETTING_KEYS: dict[str, tuple[int, int, int]] = {
    # key -> (default, min, max)
    "map/cull/enemy_xy_m": (DEFAULT_ENEMY_XY_M, 0, ENEMY_XY_MAX_M),
    "map/cull/enemy_z_m": (DEFAULT_ENEMY_Z_M, 0, ENEMY_Z_MAX_M),
    "map/cull/critter_xy_m": (DEFAULT_CRITTER_XY_M, 0, CRITTER_XY_MAX_M),
    "map/cull/critter_z_m": (DEFAULT_CRITTER_Z_M, 0, CRITTER_Z_MAX_M),
    "map/cull/patrol_xy_m": (DEFAULT_PATROL_XY_M, 1, PATROL_XY_MAX_M),
    "map/cull/patrol_z_m": (DEFAULT_PATROL_Z_M, 0, PATROL_Z_MAX_M),
    "map/cull/patrol_leash_m": (DEFAULT_PATROL_LEASH_M, 1, PATROL_LEASH_MAX_M),
    "map/cull/loot_xy_m": (DEFAULT_LOOT_XY_M, 1, LOOT_XY_MAX_M),
    "map/cull/loot_z_m": (DEFAULT_LOOT_Z_M, 1, LOOT_Z_MAX_M),
}


def clamp_cull_value(key: str, value: int) -> int:
    """Clamp a stored cull setting to its allowed range."""
    default, minimum, maximum = CULL_SETTING_KEYS[key]
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def cull_setting(settings: object, key: str) -> int:
    """Read and clamp a cull int from QSettings-like ``value`` API."""
    default, _minimum, _maximum = CULL_SETTING_KEYS[key]
    raw = settings.value(key, default)  # type: ignore[attr-defined]
    try:
        number = int(raw)
    except (TypeError, ValueError):
        number = default
    return clamp_cull_value(key, number)
