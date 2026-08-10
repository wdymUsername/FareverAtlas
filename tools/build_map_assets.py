#!/usr/bin/env python3
"""Build Farever Atlas world-map texture + calibration from res.map.pak.

Extracts minimap tiles for a world, stitches them into one image, and writes
Atlas-native calibration derived from the tile grid (not eye-fit).

    python tools/build_map_assets.py
    python tools/build_map_assets.py --pak /path/to/res.map.pak --scale 0.35

Outputs (default):
    assets/map/w1_siagarta.webp
    assets/map/w1_siagarta.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

# Game constants for Farever minimap tiles (world units per tile cell).
WORLD_UNITS_PER_TILE = 576.0
NATIVE_TILE_PX = 1024
DEFAULT_WORLD = "w1_siagarta"
MAP_PAK_NAME = "res.map.pak"
APP_ID = 3672400

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "assets" / "map"
WORK_DIR = ROOT / "extracted" / "map"


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class PakFile:
    path: str
    data_pos: int
    size: int


class PakArchive:
    """Minimal Heaps/Shiro PAK reader (header walk + ranged body reads)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = path.open("rb")
        try:
            magic = self._fh.read(4)
            if len(magic) != 4 or magic[:3] != b"PAK":
                raise BuildError(f"not a Heaps PAK: {path}")
            self.version = magic[3]
            header_size, _data_size = struct.unpack("<II", self._fh.read(8))
            if header_size < 16:
                raise BuildError(f"invalid PAK header size in {path}")
            tree = self._fh.read(header_size - 16)
            marker = self._fh.read(4)
            if marker != b"DATA":
                raise BuildError(f"missing DATA marker in {path}")
            self.header_size = header_size
            self.files = self._parse_tree(tree)
        except Exception:
            self._fh.close()
            raise

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "PakArchive":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _parse_tree(self, tree: bytes) -> dict[str, PakFile]:
        pos = 0
        files: dict[str, PakFile] = {}

        def read_entry(prefix: str) -> None:
            nonlocal pos
            if pos >= len(tree):
                raise BuildError("truncated PAK directory tree")
            name_len = tree[pos]
            pos += 1
            name = tree[pos : pos + name_len].decode("utf-8")
            pos += name_len
            flags = tree[pos]
            pos += 1
            full = f"{prefix}/{name}" if prefix else name
            if flags & 1:
                (child_count,) = struct.unpack_from("<I", tree, pos)
                pos += 4
                for _ in range(child_count):
                    read_entry(full)
                return
            if flags & 2:
                (data_pos,) = struct.unpack_from("<d", tree, pos)
                pos += 8
                data_pos = int(data_pos)
            else:
                (data_pos,) = struct.unpack_from("<I", tree, pos)
                pos += 4
            size, _checksum = struct.unpack_from("<II", tree, pos)
            pos += 8
            files[full] = PakFile(full, data_pos, size)

        read_entry("")
        return files

    def read(self, entry: PakFile) -> bytes:
        self._fh.seek(self.header_size + entry.data_pos)
        data = self._fh.read(entry.size)
        if len(data) != entry.size:
            raise BuildError(f"short read for {entry.path}")
        return data


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    home = Path.home()
    if sys.platform == "win32":
        candidates = [
            Path(value) / "Steam"
            for value in (
                os.environ.get("PROGRAMFILES(X86)", ""),
                os.environ.get("PROGRAMFILES", ""),
            )
            if value
        ]
    else:
        candidates = [
            home / ".local/share/Steam",
            home / ".steam/steam",
            home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        ]
        candidates.extend(home.glob("Games/*/steam"))
        candidates.extend(home.glob("Games/*/SteamLibrary"))
        candidates.append(home / "SteamLibrary")

    def add(path: Path) -> None:
        path = path.expanduser()
        if path.is_dir() and path not in roots:
            roots.append(path)

    for root in candidates:
        add(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            add(Path(raw.replace("\\\\", "\\")))
    return roots


def discover_game_dir() -> Path | None:
    env = os.environ.get("FAREVER_GAME_DIR", "").strip()
    if env:
        candidate = Path(env).expanduser()
        if (candidate / "Farever.exe").is_file():
            return candidate.resolve()
    conf = ROOT / "user_data" / "game_dir.conf"
    if conf.is_file():
        try:
            line = conf.read_text(encoding="utf-8").splitlines()[0].strip()
        except OSError:
            line = ""
        if line:
            candidate = Path(line).expanduser()
            if (candidate / "Farever.exe").is_file():
                return candidate.resolve()
    for steam in _steam_roots():
        manifest = steam / "steamapps" / f"appmanifest_{APP_ID}.acf"
        install_name = "Farever"
        if manifest.is_file():
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
                match = re.search(r'"installdir"\s+"([^"]+)"', text)
                if match:
                    install_name = match.group(1)
            except OSError:
                pass
        candidate = steam / "steamapps" / "common" / install_name
        if (candidate / "Farever.exe").is_file():
            return candidate.resolve()
    return None


def discover_map_pak(explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise BuildError(f"PAK not found: {path}")
        return path
    game_dir = discover_game_dir()
    if game_dir is None:
        raise BuildError(
            "Could not locate Farever. Pass --pak or set FAREVER_GAME_DIR."
        )
    path = game_dir / MAP_PAK_NAME
    if not path.is_file():
        raise BuildError(f"{MAP_PAK_NAME} missing under {game_dir}")
    return path.resolve()


def _tile_pattern(world: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?i)^Level/World/{re.escape(world)}\.dat/minimap/"
        rf"(-?\d+)_(-?\d+)_{NATIVE_TILE_PX}\.png$"
    )


def collect_tiles(
    archive: PakArchive, world: str
) -> dict[tuple[int, int], PakFile]:
    pattern = _tile_pattern(world)
    tiles: dict[tuple[int, int], PakFile] = {}
    for path, entry in archive.files.items():
        match = pattern.match(path.replace("\\", "/"))
        if match:
            tiles[(int(match.group(1)), int(match.group(2)))] = entry
    if not tiles:
        raise BuildError(f"no minimap tiles for world {world!r} in {archive.path.name}")
    return tiles


def _require_image_deps() -> tuple[object, object]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise BuildError(
            "Pillow is required. Install tool deps with:\n"
            "  .venv/bin/pip install -r tools/requirements.txt"
        ) from exc
    try:
        import texture2ddecoder
    except ImportError as exc:
        raise BuildError(
            "texture2ddecoder is required for BC7 DDS tiles. Install tool deps with:\n"
            "  .venv/bin/pip install -r tools/requirements.txt"
        ) from exc
    return Image, texture2ddecoder


def _decode_tile_image(blob: bytes, work_png: Path) -> object:
    """Decode a tile payload (PNG, or DDS/BC7 stored under a .png name)."""
    Image, texture2ddecoder = _require_image_deps()

    if blob[:4] != b"DDS ":
        from io import BytesIO

        image = Image.open(BytesIO(blob)).convert("RGBA")
        if work_png is not None:
            image.save(work_png)
        return image

    if len(blob) < 148:
        raise BuildError(f"truncated DDS tile ({work_png.name})")
    height, width = struct.unpack_from("<II", blob, 12)
    fourcc = blob[84:88]
    if fourcc != b"DX10":
        raise BuildError(
            f"unsupported DDS fourcc {fourcc!r} in {work_png.name} (expected DX10/BC7)"
        )
    (dxgi_format,) = struct.unpack_from("<I", blob, 128)
    # DXGI_FORMAT_BC7_UNORM = 98, BC7_UNORM_SRGB = 99
    if dxgi_format not in (98, 99):
        raise BuildError(
            f"unsupported DXGI format {dxgi_format} in {work_png.name} (need BC7)"
        )
    payload = blob[148:]
    expected = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 16
    if len(payload) < expected:
        raise BuildError(
            f"DDS payload too small for {width}x{height} BC7 in {work_png.name}"
        )
    rgba = texture2ddecoder.decode_bc7(payload[:expected], width, height)
    image = Image.frombytes("RGBA", (width, height), rgba, "raw", "BGRA")
    image.save(work_png)
    return image


def stitch_tiles(
    archive: PakArchive,
    tiles: dict[tuple[int, int], PakFile],
    scale: float,
    work_dir: Path,
) -> tuple[object, int, int, int, int, int]:
    """Return (PIL.Image, width, height, x0, y0, tile_px)."""
    Image, _texture2ddecoder = _require_image_deps()

    xs = sorted({tx for tx, _ty in tiles})
    ys = sorted({ty for _tx, ty in tiles})
    x0, x1 = xs[0], xs[-1]
    y0, y1 = ys[0], ys[-1]
    tile_px = max(1, int(round(NATIVE_TILE_PX * scale)))
    width = (x1 - x0 + 1) * tile_px
    height = (y1 - y0 + 1) * tile_px

    work_dir.mkdir(parents=True, exist_ok=True)
    mosaic = Image.new("RGB", (width, height), (16, 16, 16))

    loaded = 0
    for (tx, ty), entry in sorted(tiles.items()):
        blob = archive.read(entry)
        work_png = work_dir / f"{tx}_{ty}_{NATIVE_TILE_PX}.png"
        image = _decode_tile_image(blob, work_png).convert("RGB")
        if tile_px != NATIVE_TILE_PX:
            image = image.resize((tile_px, tile_px), Image.Resampling.LANCZOS)
        # +Y south/down: increasing tile Y paints downward in the image.
        mosaic.paste(image, ((tx - x0) * tile_px, (ty - y0) * tile_px))
        loaded += 1
    if loaded < 1:
        raise BuildError("no tiles decoded")
    return mosaic, width, height, x0, y0, tile_px


def atlas_calibration(
    *,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
    tile_px: int,
    width: int,
    height: int,
    world: str,
) -> dict[str, object]:
    """World→image transform for Atlas MapCalibration (+Y down, no flip)."""
    px_per_unit = tile_px / WORLD_UNITS_PER_TILE
    origin_x = x0 * WORLD_UNITS_PER_TILE
    origin_y = y0 * WORLD_UNITS_PER_TILE
    scale = px_per_unit
    offset_x = -origin_x * px_per_unit
    offset_y = -origin_y * px_per_unit
    return {
        "world": world,
        "schema": 1,
        "source": "tile-grid",
        "scale_x": scale,
        "offset_x": offset_x,
        "scale_y": scale,
        "offset_y": offset_y,
        "flip_y": False,
        "logical_width": width,
        "logical_height": height,
        "width": width,
        "height": height,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "px_per_unit": px_per_unit,
        "units_per_tile": WORLD_UNITS_PER_TILE,
        "tile_px": tile_px,
        "tiles_x": [x0, x1],
        "tiles_y": [y0, y1],
        "y_down": True,
    }


def save_webp(image: object, path: Path, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "WEBP", quality=quality, method=6)


def build(
    *,
    pak: Path,
    world: str,
    scale: float,
    out_dir: Path,
    quality: int,
    keep_tiles: bool,
) -> Path:
    if not (0.05 <= scale <= 1.0):
        raise BuildError("--scale must be between 0.05 and 1.0")
    if not (1 <= quality <= 100):
        raise BuildError("--quality must be between 1 and 100")

    world_key = world.strip().lower().replace(" ", "_")
    work_dir = WORK_DIR / world_key
    if work_dir.exists() and not keep_tiles:
        for child in work_dir.glob("*.png"):
            child.unlink(missing_ok=True)

    with PakArchive(pak) as archive:
        tiles = collect_tiles(archive, world_key)
        print(
            f"[*] {pak.name}: {len(tiles)} tiles for {world_key}",
            file=sys.stderr,
        )
        image, width, height, x0, y0, tile_px = stitch_tiles(
            archive, tiles, scale, work_dir
        )

    x1 = x0 + (width // tile_px) - 1
    y1 = y0 + (height // tile_px) - 1
    print(
        f"[*] stitch {width}x{height} "
        f"(tiles x {x0}..{x1}, y {y0}..{y1}, tile {tile_px}px)",
        file=sys.stderr,
    )

    meta = atlas_calibration(
        x0=x0,
        x1=x1,
        y0=y0,
        y1=y1,
        tile_px=tile_px,
        width=width,
        height=height,
        world=world_key,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    image_path = out_dir / f"{world_key}.webp"
    meta_path = out_dir / f"{world_key}.json"
    save_webp(image, image_path, quality)
    meta_path.write_text(
        json.dumps(meta, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"[+] {image_path} ({image_path.stat().st_size:,} bytes)", file=sys.stderr)
    print(f"[+] {meta_path}", file=sys.stderr)

    if not keep_tiles:
        for child in work_dir.glob("*.png"):
            child.unlink(missing_ok=True)
        try:
            work_dir.rmdir()
        except OSError:
            pass
    return image_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pak", type=Path, default=None, help="Path to res.map.pak")
    parser.add_argument("--world", default=DEFAULT_WORLD, help="World id (default w1_siagarta)")
    parser.add_argument(
        "--scale",
        type=float,
        default=0.35,
        help="Tile downsample factor (1.0 = full 1024px tiles → 11264²; 0.35 → ~3938²)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=90,
        help="WebP quality 1-100 (default 90)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output directory (default {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--keep-tiles",
        action="store_true",
        help="Keep extracted tile PNGs under extracted/map/",
    )
    args = parser.parse_args()
    try:
        pak = discover_map_pak(args.pak)
        build(
            pak=pak,
            world=args.world,
            scale=args.scale,
            out_dir=args.out_dir,
            quality=args.quality,
            keep_tiles=args.keep_tiles,
        )
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
