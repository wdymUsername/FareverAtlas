"""Map calibration, projection, texture loading, and discovery."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui

from ...config import (
    ACTIVITY_ICON_ATLAS_RELATIVE_PATH,
    DEFAULT_MAP_RELATIVE_PATH,
    IMAGE_SUFFIXES,
    LOOSE_KIND_ICON_FILES,
    NATIVE_CALIBRATION_RELATIVE_PATH,
    discover_project_asset,
    safe_float,
)


@dataclass(frozen=True)
class Snapshot:
    state: dict[str, Any]
    pois: list[dict[str, Any]]
    connected: bool
    message: str
    age: float | None
    live_path: str | None = None
    poi_path: str | None = None


@dataclass(frozen=True)
class MapBounds:
    min_x: float
    max_x: float
    min_y: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def valid(self) -> bool:
        values = (self.min_x, self.max_x, self.min_y, self.max_y)
        return all(math.isfinite(v) for v in values) and self.width > 1.0 and self.height > 1.0

    def fitted_to_aspect(self, aspect: float) -> "MapBounds":
        if not self.valid() or not math.isfinite(aspect) or aspect <= 0:
            return self
        cx = (self.min_x + self.max_x) / 2.0
        cy = (self.min_y + self.max_y) / 2.0
        width, height = self.width, self.height
        current = width / height
        if current < aspect:
            width = height * aspect
        else:
            height = width / aspect
        return MapBounds(cx - width / 2.0, cx + width / 2.0, cy - height / 2.0, cy + height / 2.0)

    @classmethod
    def from_points(cls, points: list[tuple[float, float]], aspect: float) -> "MapBounds | None":
        finite = [(x, y) for x, y in points if math.isfinite(x) and math.isfinite(y)]
        if len(finite) < 4:
            return None
        xs = [p[0] for p in finite]
        ys = [p[1] for p in finite]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span = max(max_x - min_x, max_y - min_y, 1.0)
        padding = max(100.0, span * 0.035)
        bounds = cls(min_x - padding, max_x + padding, min_y - padding, max_y + padding)
        return bounds.fitted_to_aspect(aspect)


@dataclass(frozen=True)
class MapCalibration:
    """Linear world-to-logical-image transform.

    For the stitched Siagarta map, logical space matches the texture pixels
    (see assets/map/w1_siagarta.json). Crops are taken in that space and then
    mapped into the loaded image coordinates when they differ.
    """

    scale_x: float
    offset_x: float
    scale_y: float
    offset_y: float

    def valid(self) -> bool:
        values = (self.scale_x, self.offset_x, self.scale_y, self.offset_y)
        return (
            all(math.isfinite(value) for value in values)
            and abs(self.scale_x) > 1e-9
            and abs(self.scale_y) > 1e-9
        )

    def world_to_logical(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.scale_x * x + self.offset_x,
            self.scale_y * y + self.offset_y,
        )

    def world_to_pixel(self, x: float, y: float) -> tuple[float, float]:
        return self.world_to_logical(x, y)

    def to_json_value(self) -> list[float]:
        return [self.scale_x, self.offset_x, self.scale_y, self.offset_y]

    @classmethod
    def from_json_value(cls, value: Any) -> "MapCalibration | None":
        try:
            raw = json.loads(value) if isinstance(value, str) else value
            if not isinstance(raw, (list, tuple)) or len(raw) != 4:
                return None
            calibration = cls(*(float(item) for item in raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return calibration if calibration.valid() else None

    @classmethod
    def from_bounds(
        cls,
        bounds: MapBounds,
        image_width: int,
        image_height: int,
    ) -> "MapCalibration | None":
        if not bounds.valid() or image_width < 2 or image_height < 2:
            return None
        calibration = cls(
            image_width / bounds.width,
            -bounds.min_x * image_width / bounds.width,
            image_height / bounds.height,
            -bounds.min_y * image_height / bounds.height,
        )
        return calibration if calibration.valid() else None

    @classmethod
    def fit_anchors(
        cls,
        anchors: list[tuple[float, float, float, float]],
    ) -> "MapCalibration | None":
        """Least-squares fit from (world_x, world_y, pixel_u, pixel_v)."""

        if len(anchors) < 2:
            return None

        def fit(samples: list[tuple[float, float]]) -> tuple[float, float] | None:
            mean_world = sum(world for world, _ in samples) / len(samples)
            mean_pixel = sum(pixel for _, pixel in samples) / len(samples)
            denominator = sum((world - mean_world) ** 2 for world, _ in samples)
            if denominator <= 1e-9:
                return None
            scale = sum(
                (world - mean_world) * (pixel - mean_pixel)
                for world, pixel in samples
            ) / denominator
            offset = mean_pixel - scale * mean_world
            return scale, offset

        fit_x = fit([(x, u) for x, _y, u, _v in anchors])
        fit_y = fit([(y, v) for _x, y, _u, v in anchors])
        if fit_x is None or fit_y is None:
            return None
        calibration = cls(fit_x[0], fit_x[1], fit_y[0], fit_y[1])
        return calibration if calibration.valid() else None


@dataclass(frozen=True)
class MapProjection:
    """Map fixed Farever world X/Y onto the source texture.

    World-space display directions are user-verified: -X west, +X east, -Y
    north, +Y south.  ``u_sign`` and ``v_sign`` describe only how the shipped
    PNG stores those axes.  The rendered crop is mirrored when necessary so
    the Atlas display always remains east-right and south-down.
    """

    u_sign: float = -1.0
    v_sign: float = -1.0
    offset_mode: str = "post"
    score: float = 0.0
    inside_ratio: float = 0.0

    @staticmethod
    def _number(obj: dict[str, Any], key: str) -> float | None:
        value = safe_float(obj.get(key), math.nan)
        return value if math.isfinite(value) else None

    @staticmethod
    def _apply(value: float, scale: float, offset: float, mode: str) -> float:
        if mode == "pre":
            return scale * (value + offset)
        return scale * value + offset

    def object_to_pixel(
        self,
        obj: dict[str, Any],
        calibration: MapCalibration,
    ) -> tuple[float, float] | None:
        world_x = self._number(obj, "x")
        world_y = self._number(obj, "y")
        if world_x is None or world_y is None:
            return None
        return (
            self._apply(
                world_x * self.u_sign,
                calibration.scale_x,
                calibration.offset_x,
                self.offset_mode,
            ),
            self._apply(
                world_y * self.v_sign,
                calibration.scale_y,
                calibration.offset_y,
                self.offset_mode,
            ),
        )

    @property
    def label(self) -> str:
        source_x = "+X" if self.u_sign > 0 else "-X"
        source_y = "+Y" if self.v_sign > 0 else "-Y"
        return f"source {source_x}/{source_y}, {self.offset_mode}-scale offset"


@dataclass
class MapTexture:
    image: QtGui.QImage
    label: str
    calibration: MapCalibration | None = None
    calibration_source: str = "uncalibrated"
    logical_width: float = 0.0
    logical_height: float = 0.0
    native_flip_y: bool = False
    native_zoom: float | None = None
    activity_icon_atlas: QtGui.QImage | None = None
    activity_icon_atlas_source: str = "unavailable"
    loose_kind_icons: dict[str, QtGui.QImage] = field(default_factory=dict)
    loose_kind_icon_sources: dict[str, str] = field(default_factory=dict)

    def ensure_dynamic_calibration(
        self,
        pois: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> None:
        del pois, state
        return

    def _logical_to_preview(self, u: float, v: float) -> tuple[float, float]:
        width = self.logical_width if self.logical_width > 1.0 else float(self.image.width())
        height = self.logical_height if self.logical_height > 1.0 else float(self.image.height())
        return (u * float(self.image.width()) / width, v * float(self.image.height()) / height)

    def object_to_pixel(self, obj: dict[str, Any]) -> tuple[float, float] | None:
        if self.calibration is None or self.image.isNull():
            return None
        x = safe_float(obj.get("x"), math.nan)
        y = safe_float(obj.get("y"), math.nan)
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        u, v = self.calibration.world_to_logical(x, y)
        if self.native_flip_y and self.logical_height > 1.0:
            v = self.logical_height - v
        return self._logical_to_preview(u, v)

    def clamp_world_center(self, x: float, y: float) -> tuple[float, float]:
        calibration = self.calibration
        if calibration is None or not calibration.valid():
            return x, y
        logical_w = self.logical_width if self.logical_width > 1.0 else float(self.image.width())
        logical_h = (
            self.logical_height
            if self.logical_height > 1.0
            else float(self.image.height())
        )
        u, raw_v = calibration.world_to_logical(x, y)
        display_v = logical_h - raw_v if self.native_flip_y else raw_v
        u = max(0.0, min(logical_w, u))
        display_v = max(0.0, min(logical_h, display_v))
        raw_v = logical_h - display_v if self.native_flip_y else display_v
        return (
            (u - calibration.offset_x) / calibration.scale_x,
            (raw_v - calibration.offset_y) / calibration.scale_y,
        )

    def render_view(
        self,
        view_center: dict[str, Any],
        pixels_per_metre: float,
        pixel_width: int,
        pixel_height: int,
    ) -> QtGui.QImage | None:
        calibration = self.calibration
        if (
            calibration is None
            or not calibration.valid()
            or self.image.isNull()
            or pixel_width < 2
            or pixel_height < 2
        ):
            return None

        center_x = safe_float(view_center.get("x"), math.nan)
        center_y = safe_float(view_center.get("y"), math.nan)
        if not (math.isfinite(center_x) and math.isfinite(center_y)):
            return None

        logical_w = self.logical_width if self.logical_width > 1.0 else float(self.image.width())
        logical_h = (
            self.logical_height
            if self.logical_height > 1.0
            else float(self.image.height())
        )
        preview_scale_x = float(self.image.width()) / logical_w
        preview_scale_y = float(self.image.height()) / logical_h

        center_u, center_v = calibration.world_to_logical(center_x, center_y)
        if self.native_flip_y:
            center_v = logical_h - center_v

        # Window size must not alter zoom. Derive the world extents from a
        # fixed pixels-per-metre scale so resizing reveals more or less map
        # while roads, markers, and movement keep the same apparent size.
        if not math.isfinite(pixels_per_metre) or pixels_per_metre <= 1e-9:
            return None
        half_world_x = float(pixel_width) / (2.0 * pixels_per_metre)
        half_world_y = float(pixel_height) / (2.0 * pixels_per_metre)
        half_u = abs(calibration.scale_x) * half_world_x
        half_v = abs(calibration.scale_y) * half_world_y
        if half_u <= 1e-6 or half_v <= 1e-6:
            return None

        source_full = QtCore.QRectF(
            center_u - half_u,
            center_v - half_v,
            half_u * 2.0,
            half_v * 2.0,
        )
        source_preview = QtCore.QRectF(
            source_full.left() * preview_scale_x,
            source_full.top() * preview_scale_y,
            source_full.width() * preview_scale_x,
            source_full.height() * preview_scale_y,
        )
        image_rect = QtCore.QRectF(0.0, 0.0, float(self.image.width()), float(self.image.height()))
        visible_source = source_preview.intersected(image_rect)
        if visible_source.isEmpty():
            return None

        view = QtGui.QImage(
            pixel_width,
            pixel_height,
            QtGui.QImage.Format.Format_ARGB32_Premultiplied,
        )
        view.fill(QtGui.QColor("#10151b"))

        target = QtCore.QRectF(
            (visible_source.left() - source_preview.left()) / source_preview.width() * pixel_width,
            (visible_source.top() - source_preview.top()) / source_preview.height() * pixel_height,
            visible_source.width() / source_preview.width() * pixel_width,
            visible_source.height() / source_preview.height() * pixel_height,
        )
        painter = QtGui.QPainter(view)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, self.image, visible_source)
        painter.end()
        return view

    def diagnostic(self, player: dict[str, Any]) -> str:
        if self.calibration is None or self.image.isNull():
            return "uncalibrated"
        player_x = safe_float(player.get("x"), math.nan)
        player_y = safe_float(player.get("y"), math.nan)
        if not (math.isfinite(player_x) and math.isfinite(player_y)):
            return "player unavailable"
        logical_u, logical_v = self.calibration.world_to_logical(player_x, player_y)
        if self.native_flip_y and self.logical_height > 1.0:
            logical_v = self.logical_height - logical_v
        inside = (0.0 <= logical_u <= self.logical_width) and (
            0.0 <= logical_v <= self.logical_height
        )
        preview_u, preview_v = self._logical_to_preview(logical_u, logical_v)
        zoom_text = (
            f"; native zoom={self.native_zoom:.1f}"
            if self.native_zoom is not None and math.isfinite(self.native_zoom)
            else ""
        )
        return (
            f"logical U={logical_u:.1f}, V={logical_v:.1f}; "
            f"preview U={preview_u:.1f}, V={preview_v:.1f}; "
            f"{'inside' if inside else 'OUTSIDE'} "
            f"{self.logical_width:.0f}x{self.logical_height:.0f}{zoom_text}"
        )



def _load_native_calibration(
    game_dir: Path | None,
    image_path: Path | None,
) -> tuple[MapCalibration | None, str, dict[str, Any]]:
    """Read world-to-image calibration for the selected map texture."""

    if image_path is None:
        return None, "native calibration unavailable", {}

    candidates: list[Path] = []
    sidecar = image_path.with_suffix(".json")
    if sidecar.is_file():
        candidates.append(sidecar)
    default_map = discover_project_asset(DEFAULT_MAP_RELATIVE_PATH)
    is_default_map = (
        image_path.name == DEFAULT_MAP_RELATIVE_PATH.name
        or (
            default_map is not None
            and image_path.resolve() == default_map.resolve()
        )
    )
    if is_default_map:
        project_path = discover_project_asset(NATIVE_CALIBRATION_RELATIVE_PATH)
        if project_path is not None:
            candidates.append(project_path)
        if game_dir is not None:
            installed = game_dir / NATIVE_CALIBRATION_RELATIVE_PATH
            if installed.is_file():
                candidates.append(installed)

    seen: set[Path] = set()
    path: Path | None = None
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        path = candidate
        break
    if path is None:
        return None, "native calibration missing from assets", {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"native calibration unreadable: {exc}", {}

    if not isinstance(payload, dict):
        return None, f"native calibration invalid: {path}", {}
    try:
        calibration = MapCalibration(
            scale_x=float(payload["scale_x"]),
            offset_x=float(payload["offset_x"]),
            scale_y=float(payload["scale_y"]),
            offset_y=float(payload["offset_y"]),
        )
    except (KeyError, TypeError, ValueError):
        return None, f"native calibration missing required keys: {path}", payload
    if not calibration.valid():
        return None, f"native calibration contains invalid values: {path}", payload
    return calibration, f"asset file: {path}", payload


def _normalised_keys(obj: dict[str, Any]) -> dict[str, Any]:
    return {re.sub(r"[^a-z0-9]", "", str(key).lower()): value for key, value in obj.items()}


def _bounds_from_dict(obj: dict[str, Any]) -> tuple[MapBounds, int] | None:
    keys = _normalised_keys(obj)
    aliases = {
        "min_x": ("minx", "xmin", "worldminx", "mapminx", "left", "west"),
        "max_x": ("maxx", "xmax", "worldmaxx", "mapmaxx", "right", "east"),
        "min_y": ("miny", "ymin", "worldminy", "mapminy", "bottom", "south"),
        "max_y": ("maxy", "ymax", "worldmaxy", "mapmaxy", "top", "north"),
    }
    found: dict[str, float] = {}
    quality = 0
    for name, candidates in aliases.items():
        for candidate in candidates:
            if candidate in keys:
                value = safe_float(keys[candidate], math.nan)
                if math.isfinite(value):
                    found[name] = value
                    quality += 3 if candidate.startswith(("world", "map")) else 1
                    break
    if len(found) != 4:
        return None
    bounds = MapBounds(found["min_x"], found["max_x"], found["min_y"], found["max_y"])
    return (bounds, quality) if bounds.valid() else None


def _walk_bounds(value: Any, depth: int = 0) -> list[tuple[MapBounds, int]]:
    if depth > 7:
        return []
    out: list[tuple[MapBounds, int]] = []
    if isinstance(value, dict):
        direct = _bounds_from_dict(value)
        if direct is not None:
            out.append(direct)
        for key, child in value.items():
            bonus = (
                4
                if any(
                    token in str(key).lower()
                    for token in ("map", "world", "bound", "extent")
                )
                else 0
            )
            for bounds, score in _walk_bounds(child, depth + 1):
                out.append((bounds, score + bonus))
    elif isinstance(value, list):
        for child in value[:2000]:
            out.extend(_walk_bounds(child, depth + 1))
    return out


def _discover_bounds(
    data_dir: Path,
    image_path: Path,
    image: QtGui.QImage,
) -> tuple[MapBounds | None, str]:
    candidates: list[tuple[int, Path]] = []
    for path in data_dir.rglob("*.json"):
        try:
            if path.stat().st_size > 8_000_000:
                continue
        except OSError:
            continue
        lower = str(path).lower()
        score = 20 if path.parent == image_path.parent else 0
        score += (
            12
            if any(
                token in lower
                for token in ("map", "world", "tile", "bound", "poi")
            )
            else 0
        )
        candidates.append((score, path))
    candidates.sort(key=lambda item: item[0], reverse=True)
    best: tuple[int, MapBounds, Path] | None = None
    for file_score, path in candidates[:120]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        for bounds, structural_score in _walk_bounds(payload):
            area_score = int(math.log10(max(bounds.width * bounds.height, 10.0)))
            total = file_score + structural_score + area_score
            if best is None or total > best[0]:
                best = (total, bounds, path)
    if best is None:
        return None, "unresolved"
    bounds = best[1].fitted_to_aspect(image.width() / max(image.height(), 1))
    return bounds, f"metadata: {best[2].name}"


def _candidate_score(path: Path, width: int, height: int) -> int:
    lower = str(path).lower()
    score = 0
    if "minimap" in lower:
        score += 140
    if "map" in lower:
        score += 100
    if "tile" in lower:
        score += 70
    if "world" in lower or re.search(r"(?:^|[/_\\-])w[0-9](?:[/_\\.-]|$)", lower):
        score += 30
    if any(token in lower for token in ("icon", "atlas", "skill", "button", "frame", "bezel")):
        score -= 100
    score += min(80, int(math.log2(max(width * height, 1))))
    return score


def _tile_coordinates(path: Path) -> tuple[int, int] | None:
    stem = path.stem.lower()
    match = re.search(r"(?:^|[_-])x(-?\d+).*?(?:^|[_-])y(-?\d+)", stem)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"(?:^|[_-])(?:col|column)(-?\d+).*?(?:^|[_-])(?:row)(-?\d+)", stem)
    if match:
        return int(match.group(1)), int(match.group(2))
    numbers = re.findall(r"-?\d+", stem)
    if len(numbers) >= 2:
        return int(numbers[-2]), int(numbers[-1])
    return None


def _load_image(path: Path) -> QtGui.QImage:
    reader = QtGui.QImageReader(str(path))
    reader.setAutoTransform(True)
    return reader.read()


def _discover_map_image(data_dir: Path) -> tuple[QtGui.QImage | None, str, Path | None]:
    image_info: list[tuple[int, Path, int, int]] = []
    for path in data_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        reader = QtGui.QImageReader(str(path))
        size = reader.size()
        if not size.isValid() or size.width() < 256 or size.height() < 256:
            continue
        score = _candidate_score(path, size.width(), size.height())
        image_info.append((score, path, size.width(), size.height()))
    if not image_info:
        return None, "No map-compatible images found", None

    groups: dict[tuple[Path, int, int], list[tuple[int, Path, int, int]]] = {}
    for item in image_info:
        groups.setdefault((item[1].parent, item[2], item[3]), []).append(item)

    mosaic_choices: list[tuple[int, list[tuple[int, Path, int, int]]]] = []
    for items in groups.values():
        if len(items) < 2:
            continue
        indexed = [(_tile_coordinates(item[1]), item) for item in items]
        usable = [(coord, item) for coord, item in indexed if coord is not None]
        parent_text = str(items[0][1].parent).lower()
        if len(usable) >= 2 and (
            "map" in parent_text
            or "tile" in parent_text
            or len(usable) >= 4
        ):
            mosaic_choices.append(
                (
                    max(item[0] for _, item in usable) + len(usable) * 8,
                    [item for _, item in usable],
                )
            )

    if mosaic_choices:
        _, items = max(mosaic_choices, key=lambda choice: choice[0])
        coords = [(_tile_coordinates(item[1]), item) for item in items]
        coords = [(coord, item) for coord, item in coords if coord is not None]
        min_col = min(coord[0] for coord, _ in coords)
        max_col = max(coord[0] for coord, _ in coords)
        min_row = min(coord[1] for coord, _ in coords)
        max_row = max(coord[1] for coord, _ in coords)
        tile_w, tile_h = items[0][2], items[0][3]
        cols, rows = max_col - min_col + 1, max_row - min_row + 1
        total_pixels = cols * tile_w * rows * tile_h
        if 0 < cols <= 64 and 0 < rows <= 64 and total_pixels <= 100_000_000:
            mosaic = QtGui.QImage(
                cols * tile_w,
                rows * tile_h,
                QtGui.QImage.Format.Format_ARGB32_Premultiplied,
            )
            mosaic.fill(QtGui.QColor("#10151b"))
            painter = QtGui.QPainter(mosaic)
            loaded = 0
            for coord, item in coords:
                image = _load_image(item[1])
                if image.isNull():
                    continue
                painter.drawImage(
                    (coord[0] - min_col) * tile_w,
                    (coord[1] - min_row) * tile_h,
                    image,
                )
                loaded += 1
            painter.end()
            if loaded >= 2:
                label = f"{items[0][1].parent} ({loaded} tiles, {cols}x{rows})"
                return mosaic, label, items[0][1]

    image_info.sort(key=lambda item: (item[0], item[2] * item[3]), reverse=True)
    for _, path, _, _ in image_info:
        image = _load_image(path)
        if not image.isNull():
            return image, str(path), path
    return None, "Map images were found but could not be decoded", None


def load_map_texture(
    game_dir: Path | None,
    forced_image: Path | None,
    forced_bounds: list[float] | None,
) -> tuple[MapTexture | None, str]:
    image: QtGui.QImage | None = None
    label = ""
    image_path: Path | None = None
    data_dir: Path | None = None
    if forced_image is not None:
        image_path = forced_image.expanduser().resolve()
        image = _load_image(image_path)
        label = str(image_path)
        data_dir = image_path.parent
    else:
        project_map = discover_project_asset(DEFAULT_MAP_RELATIVE_PATH)
        if project_map is not None:
            image_path = project_map.resolve()
            image = _load_image(image_path)
            label = str(image_path)
            data_dir = image_path.parent
    if (image is None or image.isNull()) and game_dir is not None:
        data_dir = game_dir / "data"
        preferred_path = game_dir / DEFAULT_MAP_RELATIVE_PATH
        if preferred_path.is_file():
            image_path = preferred_path.resolve()
            image = _load_image(image_path)
            label = str(image_path)
        elif data_dir.is_dir():
            image, label, image_path = _discover_map_image(data_dir)
    if image is None or image.isNull():
        reason = label or "Map texture was not found in assets"
        return None, reason

    calibration: MapCalibration | None = None
    calibration_source = "uncalibrated"
    logical_width = float(image.width())
    logical_height = float(image.height())
    native_flip_y = False
    native_zoom: float | None = None
    if forced_bounds is not None:
        bounds = MapBounds(*forced_bounds)
        if not bounds.valid():
            return None, "Invalid --map-bounds values"
        calibration = MapCalibration.from_bounds(bounds, image.width(), image.height())
        calibration_source = "command-line bounds"
    else:
        native_calibration, native_source, native_payload = (
            _load_native_calibration(game_dir, image_path)
        )
        if native_calibration is not None:
            calibration = native_calibration
            calibration_source = native_source
            logical_width = safe_float(
                native_payload.get("logical_width"), float(image.width())
            )
            logical_height = safe_float(
                native_payload.get("logical_height"), float(image.height())
            )
            if logical_width <= 1.0:
                logical_width = float(image.width())
            if logical_height <= 1.0:
                logical_height = float(image.height())
            native_flip_y = bool(native_payload.get("flip_y", False))
            zoom_value = safe_float(native_payload.get("zoom"), math.nan)
            native_zoom = zoom_value if math.isfinite(zoom_value) else None
        elif data_dir is not None and image_path is not None:
            bounds, bounds_source = _discover_bounds(data_dir, image_path, image)
            if bounds is not None:
                calibration = MapCalibration.from_bounds(bounds, image.width(), image.height())
                calibration_source = bounds_source
            else:
                calibration_source = native_source

    activity_icon_atlas: QtGui.QImage | None = None
    activity_icon_atlas_source = "unavailable"
    atlas_path = discover_project_asset(ACTIVITY_ICON_ATLAS_RELATIVE_PATH.name)
    if atlas_path is None and game_dir is not None:
        installed_atlas_path = game_dir / ACTIVITY_ICON_ATLAS_RELATIVE_PATH
        atlas_path = installed_atlas_path if installed_atlas_path.is_file() else None
    if atlas_path is not None:
        if atlas_path.is_file():
            atlas_image = _load_image(atlas_path)
            if not atlas_image.isNull():
                activity_icon_atlas = atlas_image
                activity_icon_atlas_source = str(atlas_path)

    loose_kind_icons: dict[str, QtGui.QImage] = {}
    loose_kind_icon_sources: dict[str, str] = {}
    for kind, filename in LOOSE_KIND_ICON_FILES.items():
        asset_path = discover_project_asset(filename)
        if asset_path is None:
            continue
        asset_image = _load_image(asset_path)
        if asset_image.isNull():
            continue
        loose_kind_icons[kind] = asset_image
        loose_kind_icon_sources[kind] = str(asset_path)

    texture = MapTexture(
        image=image,
        label=label,
        calibration=calibration,
        calibration_source=calibration_source,
        logical_width=logical_width,
        logical_height=logical_height,
        native_flip_y=native_flip_y,
        native_zoom=native_zoom,
        activity_icon_atlas=activity_icon_atlas,
        activity_icon_atlas_source=activity_icon_atlas_source,
        loose_kind_icons=loose_kind_icons,
        loose_kind_icon_sources=loose_kind_icon_sources,
    )
    size_note = f"Loaded {image.width()}x{image.height()} map texture"
    if image_path is not None and image_path.name == DEFAULT_MAP_RELATIVE_PATH.name:
        size_note += (
            f" (Siagarta stitch; logical "
            f"{int(logical_width)}x{int(logical_height)}; {calibration_source})"
        )
    return texture, size_note
