#!/usr/bin/env python3
"""ABANDONED Phase 0 spike — terrain.bin → synthetic instance maps.

## Goal (failed)

Prove we could bake dungeon/instance minimaps from extracted `L0_*/terrain.bin`
chunks (height + biome schematic), stitch them, and later load them in Atlas
instead of the blank local-instance view. Target proof: BeeHive dungeon, with
world-chunk validation against the official Siagarta minimap crop.

## What worked

- Parse `terrain.bin`: Haxe biome palette + HxS ChunkGameplayData + 1000 cells
- Decode the 1000-slot base-10 LOD pool:
    - last digit != 9 → fine leaves (900)
    - *9 (not *99) → mid parents (90)
    - *99 (not 999) → coarse parents (9)
    - 999 → root
- Leaf sample guess: f32 height @ byte 0, material index @ byte 7
- Emit layout-hypothesis PNGs / stitches under `extracted/map/terrain_spike/`

## Why it failed (hard gate)

Chunks hold editable terrain data, not baked minimap art. The open problem was
**cell index → local (x, y)**. Every layout hypothesis painted biome noise or
horizontal stripes — debug views, not geography:

  30x30, dec_9x100, dec_90x10, dec_9x10x10, dec_10x90, raw_10x100_skip9
  plus nested 3×3 / edge / mid trials (compare sheets under world_L0_2_0/)

Validated world chunk `L0_+2_+0` against `assets/map/w1_siagarta.webp` crop of
the same region (circular plateau, paths, water). Visual mismatch + automated
correlation stayed near noise (|r|≈0.15 vs random ≈0.09) across layouts,
flips, and rotates. Parent-node expansion was not solved.

Without a correct spatial map, stitches cannot be calibrated to player coords
and are useless for navigation. Full engine reverse-engineering of the LOD
payloads is out of scope; Phases 1–3 (bake tool + Atlas wiring) were cancelled.
Keep the blank local-instance map.

## Status

Abandoned 2026-08-08. Keep this script only as format notes / decoder scratch.
Do not treat outputs as map assets. Safe to delete with
`extracted/map/terrain_spike/`.

## Usage (historical)

    python tools/spike_terrain_chunk.py
    python tools/spike_terrain_chunk.py --level Z1_POI_Dungeon_BeeHive
    python tools/spike_terrain_chunk.py --chunk L0_-2_+1 --layouts 30x30,dec_9x100

Outputs under extracted/map/terrain_spike/<level>/
"""

from __future__ import annotations

import argparse
import base64
import re
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEVEL = "Z1_POI_Dungeon_BeeHive"
LEVELS_ROOT = ROOT / "extracted" / "res.levels" / "Level" / "POI"
OUT_ROOT = ROOT / "extracted" / "map" / "terrain_spike"
WORLD_UNITS_PER_CHUNK = 576.0

# Distinct colors for biome palette slots (index into chunk material list).
BIOME_RGB = [
    (196, 150, 60),  # Hive / paper
    (80, 140, 55),  # grass
    (210, 170, 90),  # Hive1
    (160, 110, 50),  # ground
    (90, 150, 70),  # Plains
    (220, 60, 60),  # Debug
    (180, 100, 200),
    (70, 120, 180),
    (140, 140, 140),
]


class SpikeError(RuntimeError):
    pass


def _b64_fix(text: str) -> bytes:
    cleaned = re.sub(r"[^A-Za-z0-9+/]", "", text)
    while len(cleaned) % 4 == 1:
        cleaned = cleaned[:-1]
    return base64.b64decode(cleaned + "=" * ((-len(cleaned)) % 4))


def _parse_material_palette(blob: bytes, start: int) -> tuple[list[str], int]:
    if blob[start : start + 1] != b"a":
        raise SpikeError(f"expected Haxe array at {start}")
    i = start + 1
    names: list[str] = []
    while i < len(blob) and blob[i : i + 1] != b"h":
        tag = blob[i : i + 1]
        if tag == b"n":
            # Haxe null slot in the biome list — keep a placeholder index.
            names.append(f"null_{len(names)}")
            i += 1
            continue
        if tag != b"y":
            raise SpikeError(f"expected Haxe string at {i}: {blob[i : i + 20]!r}")
        i += 1
        colon = blob.index(b":", i)
        n = int(blob[i:colon])
        i = colon + 1
        names.append(blob[i : i + n].decode("utf-8"))
        i += n
    if i >= len(blob) or blob[i : i + 1] != b"h":
        raise SpikeError("truncated material palette")
    return names, i + 1


