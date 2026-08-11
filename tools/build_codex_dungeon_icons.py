#!/usr/bin/env python3
"""Build Codex dungeon tile icons: loading-screen scene + boss portrait (B-glow)."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CDB_PATH = ROOT / "extracted" / "res.light" / "data.cdb"
EXTRACTED_RES = ROOT / "extracted" / "res"
LOADING_DIR = ROOT / "extracted" / "res" / "UI" / "Window" / "LoadingScreen" / "Background"
CATALOG_PATH = ROOT / "assets" / "codex_catalog.json"
OUT_DIR = ROOT / "assets" / "portraits" / "dungeons"
OUT_HEADER_DIR = ROOT / "assets" / "portraits" / "dungeons" / "headers"
OUT_MAP = ROOT / "assets" / "dungeon_portraits.json"
BOSS_PORTRAIT_DIR = ROOT / "assets" / "portraits"
SIZE = 96
HEADER_WIDTH = 480
HEADER_HEIGHT = 168

# Catalog dungeon id -> (boss unit id, loading-screen filename).
DUNGEON_ICON_SOURCES: dict[str, tuple[str, str]] = {
    "Bee_Hive": ("Gatsbee", "Beehive.png"),
    "Z1_POI_Dungeon_ManfishAbyss": ("SpongeBlob", "ManfishAbyss.png"),
    "R1_POI_AmaymonGoulp": ("Reblochonk", "Kobold_Mine.png"),
    "R1_POI_Boss_Ratsar": ("Ratsar", "Ratsar.png"),
    "R1_POI_CleodorasNest": ("Cleodora", "Cleodora.png"),
    "R1_POI_CrimsonSacristy": ("Phrixes", "Phrixes.png"),
    # No dedicated loading screen in level data; thematic fallbacks.
    "R1_POI_Dungeon_AbbandonedMines": ("Golcano", "Default.png"),
    "R1_POI_Dungeon_CrimsonBarraks_POI_Def": ("RobinHoof", "Barracks.png"),
    "R1_POI_Dungeon_Manfish_Ruins": ("Nepsilon", "Manfish_Ruins.png"),
    "R1_POI_GorgonsHollow": ("MunsterChuck", "Munster_Chuck.png"),
    "R1_POI_MokshisHivetree": ("Mokshi", "Mokshi.png"),
    "R1_POI_Nepsid_Boss": ("Crabgantua", "Crabgantua.png"),
}


class BuildError(RuntimeError):
    pass


def _require_deps():
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter
    except ImportError as exc:
        raise BuildError(
            "Pillow required: tools/.venv/bin/pip install -r tools/requirements.txt"
        ) from exc
    try:
        import texture2ddecoder
    except ImportError as exc:
        raise BuildError(
            "texture2ddecoder required: tools/.venv/bin/pip install -r tools/requirements.txt"
        ) from exc
    return Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, texture2ddecoder


def decode_dds(path: Path, Image, texture2ddecoder):
    blob = path.read_bytes()
    if blob[:4] != b"DDS ":
        raise BuildError(f"not DDS: {path}")
    if len(blob) < 148:
        raise BuildError(f"truncated DDS: {path}")
    height, width = struct.unpack_from("<II", blob, 12)
    fourcc = blob[84:88]
    if fourcc != b"DX10":
        raise BuildError(f"unsupported DDS fourcc {fourcc!r}: {path}")
    (dxgi_format,) = struct.unpack_from("<I", blob, 128)
    if dxgi_format not in (98, 99):
        raise BuildError(f"unsupported DXGI {dxgi_format}: {path}")
    payload = blob[148:]
    expected = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 16
    if len(payload) < expected:
        raise BuildError(f"DDS payload too small: {path}")
    rgba = texture2ddecoder.decode_bc7(payload[:expected], width, height)
    return Image.frombytes("RGBA", (width, height), rgba, "raw", "BGRA")


def resolve_source(rel_png: str) -> Path | None:
    rel = Path(rel_png)
    dds = EXTRACTED_RES / rel.with_suffix(".dds")
    if dds.is_file():
        return dds
    png = EXTRACTED_RES / rel
    if png.is_file():
        return png
    return None


def load_unit_gfx(cdb: dict) -> dict[str, str]:
    sheets = {sheet["name"]: sheet for sheet in cdb["sheets"]}
    out: dict[str, str] = {}
    for line in sheets["unit"]["lines"]:
        unit_id = line.get("id")
        gfx = line.get("gfx")
        if not unit_id or not isinstance(gfx, dict) or not gfx.get("file"):
            continue
        out[str(unit_id)] = str(gfx["file"])
    return out


def ensure_boss_portrait(
    boss_id: str,
    gfx_file: str,
    *,
    Image,
    texture2ddecoder,
    size: int = 128,
) -> Path | None:
    """Return path to a boss portrait webp under assets/portraits/, converting if needed."""
    # Prefer already-built unit portrait asset name from gfx.
    rel = Path(gfx_file)
    parts = list(rel.parts)
    if len(parts) >= 3 and parts[0] == "UI" and parts[1] == "Portraits":
        parts = parts[2:]
    asset_rel = Path(*parts).with_suffix(".webp")
    out_path = BOSS_PORTRAIT_DIR / asset_rel
    if out_path.is_file():
        return out_path
    source = resolve_source(gfx_file)
    if source is None:
        print(f"MISS boss portrait {boss_id} <- {gfx_file}", file=sys.stderr)
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".dds":
        image = decode_dds(source, Image, texture2ddecoder)
    else:
        image = Image.open(source).convert("RGBA")
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    image.save(out_path, "WEBP", quality=82, method=4)
    return out_path


def radial_vignette(Image, ImageFilter, size: int, *, strength: float, inner: float):
    mask = Image.new("L", (size, size), 0)
    px = mask.load()
    cx = cy = (size - 1) / 2
    max_r = (cx**2 + cy**2) ** 0.5
    for y in range(size):
        for x in range(size):
            r = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / max_r
            if r <= inner:
                value = 0
            else:
                t = (r - inner) / (1.0 - inner)
                value = int(255 * strength * (t * t))
            px[x, y] = value
    return mask.filter(ImageFilter.GaussianBlur(2))


def soft_circle_alpha(Image, ImageChops, ImageDraw, ImageFilter, img, *, feather: int):
    out = img.copy()
    alpha = out.split()[-1]
    ell = Image.new("L", out.size, 0)
    ImageDraw.Draw(ell).ellipse((2, 2, out.size[0] - 3, out.size[1] - 3), fill=255)
    ell = ell.filter(ImageFilter.GaussianBlur(feather))
    out.putalpha(ImageChops.multiply(alpha, ell))
    return out


def compose_b_glow(
    scene_path: Path,
    boss_path: Path,
    *,
    size: int,
    Image,
    ImageChops,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
):
    bg = Image.open(scene_path).convert("RGBA")
    w, h = bg.size
    side = min(w, h)
    x = (w - side) // 2
    y = max(0, int((h - side) / 2 - h * 0.08))
    scene = bg.crop((x, y, x + side, y + side)).resize(
        (size, size), Image.Resampling.LANCZOS
    )
    scene = scene.filter(ImageFilter.GaussianBlur(1.2))
    scene = ImageEnhance.Brightness(scene).enhance(0.48)
    scene = ImageEnhance.Color(scene).enhance(0.75)
    dark = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dark.putalpha(radial_vignette(Image, ImageFilter, size, strength=0.75, inner=0.2))
    scene = Image.alpha_composite(scene, dark)
    scene = Image.alpha_composite(
        scene, Image.new("RGBA", (size, size), (40, 22, 8, 50))
    )

    boss_size = int(size * 0.96)
    boss = Image.open(boss_path).convert("RGBA").resize(
        (boss_size, boss_size), Image.Resampling.LANCZOS
    )
    boss = soft_circle_alpha(
        Image, ImageChops, ImageDraw, ImageFilter, boss, feather=max(8, size // 8)
    )
    alpha = boss.split()[-1].filter(ImageFilter.GaussianBlur(max(4, size // 16)))
    glow = Image.new("RGBA", boss.size, (255, 190, 110, 0))
    glow.putalpha(alpha.point(lambda p: min(255, int(p * 0.45))))
    boss = Image.alpha_composite(glow, boss)

    canvas = scene.copy()
    ox = (size - boss_size) // 2
    oy = (size - boss_size) // 2 - max(1, size // 48)
    canvas.paste(boss, (ox, oy), boss)
    return canvas


def compose_header(scene_path: Path, *, Image) -> object:
    """Wide banner crop from the loading screen for the detail panel."""
    bg = Image.open(scene_path).convert("RGBA")
    w, h = bg.size
    target_ratio = HEADER_WIDTH / HEADER_HEIGHT
    crop_h = int(w / target_ratio)
    if crop_h <= h:
        y = max(0, (h - crop_h) // 3)
        crop = bg.crop((0, y, w, y + crop_h))
    else:
        crop_w = int(h * target_ratio)
        x = max(0, (w - crop_w) // 2)
        crop = bg.crop((x, 0, x + crop_w, h))
    return crop.resize((HEADER_WIDTH, HEADER_HEIGHT), Image.Resampling.LANCZOS)


def catalog_dungeon_ids() -> list[str]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    out: list[str] = []
    seen: set[str] = set()
    for region in catalog.get("regions") or []:
        if not isinstance(region, dict):
            continue
        for entry_id in region.get("dungeons") or []:
            value = str(entry_id)
            if value and value not in seen:
                seen.add(value)
                out.append(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=SIZE)
    args = parser.parse_args()

    Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, texture2ddecoder = (
        _require_deps()
    )
    if not CDB_PATH.is_file():
        raise BuildError(f"missing {CDB_PATH}")
    if not LOADING_DIR.is_dir():
        raise BuildError(f"missing {LOADING_DIR}")

    cdb = json.loads(CDB_PATH.read_text(encoding="utf-8"))
    unit_gfx = load_unit_gfx(cdb)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_HEADER_DIR.mkdir(parents=True, exist_ok=True)

    mapping: dict[str, str] = {}
    headers: dict[str, str] = {}
    missing = 0
    for dungeon_id in catalog_dungeon_ids():
        source = DUNGEON_ICON_SOURCES.get(dungeon_id)
        if not source:
            print(f"MISS mapping {dungeon_id}", file=sys.stderr)
            missing += 1
            continue
        boss_id, screen_name = source
        screen_path = LOADING_DIR / screen_name
        if not screen_path.is_file():
            print(f"MISS screen {dungeon_id} <- {screen_name}", file=sys.stderr)
            missing += 1
            continue
        gfx = unit_gfx.get(boss_id)
        if not gfx:
            print(f"MISS boss gfx {dungeon_id} <- {boss_id}", file=sys.stderr)
            missing += 1
            continue
        boss_path = ensure_boss_portrait(
            boss_id, gfx, Image=Image, texture2ddecoder=texture2ddecoder
        )
        if boss_path is None:
            missing += 1
            continue
        icon = compose_b_glow(
            screen_path,
            boss_path,
            size=args.size,
            Image=Image,
            ImageChops=ImageChops,
            ImageDraw=ImageDraw,
            ImageEnhance=ImageEnhance,
            ImageFilter=ImageFilter,
        )
        out_name = f"{dungeon_id}.webp"
        out_path = OUT_DIR / out_name
        icon.save(out_path, "WEBP", quality=86, method=4)
        mapping[dungeon_id] = f"dungeons/{out_name}"

        header = compose_header(screen_path, Image=Image)
        header_name = f"{dungeon_id}.webp"
        header_path = OUT_HEADER_DIR / header_name
        header.save(header_path, "WEBP", quality=84, method=4)
        headers[dungeon_id] = f"dungeons/headers/{header_name}"
        print(f"OK  {dungeon_id} <- {screen_name} + {boss_id}")

    payload = {
        "schema": 1,
        "size": args.size,
        "style": "b_glow",
        "portraits": mapping,
        "headers": headers,
        "sources": {
            dungeon_id: {"boss": boss, "loading": screen}
            for dungeon_id, (boss, screen) in DUNGEON_ICON_SOURCES.items()
            if dungeon_id in mapping
        },
    }
    OUT_MAP.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(mapping)} icons -> {OUT_MAP} (missing={missing})")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
