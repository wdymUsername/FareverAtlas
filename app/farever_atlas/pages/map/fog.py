"""Fog of war over inaccessible / unreleased map regions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6 import QtCore, QtGui

from ...config import discover_project_asset

FOW_REGIONS_RELATIVE_PATH = Path("map/w1_siagarta_fow.json")
FOW_PATTERN_RELATIVE_PATH = Path("map/pattern_fog_of_war_512.png")

# Prototype tier ladder. Higher index = more of the map revealed.
FOW_TIER_ORDER = ("Z1", "Z2", "Z3", "Z4")
FOW_TIER_LABELS = {
    "Z1": "Z1 Skover",
    "Z2": "Z1–Z2 (EA default)",
    "Z3": "Z1–Z3 + Crimson",
    "Z4": "All regions",
}

_OUTLINE_COLORS = {
    "Z1": QtGui.QColor(120, 200, 255, 220),
    "Z2": QtGui.QColor(255, 190, 90, 220),
    "Z3": QtGui.QColor(255, 110, 140, 220),
    "Z4": QtGui.QColor(180, 120, 255, 220),
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
    show_outlines: bool = True
    # Highest revealed tier (inclusive). "Z2" reveals Z1+Z2.
    max_tier: str = "Z2"
    hide_markers: bool = True
    _pattern: QtGui.QImage | None = field(default=None, repr=False)
    _world_accessible_path: QtGui.QPainterPath | None = field(
        default=None, repr=False, compare=False
    )
    _world_path_tiers: frozenset[str] | None = field(
        default=None, repr=False, compare=False
    )

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
        accessible = defaults.get("accessible_tiers") or ["Z1", "Z2"]
        max_tier = "Z2"
        if isinstance(accessible, list) and accessible:
            # Highest listed tier wins as the inclusive ceiling.
            rank = {t: i for i, t in enumerate(FOW_TIER_ORDER)}
            ranked = [str(t).upper() for t in accessible if str(t).upper() in rank]
            if ranked:
                max_tier = max(ranked, key=lambda t: rank[t])
        fog = cls(
            regions=tuple(regions),
            enabled=bool(defaults.get("enabled", True)),
            show_outlines=bool(defaults.get("show_outlines", True)),
            max_tier=max_tier,
        )
        fog._load_pattern()
        return fog

    def _load_pattern(self) -> None:
        path = discover_project_asset(FOW_PATTERN_RELATIVE_PATH)
        if path is None or not path.is_file():
            self._pattern = None
            return
        image = QtGui.QImage(str(path))
        self._pattern = None if image.isNull() else image

    @property
    def accessible_tiers(self) -> frozenset[str]:
        if self.max_tier not in FOW_TIER_ORDER:
            return frozenset({"Z1", "Z2"})
        cutoff = FOW_TIER_ORDER.index(self.max_tier)
        return frozenset(FOW_TIER_ORDER[: cutoff + 1])

    def cycle_max_tier(self) -> str:
        """Advance Z1→Z2→Z3→Z4→off→Z1. Returns current tier or 'OFF'."""
        order = FOW_TIER_ORDER
        if not self.enabled:
            self.enabled = True
            self.max_tier = order[0]
            self._world_path_tiers = None
            return self.max_tier
        try:
            idx = order.index(self.max_tier)
        except ValueError:
            idx = 1
        if idx >= len(order) - 1:
            self.enabled = False
            return "OFF"
        self.max_tier = order[idx + 1]
        self._world_path_tiers = None
        return self.max_tier

    def set_max_tier(self, tier: str) -> None:
        tier = str(tier).strip().upper()
        if tier not in FOW_TIER_ORDER:
            return
        if tier != self.max_tier:
            self.max_tier = tier
            self._world_path_tiers = None

    def world_is_accessible(self, x: float, y: float) -> bool:
        if not self.enabled:
            return True
        for region in self.regions:
            if region.tier not in self.accessible_tiers:
                continue
            for ring in region.rings:
                if _point_in_ring(x, y, ring):
                    return True
        return False

    def paint(
        self,
        painter: QtGui.QPainter,
        *,
        viewport: QtCore.QRectF,
        center: QtCore.QPointF,
        pixels_per_metre: float,
        view_center: dict[str, Any],
        world_to_screen: Callable[..., QtCore.QPointF],
    ) -> None:
        if not self.regions:
            return
        if self.enabled:
            self._paint_fog(
                painter,
                viewport=viewport,
                center=center,
                pixels_per_metre=pixels_per_metre,
                view_center=view_center,
                world_to_screen=world_to_screen,
            )
        if self.show_outlines:
            self._paint_outlines(
                painter,
                center=center,
                pixels_per_metre=pixels_per_metre,
                view_center=view_center,
                world_to_screen=world_to_screen,
            )

    def _world_accessible_path_cached(self) -> QtGui.QPainterPath:
        tiers = self.accessible_tiers
        if (
            self._world_accessible_path is not None
            and self._world_path_tiers == tiers
        ):
            return self._world_accessible_path
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.FillRule.WindingFill)
        for region in self.regions:
            if region.tier not in tiers:
                continue
            for ring in region.rings:
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
        self._world_accessible_path = path
        self._world_path_tiers = tiers
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

        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        if self._pattern is not None and not self._pattern.isNull():
            brush = QtGui.QBrush(QtGui.QPixmap.fromImage(self._pattern))
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
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        drawn_labels: set[str] = set()
        for region in self.regions:
            color = _OUTLINE_COLORS.get(region.tier, QtGui.QColor(200, 200, 200, 220))
            accessible = region.tier in self.accessible_tiers
            pen = QtGui.QPen(color)
            pen.setWidthF(2.0 if accessible else 1.2)
            pen.setStyle(
                QtCore.Qt.PenStyle.SolidLine
                if accessible
                else QtCore.Qt.PenStyle.DashLine
            )
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            label_at: QtCore.QPointF | None = None
            for ring in region.rings:
                path = QtGui.QPainterPath()
                first = True
                for x, y in ring:
                    pt = world_to_screen(
                        {"x": x, "y": y}, center, pixels_per_metre, view_center
                    )
                    if first:
                        path.moveTo(pt)
                        label_at = pt if label_at is None else label_at
                        first = False
                    else:
                        path.lineTo(pt)
                path.closeSubpath()
                painter.drawPath(path)
            if label_at is not None and region.id not in drawn_labels:
                drawn_labels.add(region.id)
                tag = f"{region.label} [{region.tier}]"
                if self.enabled and not accessible:
                    tag = f"{tag} · fogged"
                painter.setPen(QtGui.QColor(color.red(), color.green(), color.blue(), 255))
                painter.drawText(label_at + QtCore.QPointF(6, -4), tag)
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