def _find_material_palette(blob: bytes) -> int:
    """Locate the leading Haxe string-array palette (`a` + `yN:` / `n` … `h`)."""
    for match in re.finditer(rb"a(?:y\d+:|n)", blob):
        pos = match.start()
        # Real headers put the palette within the first few dozen bytes.
        if pos > 64:
            break
        try:
            _names, _end = _parse_material_palette(blob, pos)
            return pos
        except (SpikeError, ValueError, IndexError):
            continue
    raise SpikeError("no material palette in terrain.bin")


def parse_terrain_bin(path: Path) -> tuple[list[str], dict[int, bytes]]:
    blob = path.read_bytes()
    apos = _find_material_palette(blob)
    materials, i = _parse_material_palette(blob, apos)
    text = blob[i:].decode("latin1", errors="replace")
    lines = [ln for ln in text.split("\n") if ln != ""]
    try:
        start = next(j for j, ln in enumerate(lines) if re.fullmatch(r"\d{3,4}", ln))
    except StopIteration as exc:
        raise SpikeError(f"no numbered cells in {path}") from exc

    cells: dict[int, list[str]] = {}
    idx: int | None = None
    pending: list[str] = []
    for ln in lines[start:]:
        if re.fullmatch(r"\d{3,4}", ln):
            if idx is not None:
                cells[idx] = pending
            idx = int(ln)
            pending = []
        else:
            pending.append(ln)
    if idx is not None:
        cells[idx] = pending

    decoded = {
        key: b"".join(_b64_fix(part) for part in parts) for key, parts in cells.items()
    }
    if len(decoded) != 1000 or set(decoded) != set(range(1000)):
        raise SpikeError(
            f"{path.name}: expected cells 0..999, got {len(decoded)} "
            f"(max={max(decoded) if decoded else None})"
        )
    return materials, decoded


def leaf_sample(payload: bytes) -> tuple[float, int] | None:
    """First 10-byte height/material sample from a cell payload."""
    if len(payload) < 10:
        return None
    height = struct.unpack_from("<f", payload, 0)[0]
    if not (abs(height) < 1e6):
        return None
    mat = payload[7]
    return height, int(mat)


def is_fine_leaf_index(index: int) -> bool:
    return index % 10 != 9


def remap_fine_index(index: int) -> int:
    """Map pool index → dense 0..899 among fine slots (skip *9 parents)."""
    if not is_fine_leaf_index(index):
        raise ValueError(index)
    block = index // 10
    digit = index % 10  # 0..8
    return block * 9 + digit


LAYOUTS = (
    "30x30",
    "dec_9x100",
    "dec_90x10",
    "dec_9x10x10",
    "dec_10x90",
    "raw_10x100_skip9",
)


