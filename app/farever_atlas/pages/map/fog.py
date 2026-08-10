"""Fog of war over inaccessible / unreleased map regions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import (
    FOW_PATTERN_RELATIVE_PATH,
    FOW_REGIONS_RELATIVE_PATH,
    PROJECT_ROOT,
    discover_project_asset,
)
from .custom_fow import load_custom_fow_rings, save_custom_fow_rings
from .fow_layers import (
    FOW_LAYER_LABELS,
    FOW_LAYER_ORDER,
    FOW_TIER_ORDER,
    FowLayerState,
    FowLayerTransform,
    canonical_fow_layer,
    load_fow_layers,
    save_fow_layers,
)
from .fow_overrides import (
    load_fow_overrides,
    save_fow_overrides,
)

# Soft FOW overlay is baked once into a map-aligned texture (release / Baked-only).
FOW_BAKED_OVERLAY_MAX_DIM = 2048
# Marker visibility is tested once per visible marker per frame, so the composite
# accessible path is rasterised once and probed by pixel instead.
FOW_ACCESSIBLE_MASK_MAX_DIM = 2048

# Soft edge width in world metres (blurred alpha after hard mask).
FOG_FEATHER_METRES = 20.0
# Cap native blur radius; larger feathers downsample then blur.
FOG_FEATHER_MAX_BLUR_PX = 40.0

# Independent toggleable FOW layers (Z1/Z2 subzones + Z3 + Z4).
FOW_LAYER_Z4 = "Z4"
FOW_TIER_LABELS = FOW_LAYER_LABELS

_OUTLINE_COLOR = QtGui.QColor(248, 246, 240, 220)
_CUSTOM_OUTLINE_COLOR = QtGui.QColor(72, 196, 255, 230)
_TIER_OUTLINE_COLORS = {
    "Z0": QtGui.QColor(72, 196, 255, 230),
    "Z1": QtGui.QColor(120, 220, 140, 230),
    "Z2": QtGui.QColor(120, 180, 255, 230),
    "Z3": QtGui.QColor(255, 140, 160, 230),
    "Z4": QtGui.QColor(255, 180, 72, 230),
}
_LAYER_OUTLINE_COLORS = {
    "Baked": QtGui.QColor(180, 220, 120, 230),
    "Z0": _TIER_OUTLINE_COLORS["Z0"],
    **{layer: _TIER_OUTLINE_COLORS["Z1"] for layer in FOW_LAYER_ORDER if layer.startswith("Z1_")},
    **{layer: _TIER_OUTLINE_COLORS["Z2"] for layer in FOW_LAYER_ORDER if layer.startswith("Z2_")},
    "Z3": _TIER_OUTLINE_COLORS["Z3"],
    "Z4": _TIER_OUTLINE_COLORS["Z4"],
}


@dataclass(frozen=True)
class FogRegion:
    id: str
    label: str
    tier: str
    rings: tuple[tuple[tuple[float, float], ...], ...]


@dataclass
class FogOfWar:
    """Inverted fog: fill the viewport, punch holes for accessible regions."""

    regions: tuple[FogRegion, ...] = ()
    enabled: bool = True
    show_outlines: bool = False
    # Zone (Z1–Z4) border overlays — debug/edit aid; leave off for normal play.
    show_layer_outlines: bool = False
    # Legacy ladder ceiling (settings); independent layer toggles are authoritative.
    max_tier: str = "Z3"
    layer_state: dict[str, FowLayerState] = field(default_factory=dict)
    hide_markers: bool = True
    feather_enabled: bool = True
    feather_metres: float = FOG_FEATHER_METRES
    # User line-tool clear holes (world metres); additive with zone layers.
    custom_rings: tuple[tuple[tuple[float, float], ...], ...] = ()
    # Point-edit overrides for baked layers (Z1+); Z0 uses custom_rings.
    layer_overrides: dict[str, tuple[tuple[tuple[float, float], ...], ...]] = field(
        default_factory=dict
    )
    _dirty_layers: set[str] = field(default_factory=set, repr=False, compare=False)
    _pattern: QtGui.QImage | None = field(default=None, repr=False)
    _pattern_brush: QtGui.QBrush | None = field(default=None, repr=False, compare=False)
    _world_accessible_path: QtGui.QPainterPath | None = field(
        default=None, repr=False, compare=False
    )
    _world_path_cache_key: int | None = field(
        default=None, repr=False, compare=False
    )
    _world_path_generation: int = field(default=0, repr=False, compare=False)
    _any_layer_key: int | None = field(default=None, repr=False, compare=False)
    _any_layer_value: bool = field(default=False, repr=False, compare=False)
    _soft_fog_image: QtGui.QImage | None = field(default=None, repr=False, compare=False)
    _soft_fog_cache_key: tuple[Any, ...] | None = field(
        default=None, repr=False, compare=False
    )
    _baked_overlay: QtGui.QImage | None = field(default=None, repr=False, compare=False)
    _baked_overlay_key: tuple[Any, ...] | None = field(
        default=None, repr=False, compare=False
    )
    _accessible_mask_key: int | None = field(default=None, repr=False, compare=False)
    _accessible_mask_bits: bytes | None = field(default=None, repr=False, compare=False)
    _accessible_mask_stride: int = field(default=0, repr=False, compare=False)
    _accessible_mask_geom: tuple[float, float, float, int, int] | None = field(
        default=None, repr=False, compare=False
    )
    _blur_effect: QtWidgets.QGraphicsBlurEffect | None = field(
        default=None, repr=False, compare=False
    )
    _blur_scene: QtWidgets.QGraphicsScene | None = field(
        default=None, repr=False, compare=False
    )
    _blur_item: QtWidgets.QGraphicsPixmapItem | None = field(
        default=None, repr=False, compare=False
    )

    @property
    def z4_layer_enabled(self) -> bool:
        return self.layer_enabled("Z4")

    @property
    def z4_inverted(self) -> bool:
        return self.layer_inverted("Z4")

    @property
    def z4_transform(self) -> FowLayerTransform:
        return self.layer_transform("Z4")

    @classmethod
    def load(cls, path: Path | None = None) -> "FogOfWar":
        asset = path or discover_project_asset(FOW_REGIONS_RELATIVE_PATH)
        if asset is None or not asset.is_file():
            return cls(enabled=False, show_outlines=False)
        try:
            doc = json.loads(asset.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(enabled=False, show_outlines=False)
        regions: list[FogRegion] = []
        for entry in doc.get("regions") or []:
            if not isinstance(entry, dict):
                continue
            rings_raw = entry.get("rings") or []
            rings: list[tuple[tuple[float, float], ...]] = []
            for ring in rings_raw:
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
                    rings.append(tuple(pts))
            if not rings:
                continue
            tier = str(entry.get("tier") or "").strip().upper() or "Z1"
            regions.append(
                FogRegion(
                    id=str(entry.get("id") or f"region_{len(regions)}"),
                    label=str(entry.get("label") or entry.get("id") or "Region"),
                    tier=tier,
                    rings=tuple(rings),
                )
            )
        defaults = doc.get("defaults") if isinstance(doc.get("defaults"), dict) else {}
        fog = cls(
            regions=tuple(regions),
            enabled=bool(defaults.get("enabled", True)),
            show_outlines=bool(defaults.get("show_outlines", False)),
            max_tier="Z3",
        )
        fog._load_pattern()
        fog.set_custom_rings(load_custom_fow_rings())
        fog.layer_overrides = load_fow_overrides()
        fog._init_layer_state(load_fow_layers())
        return fog

    def _canonical_layer(self, tier: str) -> str | None:
        return canonical_fow_layer(tier)

    def _layer(self, tier: str) -> FowLayerState:
        key = self._canonical_layer(tier) or str(tier).strip()
        if key not in self.layer_state:
            self.layer_state[key] = FowLayerState()
        return self.layer_state[key]

    def layer_enabled(self, tier: str) -> bool:
        return bool(self._layer(tier).enabled)

    def layer_inverted(self, tier: str) -> bool:
        return bool(self._layer(tier).inverted)

    @property
    def world_path_generation(self) -> int:
        """Bumped whenever the drawn shape of the fog changes.

        Callers that cache anything derived from the fog key it on this.
        """
        return self._world_path_generation

    def layer_transform(self, tier: str) -> FowLayerTransform:
        return self._layer(tier).transform

    def any_layer_enabled(self) -> bool:
        # Every marker hit-tests through here, and the per-tier lookup
        # canonicalises strings. Layer edits bump the generation counter.
        if self._any_layer_key != self._world_path_generation:
            self._any_layer_value = any(
                self.layer_enabled(tier) for tier in FOW_LAYER_ORDER
            )
            self._any_layer_key = self._world_path_generation
        return self._any_layer_value

    def enabled_layers(self) -> tuple[str, ...]:
        return tuple(tier for tier in FOW_LAYER_ORDER if self.layer_enabled(tier))

    def _regions_for_layer(self, tier: str) -> tuple[FogRegion, ...]:
        key = self._canonical_layer(tier) or str(tier).strip()
        by_id = tuple(
            region for region in self.regions if region.id.upper() == key.upper()
        )
        if by_id:
            return by_id
        # Z3/Z4 stay single tier-keyed layers (region id differs from layer key).
        if key in ("Z3", "Z4"):
            return tuple(
                region for region in self.regions if region.tier.upper() == key.upper()
            )
        return ()

    def _layer_centroid(self, tier: str) -> tuple[float, float]:
        xs: list[float] = []
        ys: list[float] = []
        for ring in self.source_rings(tier):
            for x, y in ring:
                xs.append(x)
                ys.append(y)
        if not xs:
            return 0.0, 0.0
        return sum(xs) / len(xs), sum(ys) / len(ys)

    def _init_layer_state(self, layers: dict[str, FowLayerState]) -> None:
        prepared: dict[str, FowLayerState] = {}
        for tier in FOW_LAYER_ORDER:
            state = layers.get(tier) or FowLayerState()
            ox, oy = self._layer_centroid(tier)
            xform = state.transform
            if xform.is_identity() and abs(xform.ox) <= 1e-9 and abs(xform.oy) <= 1e-9:
                xform = FowLayerTransform(ox=ox, oy=oy)
            elif abs(xform.ox) <= 1e-9 and abs(xform.oy) <= 1e-9:
                xform = FowLayerTransform(
                    tx=xform.tx,
                    ty=xform.ty,
                    sx=xform.sx,
                    sy=xform.sy,
                    ox=ox,
                    oy=oy,
                )
            prepared[tier] = FowLayerState(
                enabled=bool(state.enabled),
                inverted=bool(state.inverted),
                transform=xform,
            )
        self.layer_state = prepared
        self._invalidate_accessible_path()

    def _persist_layers(self) -> None:
        save_fow_layers(self.layer_state)

    def set_layer_enabled(self, tier: str, enabled: bool, *, persist: bool = True) -> None:
        key = self._canonical_layer(tier)
        if key is None:
            return
        state = self._layer(key)
        enabled = bool(enabled)
        if state.enabled == enabled:
            return
        state.enabled = enabled
        self._invalidate_accessible_path()
        if persist:
            self._persist_layers()

    def set_layer_inverted(self, tier: str, inverted: bool, *, persist: bool = True) -> None:
        key = self._canonical_layer(tier)
        if key is None:
            return
        state = self._layer(key)
        inverted = bool(inverted)
        if state.inverted == inverted:
            return
        state.inverted = inverted
        self._invalidate_accessible_path()
        if persist:
            self._persist_layers()

    def set_layer_transform(
        self, tier: str, transform: FowLayerTransform, *, persist: bool = True
    ) -> None:
        key = self._canonical_layer(tier)
        if key is None:
            return
        state = self._layer(key)
        state.transform = FowLayerTransform(
            tx=float(transform.tx),
            ty=float(transform.ty),
            sx=max(1e-4, float(transform.sx)),
            sy=max(1e-4, float(transform.sy)),
            ox=float(transform.ox),
            oy=float(transform.oy),
        )
        self._invalidate_accessible_path()
        if persist:
            self._persist_layers()

    def nudge_layer(
        self, tier: str, dx: float, dy: float, *, persist: bool = True
    ) -> None:
        xform = self.layer_transform(tier)
        self.set_layer_transform(
            tier,
            FowLayerTransform(
                tx=xform.tx + float(dx),
                ty=xform.ty + float(dy),
                sx=xform.sx,
                sy=xform.sy,
                ox=xform.ox,
                oy=xform.oy,
            ),
            persist=persist,
        )

    def stretch_layer(
        self,
        tier: str,
        *,
        sx_factor: float = 1.0,
        sy_factor: float = 1.0,
        persist: bool = True,
    ) -> None:
        xform = self.layer_transform(tier)
        self.set_layer_transform(
            tier,
            FowLayerTransform(
                tx=xform.tx,
                ty=xform.ty,
                sx=max(1e-4, xform.sx * float(sx_factor)),
                sy=max(1e-4, xform.sy * float(sy_factor)),
                ox=xform.ox,
                oy=xform.oy,
            ),
            persist=persist,
        )

    def reset_layer_transform(self, tier: str, *, persist: bool = True) -> None:
        ox, oy = self._layer_centroid(tier)
        self.set_layer_transform(
            tier, FowLayerTransform(ox=ox, oy=oy), persist=persist
        )

    def source_rings(
        self, tier: str
    ) -> tuple[tuple[tuple[float, float], ...], ...]:
        """Local-space rings for a layer (override / custom / baked), no affine."""
        key = self._canonical_layer(tier) or str(tier).strip()
        if key == "Z0":
            return self.custom_rings
        if key in self.layer_overrides:
            return self.layer_overrides[key]
        out: list[tuple[tuple[float, float], ...]] = []
        for region in self._regions_for_layer(key):
            out.extend(region.rings)
        return tuple(out)

    def has_layer_override(self, tier: str) -> bool:
        key = self._canonical_layer(tier) or str(tier).strip()
        if key == "Z0":
            return bool(self.custom_rings)
        return key in self.layer_overrides

    def is_layer_dirty(self, tier: str) -> bool:
        key = self._canonical_layer(tier) or str(tier).strip()
        return key in self._dirty_layers

    def any_layer_dirty(self) -> bool:
        return bool(self._dirty_layers)

    def transformed_layer_rings(
        self, tier: str
    ) -> tuple[tuple[tuple[float, float], ...], ...]:
        key = self._canonical_layer(tier) or str(tier).strip()
        xform = self.layer_transform(key)
        return tuple(
            tuple(xform.apply(x, y) for x, y in ring) for ring in self.source_rings(key)
        )

    def layer_local_point(self, tier: str, x: float, y: float) -> tuple[float, float]:
        return self.layer_transform(tier).inverse_apply(x, y)

    def layer_world_point(self, tier: str, x: float, y: float) -> tuple[float, float]:
        return self.layer_transform(tier).apply(x, y)

    def custom_local_point(self, x: float, y: float) -> tuple[float, float]:
        """Map world metres into Z0 local (untransformed custom ring) space."""
        return self.layer_local_point("Z0", x, y)

    def custom_world_point(self, x: float, y: float) -> tuple[float, float]:
        """Map Z0 local custom-ring coordinates into world metres."""
        return self.layer_world_point("Z0", x, y)

    def set_editable_rings(
        self,
        tier: str,
        rings: list[list[tuple[float, float]]] | tuple[tuple[tuple[float, float], ...], ...],
        *,
        mark_dirty: bool = True,
    ) -> None:
        key = self._canonical_layer(tier)
        if key is None:
            return
        cleaned: list[tuple[tuple[float, float], ...]] = []
        for ring in rings:
            pts = tuple((float(x), float(y)) for x, y in ring)
            if len(pts) >= 3:
                cleaned.append(pts)
        stored = tuple(cleaned)
        if key == "Z0":
            self.custom_rings = stored
        else:
            # Keep empty overrides so Clear does not fall back to baked asset rings.
            self.layer_overrides[key] = stored
        if mark_dirty:
            self._dirty_layers.add(key)
        self._invalidate_accessible_path()

    def promote_layer_for_edit(self, tier: str) -> bool:
        """Bake current affine into editable rings and reset transform.

        Returns True when geometry/transform changed.
        All baked vertices are preserved so point edit keeps full detail.
        """
        key = self._canonical_layer(tier)
        if key is None:
            return False
        xform = self.layer_transform(key)
        already_overridden = self.has_layer_override(key)
        # Z0 already lives in custom_rings; only fold a non-identity affine in.
        if key == "Z0":
            if xform.is_identity():
                return False
        elif already_overridden and xform.is_identity():
            return False
        world_rings = [list(ring) for ring in self.transformed_layer_rings(key)]
        self.set_editable_rings(key, world_rings, mark_dirty=True)
        ox, oy = self._layer_centroid(key)
        self.set_layer_transform(
            key, FowLayerTransform(ox=ox, oy=oy), persist=True
        )
        return True

    def bake_layer(self, tier: str) -> bool:
        """Persist editable rings and clear dirty for one layer."""
        key = self._canonical_layer(tier)
        if key is None:
            return False
        # Ensure transform is baked into points before persist.
        if not self.layer_transform(key).is_identity():
            self.promote_layer_for_edit(key)
        if key == "Z0":
            save_custom_fow_rings(self.custom_rings)
        else:
            save_fow_overrides(self.layer_overrides)
        self._dirty_layers.discard(key)
        ox, oy = self._layer_centroid(key)
        self.set_layer_transform(
            key, FowLayerTransform(ox=ox, oy=oy), persist=True
        )
        self._invalidate_accessible_path()
        return True

    def bake_dirty_layers(self) -> None:
        for key in list(self._dirty_layers):
            self.bake_layer(key)

    @staticmethod
    def _rings_from_painter_path(
        path: QtGui.QPainterPath,
    ) -> list[list[tuple[float, float]]]:
        rings: list[list[tuple[float, float]]] = []
        for polygon in path.toSubpathPolygons():
            pts = [(float(p.x()), float(p.y())) for p in polygon]
            if (
                len(pts) >= 2
                and abs(pts[0][0] - pts[-1][0]) <= 1e-6
                and abs(pts[0][1] - pts[-1][1]) <= 1e-6
            ):
                pts = pts[:-1]
            if len(pts) >= 3:
                rings.append(pts)
        return rings

    @staticmethod
    def _ring_looks_like_world_bounds(
        ring: list[tuple[float, float]] | tuple[tuple[float, float], ...],
        *,
        limit: float = 7500.0,
    ) -> bool:
        xs = [x for x, _y in ring]
        ys = [y for _x, y in ring]
        if not xs or not ys:
            return False
        return (
            min(xs) <= -limit
            and max(xs) >= limit
            and min(ys) <= -limit
            and max(ys) >= limit
        )

    def bake_all_enabled_to_z0(self) -> tuple[bool, str]:
        """Back-compat alias for bake_all_enabled_to_baked."""
        return self.bake_all_enabled_to_baked()

    def _replace_baked_region_rings(
        self,
        rings: list[list[tuple[float, float]]] | tuple[tuple[tuple[float, float], ...], ...],
    ) -> tuple[tuple[tuple[float, float], ...], ...]:
        cleaned = tuple(
            tuple((float(x), float(y)) for x, y in ring)
            for ring in rings
            if len(ring) >= 3
        )
        updated: list[FogRegion] = []
        found = False
        for region in self.regions:
            if region.id.upper() == "BAKED":
                updated.append(
                    FogRegion(
                        id="Baked",
                        label=region.label or "Baked",
                        tier="Baked",
                        rings=cleaned,
                    )
                )
                found = True
            else:
                updated.append(region)
        if not found:
            updated.insert(
                0,
                FogRegion(
                    id="Baked",
                    label="Baked",
                    tier="Baked",
                    rings=cleaned,
                ),
            )
        self.regions = tuple(updated)
        # Drop any point-edit override so the asset rings are authoritative.
        self.layer_overrides.pop("Baked", None)
        self._dirty_layers.discard("Baked")
        return cleaned

    def _write_baked_region_asset(
        self,
        rings: tuple[tuple[tuple[float, float], ...], ...],
    ) -> bool:
        asset = discover_project_asset(FOW_REGIONS_RELATIVE_PATH)
        target = asset if asset is not None else (PROJECT_ROOT / "assets" / FOW_REGIONS_RELATIVE_PATH)
        try:
            if target.is_file():
                doc = json.loads(target.read_text(encoding="utf-8"))
            else:
                doc = {
                    "world": "w1_siagarta",
                    "schema": 1,
                    "source": "baked-release",
                    "regions": [],
                }
            if not isinstance(doc, dict):
                return False
            regions = [
                entry
                for entry in (doc.get("regions") or [])
                if isinstance(entry, dict) and str(entry.get("id") or "").upper() != "BAKED"
            ]
            regions.insert(
                0,
                {
                    "id": "Baked",
                    "label": "Baked",
                    "tier": "Baked",
                    "rings": [
                        [[round(float(x), 3), round(float(y), 3)] for x, y in ring]
                        for ring in rings
                    ],
                },
            )
            doc["regions"] = regions
            doc["note"] = (
                "Baked is the release FOW clear zone. Z1–Z4 remain --dev edit "
                "layers; Z0 is user custom FOW."
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return False
        return True

    def bake_all_enabled_to_baked(self) -> tuple[bool, str]:
        """Merge enabled layers into the shipping Baked asset region.

        Writes assets/map/w1_siagarta_fow.json, enables Baked, disables other zones.
        Returns (ok, message).
        """
        if not self.any_layer_enabled():
            return False, "Enable at least one FOW layer first."
        has_clear = any(
            self.layer_enabled(t) and not self.layer_inverted(t)
            for t in FOW_LAYER_ORDER
        )
        if not has_clear:
            return (
                False,
                "Bake all needs at least one non-inverted clear layer "
                "(invert-only uses the world bounds and cannot bake).",
            )
        self._invalidate_accessible_path()
        accessible = self._world_accessible_path_cached()
        if accessible.isEmpty():
            return False, "Current FOW composite is empty."
        rings = [
            ring
            for ring in self._rings_from_painter_path(accessible)
            if not self._ring_looks_like_world_bounds(ring)
        ]
        if not rings:
            return False, "Could not extract zone polygons from the current FOW."
        cleaned = self._replace_baked_region_rings(rings)
        if not self._write_baked_region_asset(cleaned):
            return False, "Merged rings in memory, but failed to write the Baked asset."
        save_fow_overrides(self.layer_overrides)
        self.set_layer_enabled("Baked", True, persist=False)
        self.set_layer_inverted("Baked", False, persist=False)
        self.reset_layer_transform("Baked", persist=False)
        for tier in FOW_LAYER_ORDER:
            if tier == "Baked":
                continue
            self.set_layer_enabled(tier, False, persist=False)
        self._persist_layers()
        self._invalidate_accessible_path()
        return (
            True,
            f"Shipped {len(cleaned)} ring(s) as Baked; other zones disabled.",
        )

    def reset_layer_geometry(self, tier: str) -> bool:
        """Drop override/custom rings and restore baked asset geometry."""
        key = self._canonical_layer(tier)
        if key is None:
            return False
        if key == "Z0":
            self.custom_rings = ()
            save_custom_fow_rings([])
        else:
            self.layer_overrides.pop(key, None)
            save_fow_overrides(self.layer_overrides)
        self._dirty_layers.discard(key)
        ox, oy = self._layer_centroid(key)
        self.set_layer_transform(
            key, FowLayerTransform(ox=ox, oy=oy), persist=True
        )
        self._invalidate_accessible_path()
        return True

    # ---- Z4 back-compat wrappers ----
    def set_z4_layer_enabled(self, enabled: bool) -> None:
        self.set_layer_enabled("Z4", enabled)

    def set_z4_inverted(self, inverted: bool) -> None:
        self.set_layer_inverted("Z4", inverted)

    def set_z4_transform(self, transform: FowLayerTransform, *, persist: bool = True) -> None:
        self.set_layer_transform("Z4", transform, persist=persist)

    def nudge_z4(self, dx: float, dy: float, *, persist: bool = True) -> None:
        self.nudge_layer("Z4", dx, dy, persist=persist)

    def stretch_z4(
        self, *, sx_factor: float = 1.0, sy_factor: float = 1.0, persist: bool = True
    ) -> None:
        self.stretch_layer("Z4", sx_factor=sx_factor, sy_factor=sy_factor, persist=persist)

    def reset_z4_transform(self, *, persist: bool = True) -> None:
        self.reset_layer_transform("Z4", persist=persist)

    def transformed_z4_rings(
        self,
    ) -> tuple[tuple[tuple[float, float], ...], ...]:
        return self.transformed_layer_rings("Z4")

    def _drop_soft_fog_cache(self) -> None:
        self._soft_fog_image = None
        self._soft_fog_cache_key = None

    def _drop_baked_overlay_cache(self) -> None:
        self._baked_overlay = None
        self._baked_overlay_key = None

    def release_paint_caches(self) -> None:
        """Free soft-fog and baked-overlay images (e.g. FOW master off)."""
        self._drop_soft_fog_cache()
        self._drop_baked_overlay_cache()

    def _invalidate_accessible_path(self) -> None:
        self._world_accessible_path = None
        self._world_path_cache_key = None
        self._world_path_generation += 1
        self.release_paint_caches()
        self._accessible_mask_key = None
        self._accessible_mask_bits = None
        self._accessible_mask_geom = None

    def set_custom_rings(
        self, rings: list[list[tuple[float, float]]] | tuple[tuple[tuple[float, float], ...], ...]
    ) -> None:
        cleaned: list[tuple[tuple[float, float], ...]] = []
        for ring in rings:
            pts = tuple((float(x), float(y)) for x, y in ring)
            if len(pts) >= 3:
                cleaned.append(pts)
        self.custom_rings = tuple(cleaned)
        self._invalidate_accessible_path()

    def _layer_ring_path(self, tier: str) -> QtGui.QPainterPath:
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.FillRule.WindingFill)
        for ring in self.transformed_layer_rings(tier):
            ring_path = QtGui.QPainterPath()
            first = True
            for x, y in ring:
                if first:
                    ring_path.moveTo(x, y)
                    first = False
                else:
                    ring_path.lineTo(x, y)
            ring_path.closeSubpath()
            path = path.united(ring_path)
        return path

    def _world_clear_bounds_path(self) -> QtGui.QPainterPath:
        path = QtGui.QPainterPath()
        path.addRect(QtCore.QRectF(-8000.0, -8000.0, 16000.0, 16000.0))
        return path

    def _load_pattern(self) -> None:
        path = discover_project_asset(FOW_PATTERN_RELATIVE_PATH)
        if path is None or not path.is_file():
            self._pattern = None
            self._pattern_brush = None
            return
        image = QtGui.QImage(str(path))
        if image.isNull():
            self._pattern = None
            self._pattern_brush = None
            return
        self._pattern = image
        # QPixmap/QBrush need a QGuiApplication — build lazily in _draw_fog_path.
        self._pattern_brush = None

    @property
    def accessible_tiers(self) -> frozenset[str]:
        return frozenset(self.enabled_layers())

    def cycle_max_tier(self) -> str:
        """Legacy no-op cycle kept for API stability."""
        return self.max_tier if self.enabled else "OFF"

    def set_max_tier(self, tier: str) -> None:
        tier = str(tier).strip().upper()
        if tier in FOW_TIER_ORDER:
            self.max_tier = tier

    def _ensure_accessible_mask(self) -> bool:
        """Rasterise the composite accessible path for O(1) point probes."""
        if self._accessible_mask_key == self._world_path_generation:
            return self._accessible_mask_bits is not None
        self._accessible_mask_key = self._world_path_generation
        self._accessible_mask_bits = None
        self._accessible_mask_geom = None

        path = self._world_accessible_path_cached()
        if path.isEmpty():
            return False
        bounds = path.boundingRect()
        if bounds.width() <= 0.0 or bounds.height() <= 0.0:
            return False
        scale = FOW_ACCESSIBLE_MASK_MAX_DIM / max(bounds.width(), bounds.height())
        width = max(
            1, min(FOW_ACCESSIBLE_MASK_MAX_DIM, math.ceil(bounds.width() * scale))
        )
        height = max(
            1, min(FOW_ACCESSIBLE_MASK_MAX_DIM, math.ceil(bounds.height() * scale))
        )
        image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_Grayscale8)
        if image.isNull():
            return False
        image.fill(0)
        painter = QtGui.QPainter(image)
        # Hard edges keep every probe an unambiguous inside/outside answer.
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(255, 255, 255))
        transform = QtGui.QTransform()
        transform.scale(scale, scale)
        transform.translate(-bounds.left(), -bounds.top())
        painter.setTransform(transform)
        painter.drawPath(path)
        painter.end()

        self._accessible_mask_bits = image.constBits().tobytes()
        self._accessible_mask_stride = image.bytesPerLine()
        self._accessible_mask_geom = (
            bounds.left(),
            bounds.top(),
            scale,
            width,
            height,
        )
        return True

    def world_is_accessible(self, x: float, y: float) -> bool:
        if not self.enabled:
            return True
        if not self.any_layer_enabled():
            return False
        if self._ensure_accessible_mask() and self._accessible_mask_geom is not None:
            left, top, scale, width, height = self._accessible_mask_geom
            column = int((x - left) * scale)
            row = int((y - top) * scale)
            if column < 0 or row < 0 or column >= width or row >= height:
                return False
            bits = self._accessible_mask_bits
            if bits is not None:
                return bits[row * self._accessible_mask_stride + column] > 127
        # Use the cached composite path instead of rebuilding rings per marker.
        return self._world_accessible_path_cached().contains(QtCore.QPointF(x, y))

    def can_use_baked_overlay(self) -> bool:
        """True when FOW is the shipping Baked layer only (texture-friendly)."""
        if not self.enabled:
            return False
        enabled = [tier for tier in FOW_LAYER_ORDER if self.layer_enabled(tier)]
        if enabled != ["Baked"]:
            return False
        if self.layer_inverted("Baked"):
            return False
        if not self.layer_transform("Baked").is_identity():
            return False
        return bool(self.source_rings("Baked"))

    def _baked_overlay_cache_key(self, map_texture: Any) -> tuple[Any, ...]:
        image = getattr(map_texture, "image", None)
        width = int(image.width()) if image is not None and not image.isNull() else 0
        height = int(image.height()) if image is not None and not image.isNull() else 0
        return (
            self._world_path_generation,
            width,
            height,
            bool(self.feather_enabled),
            round(float(self.feather_metres), 2),
            id(self._pattern) if self._pattern is not None else 0,
        )

    def ensure_baked_overlay(self, map_texture: Any) -> bool:
        """Build a map-aligned FOW overlay texture for the Baked clear zone."""
        if not self.can_use_baked_overlay():
            self._drop_baked_overlay_cache()
            return False
        image = getattr(map_texture, "image", None)
        if image is None or image.isNull():
            return False
        key = self._baked_overlay_cache_key(map_texture)
        if (
            self._baked_overlay is not None
            and self._baked_overlay_key == key
            and not self._baked_overlay.isNull()
        ):
            return True
        overlay = self._build_baked_overlay(map_texture)
        if overlay is None or overlay.isNull():
            self._baked_overlay = None
            self._baked_overlay_key = None
            return False
        self._baked_overlay = overlay
        self._baked_overlay_key = key
        return True

    def paint_baked_overlay(
        self,
        painter: QtGui.QPainter,
        map_texture: Any,
        *,
        viewport: QtCore.QRectF,
        view_center: dict[str, Any],
        pixels_per_metre: float,
    ) -> bool:
        if not self.ensure_baked_overlay(map_texture):
            return False
        assert self._baked_overlay is not None
        draw = getattr(map_texture, "draw_aligned_image", None)
        if not callable(draw):
            return False
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        ok = bool(
            draw(
                painter,
                self._baked_overlay,
                target_rect=viewport,
                view_center=view_center,
                pixels_per_metre=pixels_per_metre,
                fill_background=None,
            )
        )
        painter.restore()
        return ok

    def _build_baked_overlay(self, map_texture: Any) -> QtGui.QImage | None:
        map_image = getattr(map_texture, "image", None)
        if map_image is None or map_image.isNull():
            return None
        map_w = int(map_image.width())
        map_h = int(map_image.height())
        if map_w < 2 or map_h < 2:
            return None
        scale = 1.0
        max_dim = max(map_w, map_h)
        if max_dim > FOW_BAKED_OVERLAY_MAX_DIM:
            scale = FOW_BAKED_OVERLAY_MAX_DIM / float(max_dim)
        out_w = max(2, int(round(map_w * scale)))
        out_h = max(2, int(round(map_h * scale)))

        object_to_pixel = getattr(map_texture, "object_to_pixel", None)
        if not callable(object_to_pixel):
            return None

        clear_path = QtGui.QPainterPath()
        clear_path.setFillRule(QtCore.Qt.FillRule.WindingFill)
        for ring in self.source_rings("Baked"):
            ring_path = QtGui.QPainterPath()
            first = True
            for x, y in ring:
                pixel = object_to_pixel({"x": x, "y": y})
                if pixel is None:
                    first = True
                    continue
                px = float(pixel[0]) * scale
                py = float(pixel[1]) * scale
                if first:
                    ring_path.moveTo(px, py)
                    first = False
                else:
                    ring_path.lineTo(px, py)
            if not ring_path.isEmpty():
                ring_path.closeSubpath()
                clear_path = clear_path.united(ring_path)
        if clear_path.isEmpty():
            return None

        # Soft clear mask in texture space (feather in world metres → tex px).
        mask = QtGui.QImage(out_w, out_h, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        mask.fill(QtCore.Qt.GlobalColor.transparent)
        mask_painter = QtGui.QPainter(mask)
        mask_painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        mask_painter.setPen(QtCore.Qt.PenStyle.NoPen)
        mask_painter.setBrush(QtGui.QColor(255, 255, 255, 255))
        mask_painter.drawPath(clear_path)
        mask_painter.end()

        feather_m = (
            max(0.0, float(self.feather_metres)) if self.feather_enabled else 0.0
        )
        if feather_m > 0.05:
            calibration = getattr(map_texture, "calibration", None)
            logical_w = float(getattr(map_texture, "logical_width", 0.0) or map_w)
            logical_h = float(getattr(map_texture, "logical_height", 0.0) or map_h)
            ppm_tex = 1.0
            if calibration is not None and getattr(calibration, "valid", lambda: False)():
                ppm_u = abs(float(calibration.scale_x)) * (out_w / max(1.0, logical_w))
                ppm_v = abs(float(calibration.scale_y)) * (out_h / max(1.0, logical_h))
                ppm_tex = max(0.05, (ppm_u + ppm_v) * 0.5)
            mask = self._blur_image(mask, feather_m * ppm_tex)

        overlay = QtGui.QImage(
            out_w, out_h, QtGui.QImage.Format.Format_ARGB32_Premultiplied
        )
        overlay.fill(QtCore.Qt.GlobalColor.transparent)
        layer = QtGui.QPainter(overlay)
        layer.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        full = QtGui.QPainterPath()
        full.addRect(QtCore.QRectF(0.0, 0.0, float(out_w), float(out_h)))
        self._draw_fog_path(layer, full)
        # Punch soft clear holes out of the patterned fog.
        layer.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_DestinationOut
        )
        layer.drawImage(0, 0, mask)
        layer.end()
        return overlay

    def paint(
        self,
        painter: QtGui.QPainter,
        *,
        viewport: QtCore.QRectF,
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
        world_to_screen: Callable[..., QtCore.QPointF],
        draft_ring: list[tuple[float, float]] | tuple[tuple[float, float], ...] | None = None,
        draft_cursor: tuple[float, float] | None = None,
        show_custom_handles: bool = False,
        handle_layer: str = "Z0",
        selected_vertices: set[tuple[int, int]] | None = None,
        hover_ring: int | None = None,
        hover_vertex: int | None = None,
        hover_edge: int | None = None,
        active_ring: int | None = None,
        active_vertex: int | None = None,
        map_texture: Any | None = None,
    ) -> None:
        layers_on = self.any_layer_enabled()
        if (
            not self.enabled
            and not self.show_outlines
            and not self.custom_rings
            and not draft_ring
            and not layers_on
            and not show_custom_handles
        ):
            return
        if self.enabled:
            used_overlay = False
            if (
                map_texture is not None
                and not show_custom_handles
                and self.can_use_baked_overlay()
            ):
                used_overlay = self.paint_baked_overlay(
                    painter,
                    map_texture,
                    viewport=viewport,
                    view_center=view_center,
                    pixels_per_metre=pixels_per_metre,
                )
            if used_overlay:
                # Baked path owns FOW fill — soft viewport cache is unused.
                self._drop_soft_fog_cache()
            else:
                # Soft/hard path — drop map-sized baked overlay while unused.
                self._drop_baked_overlay_cache()
                self._paint_fog(
                    painter,
                    viewport=viewport,
                    center=center,
                    pixels_per_metre=pixels_per_metre,
                    view_center=view_center,
                    world_to_screen=world_to_screen,
                )
        else:
            self.release_paint_caches()
        if self.show_outlines and self.show_layer_outlines:
            self._paint_outlines(
                painter,
                center=center,
                pixels_per_metre=pixels_per_metre,
                view_center=view_center,
                world_to_screen=world_to_screen,
            )
        if layers_on and self.show_layer_outlines:
            for tier in FOW_LAYER_ORDER:
                if not self.layer_enabled(tier):
                    continue
                rings = self.transformed_layer_rings(tier)
                if not rings:
                    continue
                self._paint_ring_outlines(
                    painter,
                    rings=rings,
                    color=_LAYER_OUTLINE_COLORS.get(tier, _OUTLINE_COLOR),
                    center=center,
                    pixels_per_metre=pixels_per_metre,
                    view_center=view_center,
                    world_to_screen=world_to_screen,
                    closed=True,
                )
        # Vertex/edit borders are --dev (or Points-tool) only.
        if not (self.show_layer_outlines or show_custom_handles):
            if draft_ring:
                self._paint_draft_line(
                    painter,
                    draft_ring=draft_ring,
                    draft_cursor=draft_cursor,
                    center=center,
                    pixels_per_metre=pixels_per_metre,
                    view_center=view_center,
                    world_to_screen=world_to_screen,
                )
            return
        edit_key = self._canonical_layer(handle_layer) or "Z0"
        edit_world = self.transformed_layer_rings(edit_key)
        # Cyan Z0 outline when custom rings exist and aren't already drawn as a
        # layer border (unless Points is editing another layer).
        z0_world = (
            edit_world
            if edit_key == "Z0"
            else self.transformed_layer_rings("Z0")
        )
        if z0_world and edit_key == "Z0":
            if show_custom_handles or not (
                self.show_layer_outlines and self.layer_enabled("Z0")
            ):
                self._paint_ring_outlines(
                    painter,
                    rings=z0_world,
                    color=_CUSTOM_OUTLINE_COLOR,
                    center=center,
                    pixels_per_metre=pixels_per_metre,
                    view_center=view_center,
                    world_to_screen=world_to_screen,
                    closed=True,
                )
        elif z0_world and not (
            self.show_layer_outlines and self.layer_enabled("Z0")
        ):
            self._paint_ring_outlines(
                painter,
                rings=z0_world,
                color=_CUSTOM_OUTLINE_COLOR,
                center=center,
                pixels_per_metre=pixels_per_metre,
                view_center=view_center,
                world_to_screen=world_to_screen,
                closed=True,
            )
        if edit_world and edit_key != "Z0" and show_custom_handles:
            self._paint_ring_outlines(
                painter,
                rings=edit_world,
                color=_CUSTOM_OUTLINE_COLOR,
                center=center,
                pixels_per_metre=pixels_per_metre,
                view_center=view_center,
                world_to_screen=world_to_screen,
                closed=True,
            )
        if show_custom_handles and edit_world:
            self._paint_custom_handles(
                painter,
                rings=edit_world,
                center=center,
                pixels_per_metre=pixels_per_metre,
                view_center=view_center,
                world_to_screen=world_to_screen,
                selected_vertices=selected_vertices or set(),
                hover_ring=hover_ring,
                hover_vertex=hover_vertex,
                hover_edge=hover_edge,
                active_ring=active_ring,
                active_vertex=active_vertex,
            )
        if draft_ring:
            # Draft vertices are stored in world space while drawing.
            self._paint_draft_line(
                painter,
                draft_ring=draft_ring,
                draft_cursor=draft_cursor,
                center=center,
                pixels_per_metre=pixels_per_metre,
                view_center=view_center,
                world_to_screen=world_to_screen,
            )

    def _custom_rings_path(self) -> QtGui.QPainterPath:
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.FillRule.WindingFill)
        for ring in self.transformed_layer_rings("Z0"):
            ring_path = QtGui.QPainterPath()
            first = True
            for x, y in ring:
                if first:
                    ring_path.moveTo(x, y)
                    first = False
                else:
                    ring_path.lineTo(x, y)
            ring_path.closeSubpath()
            path = path.united(ring_path)
        return path

    def _world_accessible_path_cached(self) -> QtGui.QPainterPath:
        cache_key = self._world_path_generation
        if (
            self._world_accessible_path is not None
            and self._world_path_cache_key == cache_key
        ):
            return self._world_accessible_path
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.FillRule.WindingFill)
        if self.any_layer_enabled():
            clear_path = QtGui.QPainterPath()
            clear_path.setFillRule(QtCore.Qt.FillRule.WindingFill)
            invert_path = QtGui.QPainterPath()
            invert_path.setFillRule(QtCore.Qt.FillRule.WindingFill)
            has_clear = False
            has_invert = False
            for tier in FOW_LAYER_ORDER:
                if not self.layer_enabled(tier):
                    continue
                layer_path = self._layer_ring_path(tier)
                if self.layer_inverted(tier):
                    invert_path = invert_path.united(layer_path)
                    has_invert = True
                else:
                    clear_path = clear_path.united(layer_path)
                    has_clear = True
            if has_invert and not has_clear:
                path = self._world_clear_bounds_path().subtracted(invert_path)
            elif has_clear and has_invert:
                path = clear_path.subtracted(invert_path)
            else:
                path = clear_path
        self._world_accessible_path = path
        self._world_path_cache_key = cache_key
        return path

    def _accessible_screen_path(
        self,
        *,
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
    ) -> QtGui.QPainterPath:
        world_path = self._world_accessible_path_cached()
        view_x = float(view_center.get("x") or 0.0)
        view_y = float(view_center.get("y") or 0.0)
        transform = QtGui.QTransform()
        transform.translate(center.x(), center.y())
        transform.scale(pixels_per_metre, pixels_per_metre)
        transform.translate(-view_x, -view_y)
        return transform.map(world_path)

    def _ensure_blur_pipeline(self) -> None:
        if self._blur_effect is not None:
            return
        self._blur_effect = QtWidgets.QGraphicsBlurEffect()
        self._blur_effect.setBlurHints(
            QtWidgets.QGraphicsBlurEffect.BlurHint.PerformanceHint
        )
        self._blur_scene = QtWidgets.QGraphicsScene()
        self._blur_item = QtWidgets.QGraphicsPixmapItem()
        self._blur_item.setGraphicsEffect(self._blur_effect)
        self._blur_scene.addItem(self._blur_item)

    def _blur_image(self, image: QtGui.QImage, radius_px: float) -> QtGui.QImage:
        """Blur an ARGB image; downsample first when radius is large."""
        if radius_px <= 0.5 or image.isNull():
            return image
        self._ensure_blur_pipeline()
        assert self._blur_effect is not None
        assert self._blur_scene is not None
        assert self._blur_item is not None

        work = image
        blur_radius = float(radius_px)
        scale = 1.0
        if blur_radius > FOG_FEATHER_MAX_BLUR_PX:
            scale = FOG_FEATHER_MAX_BLUR_PX / blur_radius
            work = image.scaled(
                max(1, int(round(image.width() * scale))),
                max(1, int(round(image.height() * scale))),
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            blur_radius = FOG_FEATHER_MAX_BLUR_PX
        else:
            # Soft fog runs every follow frame — keep the blur buffer modest.
            max_dim = max(work.width(), work.height())
            if max_dim > 960:
                scale = 960.0 / float(max_dim)
                work = image.scaled(
                    max(1, int(round(image.width() * scale))),
                    max(1, int(round(image.height() * scale))),
                    QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                    QtCore.Qt.TransformationMode.FastTransformation,
                )
                blur_radius = max(1.0, blur_radius * scale)

        self._blur_effect.setBlurRadius(blur_radius)
        self._blur_item.setPixmap(QtGui.QPixmap.fromImage(work))
        self._blur_scene.setSceneRect(QtCore.QRectF(work.rect()))

        out = QtGui.QImage(work.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(QtCore.Qt.GlobalColor.transparent)
        scene_painter = QtGui.QPainter(out)
        self._blur_scene.render(
            scene_painter,
            QtCore.QRectF(out.rect()),
            QtCore.QRectF(work.rect()),
        )
        scene_painter.end()

        if scale < 1.0:
            out = out.scaled(
                image.size(),
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        return out

    def _paint_fog(
        self,
        painter: QtGui.QPainter,
        *,
        viewport: QtCore.QRectF,
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
        world_to_screen: Callable[..., QtCore.QPointF],
    ) -> None:
        del world_to_screen
        accessible = self._accessible_screen_path(
            center=center,
            pixels_per_metre=pixels_per_metre,
            view_center=view_center,
        )
        fog_path = QtGui.QPainterPath()
        fog_path.addRect(viewport)
        fog_path = fog_path.subtracted(accessible)

        feather_m = (
            max(0.0, float(self.feather_metres)) if self.feather_enabled else 0.0
        )
        radius_px = feather_m * max(0.0, float(pixels_per_metre))
        if radius_px < 0.75:
            # Hard edge — soft viewport cache is unused.
            self._drop_soft_fog_cache()
            self._draw_fog_path(painter, fog_path)
            return

        # Soft edge: blur only the fog alpha mask. Keep the swirl pattern sharp
        # by DestinationIn-compositing the patterned fill with that mask.
        pad = int(math.ceil(min(radius_px, FOG_FEATHER_MAX_BLUR_PX) + 2))
        width = max(1, int(math.ceil(viewport.width())))
        height = max(1, int(math.ceil(viewport.height())))
        view_x = float(view_center.get("x") or 0.0)
        view_y = float(view_center.get("y") or 0.0)
        cache_key = (
            self._world_path_generation,
            round(view_x, 1),
            round(view_y, 1),
            round(float(pixels_per_metre), 3),
            width,
            height,
            pad,
            round(float(self.feather_metres), 2),
            bool(self.feather_enabled),
        )
        if (
            self._soft_fog_image is not None
            and self._soft_fog_cache_key == cache_key
            and not self._soft_fog_image.isNull()
        ):
            painter.save()
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(
                viewport.topLeft() - QtCore.QPointF(pad, pad),
                self._soft_fog_image,
            )
            painter.restore()
            return

        img_w = width + 2 * pad
        img_h = height + 2 * pad
        origin = QtCore.QPointF(pad - viewport.left(), pad - viewport.top())

        mask_img = QtGui.QImage(
            img_w, img_h, QtGui.QImage.Format.Format_ARGB32_Premultiplied
        )
        mask_img.fill(QtCore.Qt.GlobalColor.transparent)
        mask_painter = QtGui.QPainter(mask_img)
        mask_painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        mask_painter.translate(origin)
        mask_painter.setPen(QtCore.Qt.PenStyle.NoPen)
        mask_painter.setBrush(QtGui.QColor(255, 255, 255, 255))
        mask_painter.drawPath(fog_path)
        mask_painter.end()
        soft_mask = self._blur_image(mask_img, radius_px)

        fog_img = QtGui.QImage(
            img_w, img_h, QtGui.QImage.Format.Format_ARGB32_Premultiplied
        )
        fog_img.fill(QtCore.Qt.GlobalColor.transparent)
        layer = QtGui.QPainter(fog_img)
        layer.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        layer.translate(origin)
        # Pattern the full viewport; soft mask limits visibility + feather bleed.
        viewport_path = QtGui.QPainterPath()
        viewport_path.addRect(viewport)
        self._draw_fog_path(layer, viewport_path)
        layer.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_DestinationIn
        )
        layer.setTransform(QtGui.QTransform())
        layer.drawImage(0, 0, soft_mask)
        layer.end()

        self._soft_fog_image = fog_img
        self._soft_fog_cache_key = cache_key

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(
            viewport.topLeft() - QtCore.QPointF(pad, pad),
            fog_img,
        )
        painter.restore()

    def _draw_fog_path(
        self, painter: QtGui.QPainter, fog_path: QtGui.QPainterPath
    ) -> None:
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        if self._pattern_brush is not None:
            painter.setOpacity(0.88)
            painter.setBrush(self._pattern_brush)
            painter.drawPath(fog_path)
            painter.setOpacity(0.42)
            painter.setBrush(QtGui.QColor(8, 12, 18, 255))
            painter.drawPath(fog_path)
        elif self._pattern is not None and not self._pattern.isNull():
            brush = QtGui.QBrush(QtGui.QPixmap.fromImage(self._pattern))
            self._pattern_brush = brush
            painter.setOpacity(0.88)
            painter.setBrush(brush)
            painter.drawPath(fog_path)
            painter.setOpacity(0.42)
            painter.setBrush(QtGui.QColor(8, 12, 18, 255))
            painter.drawPath(fog_path)
        else:
            painter.setOpacity(0.78)
            painter.setBrush(QtGui.QColor(12, 16, 22, 255))
            painter.drawPath(fog_path)
        painter.restore()

    def _paint_outlines(
        self,
        painter: QtGui.QPainter,
        *,
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
        world_to_screen: Callable[..., QtCore.QPointF],
    ) -> None:
        painter.save()
        for region in self.regions:
            color = _OUTLINE_COLOR
            accessible = (
                region.id in self.accessible_tiers
                or region.tier in self.accessible_tiers
            )
            pen = QtGui.QPen(color)
            pen.setWidthF(1.25 if accessible else 1.0)
            pen.setStyle(
                QtCore.Qt.PenStyle.SolidLine
                if accessible
                else QtCore.Qt.PenStyle.DashLine
            )
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            for ring in region.rings:
                path = QtGui.QPainterPath()
                first = True
                for x, y in ring:
                    pt = world_to_screen(
                        {"x": x, "y": y}, center, pixels_per_metre, view_center
                    )
                    if first:
                        path.moveTo(pt)
                        first = False
                    else:
                        path.lineTo(pt)
                path.closeSubpath()
                painter.drawPath(path)
        painter.restore()

    def _paint_ring_outlines(
        self,
        painter: QtGui.QPainter,
        *,
        rings: tuple[tuple[tuple[float, float], ...], ...]
        | list[list[tuple[float, float]]]
        | list[tuple[tuple[float, float], ...]],
        color: QtGui.QColor,
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
        world_to_screen: Callable[..., QtCore.QPointF],
        closed: bool = True,
    ) -> None:
        painter.save()
        pen = QtGui.QPen(color)
        pen.setWidthF(1.6)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        for ring in rings:
            path = QtGui.QPainterPath()
            first = True
            for x, y in ring:
                pt = world_to_screen(
                    {"x": x, "y": y}, center, pixels_per_metre, view_center
                )
                if first:
                    path.moveTo(pt)
                    first = False
                else:
                    path.lineTo(pt)
            if closed and len(ring) >= 3:
                path.closeSubpath()
            painter.drawPath(path)
        painter.restore()

    def _paint_custom_handles(
        self,
        painter: QtGui.QPainter,
        *,
        rings: tuple[tuple[tuple[float, float], ...], ...],
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
        world_to_screen: Callable[..., QtCore.QPointF],
        selected_vertices: set[tuple[int, int]] | None = None,
        hover_ring: int | None = None,
        hover_vertex: int | None = None,
        hover_edge: int | None = None,
        active_ring: int | None = None,
        active_vertex: int | None = None,
    ) -> None:
        selected = selected_vertices or set()
        painter.save()
        for ring_i, ring in enumerate(rings):
            n = len(ring)
            if n < 3:
                continue
            screen_pts = [
                world_to_screen(
                    {"x": x, "y": y}, center, pixels_per_metre, view_center
                )
                for x, y in ring
            ]
            if hover_ring == ring_i and hover_edge is not None and 0 <= hover_edge < n:
                a = screen_pts[hover_edge]
                b = screen_pts[(hover_edge + 1) % n]
                mid = QtCore.QPointF((a.x() + b.x()) * 0.5, (a.y() + b.y()) * 0.5)
                pen = QtGui.QPen(QtGui.QColor(255, 220, 96, 230))
                pen.setWidthF(1.2)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(QtGui.QColor(255, 220, 96, 200))
                painter.drawEllipse(mid, 3.0, 3.0)
            for vert_i, pt in enumerate(screen_pts):
                active = active_ring == ring_i and active_vertex == vert_i
                hovered = hover_ring == ring_i and hover_vertex == vert_i
                is_selected = (ring_i, vert_i) in selected
                if active:
                    fill = QtGui.QColor(255, 220, 96, 230)
                    radius = 5.0
                elif is_selected:
                    fill = QtGui.QColor(255, 170, 72, 230)
                    radius = 5.0
                elif hovered:
                    fill = QtGui.QColor(120, 220, 255, 220)
                    radius = 4.5
                else:
                    fill = QtGui.QColor(72, 196, 255, 180)
                    radius = 3.5
                pen = QtGui.QPen(_CUSTOM_OUTLINE_COLOR)
                pen.setWidthF(1.0)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(fill)
                painter.drawEllipse(pt, radius, radius)
        painter.restore()

    def _paint_draft_line(
        self,
        painter: QtGui.QPainter,
        *,
        draft_ring: list[tuple[float, float]] | tuple[tuple[float, float], ...],
        draft_cursor: tuple[float, float] | None,
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
        world_to_screen: Callable[..., QtCore.QPointF],
    ) -> None:
        if not draft_ring and draft_cursor is None:
            return
        painter.save()
        pen = QtGui.QPen(_CUSTOM_OUTLINE_COLOR)
        pen.setWidthF(1.8)
        pen.setCosmetic(True)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        path = QtGui.QPainterPath()
        first = True
        for x, y in draft_ring:
            pt = world_to_screen(
                {"x": x, "y": y}, center, pixels_per_metre, view_center
            )
            if first:
                path.moveTo(pt)
                first = False
            else:
                path.lineTo(pt)
        if draft_cursor is not None and draft_ring:
            cursor_pt = world_to_screen(
                {"x": draft_cursor[0], "y": draft_cursor[1]},
                center,
                pixels_per_metre,
                view_center,
            )
            if first:
                path.moveTo(cursor_pt)
            else:
                path.lineTo(cursor_pt)
        painter.drawPath(path)

        # Vertex handles
        handle = QtGui.QPen(_CUSTOM_OUTLINE_COLOR)
        handle.setWidthF(1.0)
        handle.setCosmetic(True)
        painter.setPen(handle)
        painter.setBrush(QtGui.QColor(72, 196, 255, 180))
        for x, y in draft_ring:
            pt = world_to_screen(
                {"x": x, "y": y}, center, pixels_per_metre, view_center
            )
            painter.drawEllipse(pt, 3.5, 3.5)
        painter.restore()


def _point_in_ring(x: float, y: float, ring: tuple[tuple[float, float], ...]) -> bool:
    # Ray casting; rings are closed implicitly.
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-30) + xi
        ):
            inside = not inside
        j = i
    return inside
