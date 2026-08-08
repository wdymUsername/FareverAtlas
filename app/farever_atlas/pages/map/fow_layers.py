"""Persisted per-layer FOW state (enable / invert / align transform)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ...config import PROJECT_ROOT

FOW_LAYERS_DIR = PROJECT_ROOT / "user_data" / "map"
FOW_LAYERS_PATH = FOW_LAYERS_DIR / "fow_layers_siagarta.json"
LEGACY_Z4_TRANSFORM_PATH = FOW_LAYERS_DIR / "z4_transform_siagarta.json"

# Z0 = user custom FOW; Baked = release shipping clear zone; Z1–Z4 = --dev edit layers.
FOW_LAYER_ORDER = (
    "Baked",
    "Z0",
    "Z1_Primevalley",
    "Z1_Honeywoods",
    "Z1_Meridion",
    "Z1_Enripit",
    "Z1_Bel_Etir",
    "Z1_Slime",
    "Z2_Azuram",
    "Z2_Krisomal",
    "Z2_Nescent",
    "Z2_Eksod",
    "Z3",
    "Z4",
)

# Layers that ship / matter for release FOW (edit zones stay --dev tooling).
FOW_RELEASE_LAYERS = ("Baked",)

# Legacy ladder ceiling used by Settings → "Accessible through".
FOW_TIER_ORDER = ("Z1", "Z2", "Z3")

FOW_LAYER_SHORT_LABELS = {
    "Baked": "Bake",
    "Z0": "Z0",
    "Z1_Primevalley": "Prim",
    "Z1_Honeywoods": "Hony",
    "Z1_Meridion": "Meri",
    "Z1_Enripit": "Enri",
    "Z1_Bel_Etir": "Bel",
    "Z1_Slime": "Slim",
    "Z2_Azuram": "Azur",
    "Z2_Krisomal": "Kris",
    "Z2_Nescent": "Nesc",
    "Z2_Eksod": "Eksd",
    "Z3": "Z3",
    "Z4": "Z4",
}

FOW_LAYER_LABELS = {
    "Baked": "Baked",
    "Z0": "Custom",
    "Z1_Primevalley": "Primevalley",
    "Z1_Honeywoods": "Honeywoods",
    "Z1_Meridion": "Meridion",
    "Z1_Enripit": "Enripit",
    "Z1_Bel_Etir": "Bel Etir",
    "Z1_Slime": "Slime Island",
    "Z2_Azuram": "Azuram",
    "Z2_Krisomal": "Krisomal",
    "Z2_Nescent": "Nescent",
    "Z2_Eksod": "Eksod",
    "Z3": "Crimson Island",
    "Z4": "Ebral",
}

_LEGACY_TIER_CHILDREN = {
    "Z1": (
        "Z1_Primevalley",
        "Z1_Honeywoods",
        "Z1_Meridion",
        "Z1_Enripit",
        "Z1_Bel_Etir",
        "Z1_Slime",
    ),
    "Z2": (
        "Z2_Azuram",
        "Z2_Krisomal",
        "Z2_Nescent",
        "Z2_Eksod",
    ),
}


def canonical_fow_layer(layer: str) -> str | None:
    """Return the canonical FOW_LAYER_ORDER key, or None if unknown."""
    raw = str(layer or "").strip()
    if not raw:
        return None
    upper = raw.upper()
    for key in FOW_LAYER_ORDER:
        if key.upper() == upper:
            return key
    return None


@dataclass
class FowLayerTransform:
    """Scale about (ox, oy), then translate by (tx, ty) in world metres."""

    tx: float = 0.0
    ty: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    ox: float = 0.0
    oy: float = 0.0

    def is_identity(self, *, eps: float = 1e-9) -> bool:
        return (
            abs(self.tx) <= eps
            and abs(self.ty) <= eps
            and abs(self.sx - 1.0) <= eps
            and abs(self.sy - 1.0) <= eps
        )

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (
            (x - self.ox) * self.sx + self.ox + self.tx,
            (y - self.oy) * self.sy + self.oy + self.ty,
        )

    def inverse_apply(self, x: float, y: float) -> tuple[float, float]:
        return (
            (x - self.tx - self.ox) / self.sx + self.ox,
            (y - self.ty - self.oy) / self.sy + self.oy,
        )

    def key(self) -> tuple[float, float, float, float, float, float]:
        return (
            round(self.tx, 4),
            round(self.ty, 4),
            round(self.sx, 6),
            round(self.sy, 6),
            round(self.ox, 3),
            round(self.oy, 3),
        )


@dataclass
class FowLayerState:
    enabled: bool = False
    inverted: bool = False
    transform: FowLayerTransform = field(default_factory=FowLayerTransform)

    def key(self) -> tuple[Any, ...]:
        return (self.enabled, self.inverted, self.transform.key())


def _parse_transform(raw: dict[str, Any] | None) -> FowLayerTransform:
    doc = raw if isinstance(raw, dict) else {}
    try:
        return FowLayerTransform(
            tx=float(doc.get("tx", 0.0)),
            ty=float(doc.get("ty", 0.0)),
            sx=max(1e-4, float(doc.get("sx", 1.0))),
            sy=max(1e-4, float(doc.get("sy", 1.0))),
            ox=float(doc.get("ox", 0.0)),
            oy=float(doc.get("oy", 0.0)),
        )
    except (TypeError, ValueError):
        return FowLayerTransform()


def _state_from_entry(entry: dict[str, Any] | None) -> FowLayerState:
    if not isinstance(entry, dict):
        return FowLayerState()
    return FowLayerState(
        enabled=bool(entry.get("enabled", False)),
        inverted=bool(entry.get("inverted", False)),
        transform=_parse_transform(entry.get("transform") or entry),
    )


def _default_layers() -> dict[str, FowLayerState]:
    layers = {tier: FowLayerState() for tier in FOW_LAYER_ORDER}
    # Release shipping clear zone; edit/custom layers stay off until --dev.
    layers["Baked"] = FowLayerState(enabled=True)
    return layers


def load_fow_layers(path: Path | None = None) -> dict[str, FowLayerState]:
    layers = _default_layers()
    target = path or FOW_LAYERS_PATH
    if target.is_file():
        try:
            doc = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {}
        raw_layers = doc.get("layers") if isinstance(doc, dict) else None
        if isinstance(raw_layers, dict):
            for tier in FOW_LAYER_ORDER:
                entry = raw_layers.get(tier)
                if isinstance(entry, dict):
                    layers[tier] = _state_from_entry(entry)
            # Migrate legacy whole-tier Z1/Z2 entries onto their subzones.
            for parent, children in _LEGACY_TIER_CHILDREN.items():
                legacy = raw_layers.get(parent)
                if not isinstance(legacy, dict):
                    continue
                legacy_state = _state_from_entry(legacy)
                for child in children:
                    if child in raw_layers and isinstance(raw_layers.get(child), dict):
                        continue
                    layers[child] = FowLayerState(
                        enabled=legacy_state.enabled,
                        inverted=legacy_state.inverted,
                        transform=FowLayerTransform(
                            tx=legacy_state.transform.tx,
                            ty=legacy_state.transform.ty,
                            sx=legacy_state.transform.sx,
                            sy=legacy_state.transform.sy,
                            ox=legacy_state.transform.ox,
                            oy=legacy_state.transform.oy,
                        ),
                    )
    elif LEGACY_Z4_TRANSFORM_PATH.is_file():
        # Migrate older Z4-only transform file.
        try:
            legacy = json.loads(LEGACY_Z4_TRANSFORM_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            legacy = {}
        if isinstance(legacy, dict):
            layers["Z4"] = FowLayerState(
                enabled=False,
                inverted=False,
                transform=_parse_transform(legacy),
            )
    return layers


def save_fow_layers(
    layers: dict[str, FowLayerState], path: Path | None = None
) -> bool:
    target = path or FOW_LAYERS_PATH
    payload: dict[str, Any] = {
        "world": "w1_siagarta",
        "schema": 2,
        "source": "fow-layer-align",
        "layers": {},
    }
    for tier in FOW_LAYER_ORDER:
        state = layers.get(tier) or FowLayerState()
        xform = state.transform
        payload["layers"][tier] = {
            "enabled": bool(state.enabled),
            "inverted": bool(state.inverted),
            "transform": {
                key: round(float(value), 6) for key, value in asdict(xform).items()
            },
        }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


# Back-compat aliases used by older call sites.
Z4Transform = FowLayerTransform
load_z4_transform = lambda path=None: load_fow_layers(path)["Z4"].transform  # noqa: E731
save_z4_transform = lambda transform, path=None: save_fow_layers(  # noqa: E731
    {**load_fow_layers(path), "Z4": FowLayerState(transform=transform)}, path
)