def layout_xy(name: str, index: int) -> tuple[int, int, int, int] | None:
    """Return (x, y, width, height) for a fine leaf index, or None if skip."""
    if not is_fine_leaf_index(index):
        return None

    fine = index % 10  # 0..8
    mid = (index // 10) % 10  # 0..9
    coarse = index // 100  # 0..9

    if name == "30x30":
        j = remap_fine_index(index)
        return j % 30, j // 30, 30, 30

    if name == "dec_9x100":
        return fine, index // 10, 9, 100

    if name == "dec_90x10":
        return mid * 9 + fine, coarse, 90, 10

    if name == "dec_10x90":
        # swap axes vs dec_90x10
        return coarse, mid * 9 + fine, 10, 90

    if name == "dec_9x10x10":
        return fine, mid + 10 * coarse, 9, 100

    if name == "raw_10x100_skip9":
        return index % 10, index // 10, 10, 100

    raise SpikeError(f"unknown layout {name!r}")


def _require_pil():
    try:
        from PIL import Image
    except ImportError as exc:
        raise SpikeError(
            "Pillow required. Install with:\n"
            "  .venv/bin/pip install -r tools/requirements.txt"
        ) from exc
    return Image


def biome_color(mat: int, materials: list[str]) -> tuple[int, int, int]:
    if 0 <= mat < len(BIOME_RGB):
        return BIOME_RGB[mat]
    return (110, 110, 110)


def shade(rgb: tuple[int, int, int], height: float, h_min: float, h_max: float) -> tuple[int, int, int]:
    span = max(h_max - h_min, 1e-3)
    t = (height - h_min) / span  # 0..1
    factor = 0.45 + 0.55 * t
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def render_chunk(
    materials: list[str],
    cells: dict[int, bytes],
    layout: str,
    cell_px: int,
) -> object:
    Image = _require_pil()
    samples: dict[int, tuple[float, int]] = {}
    for idx, payload in cells.items():
        if not is_fine_leaf_index(idx):
            continue
        sample = leaf_sample(payload)
        if sample is not None:
            samples[idx] = sample
    if not samples:
        raise SpikeError("no fine leaf samples")

    # probe size
    _, _, width, height = next(
        xy for idx in samples for xy in [layout_xy(layout, idx)] if xy is not None
    )
    heights = [h for h, _m in samples.values()]
    h_min, h_max = min(heights), max(heights)

    img = Image.new("RGB", (width * cell_px, height * cell_px), (20, 22, 28))
    for idx, (h, mat) in samples.items():
        placed = layout_xy(layout, idx)
        if placed is None:
            continue
        x, y, _w, _h = placed
        color = shade(biome_color(mat, materials), h, h_min, h_max)
        x0, y0 = x * cell_px, y * cell_px
        for py in range(y0, y0 + cell_px):
            for px in range(x0, x0 + cell_px):
                img.putpixel((px, py), color)
    return img


def parse_chunk_dir_name(name: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"L0_([+-]?\d+)_([+-]?\d+)", name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def find_level_dir(level: str) -> Path:
    direct = Path(level).expanduser()
    if direct.is_dir() and any(direct.glob("L0_*")):
        return direct.resolve()
    needle = level.strip().removesuffix(".dat")
    matches = list(LEVELS_ROOT.glob(f"**/{needle}.dat"))
    if not matches:
        matches = list(LEVELS_ROOT.glob(f"**/*{needle}*.dat"))
    if not matches:
        raise SpikeError(f"level not found under {LEVELS_ROOT}: {level}")
    if len(matches) > 1:
        exact = [p for p in matches if p.stem.lower() == needle.lower()]
        matches = exact or matches
    return matches[0].resolve()


def stitch_level(
    level_dir: Path,
    layout: str,
    cell_px: int,
    chunk_px: int | None,
) -> tuple[object, list[tuple[int, int]], list[str]]:
    Image = _require_pil()
    chunk_dirs = sorted(
        (parse_chunk_dir_name(p.name), p)
        for p in level_dir.iterdir()
        if p.is_dir() and parse_chunk_dir_name(p.name) is not None
    )
    chunk_dirs = [(xy, p) for xy, p in chunk_dirs if xy is not None]
    if not chunk_dirs:
        raise SpikeError(f"no L0_* chunks in {level_dir}")

    rendered: dict[tuple[int, int], object] = {}
    materials_acc: list[str] = []
    for (cx, cy), path in chunk_dirs:
        terrain = path / "terrain.bin"
        if not terrain.is_file():
            continue
        materials, cells = parse_terrain_bin(terrain)
        if not materials_acc:
            materials_acc = materials
        rendered[(cx, cy)] = render_chunk(materials, cells, layout, cell_px)

    xs = [c[0] for c in rendered]
    ys = [c[1] for c in rendered]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    sample = next(iter(rendered.values()))
    cw, ch = sample.size
    # Uniform chunk tile size for the mosaic. Preserve aspect unless --chunk-px set.
    if chunk_px is not None and chunk_px > 0:
        # Fit inside chunk_px×chunk_px box, keep aspect (no stretch).
        scale = chunk_px / max(cw, ch)
        tw = max(1, int(round(cw * scale)))
        th = max(1, int(round(ch * scale)))
        tiles = {
            key: img.resize((tw, th), Image.Resampling.NEAREST)
            for key, img in rendered.items()
        }
        cw, ch = tw, th
    else:
        tiles = rendered

    mosaic = Image.new(
        "RGB",
        ((x1 - x0 + 1) * cw, (y1 - y0 + 1) * ch),
        (12, 14, 18),
    )
    for (cx, cy), img in tiles.items():
        # +Y down in image space (Atlas world maps use y_down)
        mosaic.paste(img, ((cx - x0) * cw, (cy - y0) * ch))
    return mosaic, sorted(rendered), materials_acc


def write_legend(path: Path, materials: list[str]) -> None:
    lines = ["# biome palette (chunk-local indices)", ""]
    for i, name in enumerate(materials):
        rgb = biome_color(i, materials)
        lines.append(f"{i}\t{name}\tRGB{rgb}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize_pool(cells: dict[int, bytes]) -> str:
    bands = {
        "fine(*0-*8)": [i for i in range(1000) if i % 10 != 9],
        "mid(*9)": [i for i in range(1000) if i % 10 == 9 and i % 100 != 99],
        "coarse(*99)": [i for i in range(1000) if i % 100 == 99 and i != 999],
        "root(999)": [999],
    }
    parts = []
    for label, idxs in bands.items():
        lens = Counter(len(cells[i]) for i in idxs)
        parts.append(f"{label}: {dict(lens.most_common(4))}")
    return "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", default=DEFAULT_LEVEL, help="Level folder name or path")
    parser.add_argument(
        "--chunk",
        default=None,
        help="Single chunk dir name (e.g. L0_-2_+1). Default: all chunks + stitch",
    )
    parser.add_argument(
        "--layouts",
        default=",".join(LAYOUTS),
        help=f"Comma list of layouts ({', '.join(LAYOUTS)})",
    )
    parser.add_argument("--cell-px", type=int, default=4, help="Pixels per fine cell")
    parser.add_argument(
        "--chunk-px",
        type=int,
        default=0,
        help="If >0, fit each chunk tile inside this square (keeps aspect). 0=native size",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default extracted/map/terrain_spike/<level>)",
    )
    args = parser.parse_args(argv)

    level_dir = find_level_dir(args.level)
    out_dir = args.out or (OUT_ROOT / level_dir.stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    layouts = [part.strip() for part in args.layouts.split(",") if part.strip()]
    for name in layouts:
        if name not in LAYOUTS:
            raise SpikeError(f"unknown layout {name!r}; choose from {LAYOUTS}")

    print(f"[*] level {level_dir}", file=sys.stderr)
    print(f"[*] out   {out_dir}", file=sys.stderr)
    print(
        f"[*] assume {WORLD_UNITS_PER_CHUNK} world units / chunk "
        "(validate against live player coords)",
        file=sys.stderr,
    )

    if args.chunk:
        chunk_path = level_dir / args.chunk
        terrain = chunk_path / "terrain.bin"
        if not terrain.is_file():
            raise SpikeError(f"missing {terrain}")
        materials, cells = parse_terrain_bin(terrain)
        write_legend(out_dir / f"{args.chunk}_legend.txt", materials)
        print(f"[*] {args.chunk} pool: {summarize_pool(cells)}", file=sys.stderr)
        print(f"[*] materials: {materials}", file=sys.stderr)
        for layout in layouts:
            img = render_chunk(materials, cells, layout, args.cell_px)
            dest = out_dir / f"{args.chunk}_{layout}.png"
            img.save(dest)
            print(f"[+] {dest} ({img.size[0]}x{img.size[1]})", file=sys.stderr)
        return 0

    # all chunks: per-chunk previews for first layout + stitches for all layouts
    chunk_names = sorted(
        p.name
        for p in level_dir.iterdir()
        if p.is_dir() and parse_chunk_dir_name(p.name) is not None
    )
    if not chunk_names:
        raise SpikeError(f"no chunks in {level_dir}")

    # detail dump for densest chunk
    densest = max(
        chunk_names,
        key=lambda name: (level_dir / name / "terrain.bin").stat().st_size
        if (level_dir / name / "terrain.bin").is_file()
        else 0,
    )
    materials, cells = parse_terrain_bin(level_dir / densest / "terrain.bin")
    write_legend(out_dir / "legend.txt", materials)
    print(f"[*] densest {densest}: {summarize_pool(cells)}", file=sys.stderr)
    print(f"[*] materials: {materials}", file=sys.stderr)
    for layout in layouts:
        img = render_chunk(materials, cells, layout, args.cell_px)
        dest = out_dir / f"{densest}_{layout}.png"
        img.save(dest)
        print(f"[+] {dest}", file=sys.stderr)

    meta_lines = [
        "STATUS=ABANDONED (2026-08-08) — index→XY never matched real geography",
        f"level={level_dir}",
        f"chunks={','.join(chunk_names)}",
        f"units_per_chunk={WORLD_UNITS_PER_CHUNK}",
        "y_down=true (image +Y with increasing chunk cy)",
        "",
        "Format notes (decoder only — not a map pipeline):",
        "- terrain.bin = Haxe biome palette + HxS ChunkGameplayData + 1000 base64 cells",
        "- LOD pool: fine i%10!=9 (900); mid *9 (90); coarse *99 (9); root 999",
        "- leaf sample = first 10 bytes: f32 height @0, material index @7",
        "- layouts are failed hypotheses; outputs are biome noise/stripes, not maps",
        "- failed validate: world L0_+2_+0 spike vs w1_siagarta.webp crop (|r|~noise)",
        "- cancelled: dungeon stitch player overlay, bake tool, Atlas instance maps",
        "",
    ]
    for layout in layouts:
        mosaic, coords, mats = stitch_level(
            level_dir, layout, args.cell_px, args.chunk_px
        )
        dest = out_dir / f"stitch_{layout}.png"
        mosaic.save(dest)
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        print(
            f"[+] {dest} chunks x {min(xs)}..{max(xs)} y {min(ys)}..{max(ys)} "
            f"size {mosaic.size[0]}x{mosaic.size[1]}",
            file=sys.stderr,
        )
        meta_lines.append(
            f"stitch_{layout}: origin_chunk=({min(xs)},{min(ys)}) "
            f"span=({max(xs) - min(xs) + 1},{max(ys) - min(ys) + 1}) "
            f"px={mosaic.size[0]}x{mosaic.size[1]}"
        )
    (out_dir / "README.txt").write_text("\n".join(meta_lines) + "\n", encoding="utf-8")
    print(f"[+] {out_dir / 'README.txt'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SpikeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
