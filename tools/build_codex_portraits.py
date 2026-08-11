#!/usr/bin/env python3
"""Build Codex portrait webps + id map from extracted CDB / DDS art."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CDB_PATH = ROOT / "extracted" / "res.light" / "data.cdb"
EXTRACTED_RES = ROOT / "extracted" / "res"
CATALOG_PATH = ROOT / "assets" / "codex_catalog.json"
OUT_DIR = ROOT / "assets" / "portraits"
OUT_MAP = ROOT / "assets" / "unit_portraits.json"
SIZE = 128


class BuildError(RuntimeError):
    pass


def _require_deps():
    try:
        from PIL import Image
    except ImportError as exc:
        raise BuildError(
            "Pillow required: .venv/bin/pip install -r tools/requirements.txt"
        ) from exc
    try:
        import texture2ddecoder
    except ImportError as exc:
        raise BuildError(
            "texture2ddecoder required: .venv/bin/pip install -r tools/requirements.txt"
        ) from exc
    return Image, texture2ddecoder


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


def collect_targets() -> dict[str, str]:
    """entry_id -> CDB gfx relative path (…/*.png)."""
    cdb = json.loads(CDB_PATH.read_text(encoding="utf-8"))
    sheets = {sheet["name"]: sheet for sheet in cdb["sheets"]}
    units = {line["id"]: line for line in sheets["unit"]["lines"] if line.get("id")}
    items = {line["id"]: line for line in sheets["item"]["lines"] if line.get("id")}
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    wanted: set[str] = set()
    for region in catalog.get("regions") or []:
        if not isinstance(region, dict):
            continue
        for key in ("monsters",):
            for entry_id in region.get(key) or []:
                wanted.add(str(entry_id))
    collection = catalog.get("collection") if isinstance(catalog.get("collection"), dict) else {}
    for key in ("mounts", "gliders", "companions", "appearances"):
        for entry_id in collection.get(key) or []:
            wanted.add(str(entry_id))

    mapping: dict[str, str] = {}
    for entry_id in sorted(wanted):
        candidates = [
            units.get(entry_id),
            items.get(entry_id),
            items.get(f"Critter_{entry_id}"),
            units.get(entry_id.removeprefix("Critter_")),
        ]
        gfx_file = None
        for row in candidates:
            if not row:
                continue
            gfx = row.get("gfx")
            if isinstance(gfx, dict) and gfx.get("file"):
                gfx_file = str(gfx["file"])
                break
        if gfx_file is None:
            guess = f"UI/Portraits/Units/{entry_id.removeprefix('Critter_')}.png"
            if resolve_source(guess) is not None:
                gfx_file = guess
        if gfx_file:
            mapping[entry_id] = gfx_file
    return mapping


def asset_rel_for(gfx_file: str) -> str:
    """UI/Portraits/Units/Foo.png -> units/Foo.webp"""
    rel = Path(gfx_file)
    parts = list(rel.parts)
    # drop UI/Portraits prefix when present
    if len(parts) >= 3 and parts[0] == "UI" and parts[1] == "Portraits":
        parts = parts[2:]
    stem_path = Path(*parts).with_suffix(".webp")
    return stem_path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=SIZE)
    args = parser.parse_args()

    if not CDB_PATH.is_file():
        raise BuildError(f"missing {CDB_PATH}")
    Image, texture2ddecoder = _require_deps()

    targets = collect_targets()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # unique source -> asset rel
    source_to_asset: dict[str, str] = {}
    entry_to_asset: dict[str, str] = {}
    converted = 0
    reused = 0
    missing = 0

    for entry_id, gfx_file in targets.items():
        asset_rel = asset_rel_for(gfx_file)
        entry_to_asset[entry_id] = asset_rel
        if gfx_file in source_to_asset:
            reused += 1
            continue
        source_to_asset[gfx_file] = asset_rel
        source = resolve_source(gfx_file)
        out_path = OUT_DIR / asset_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if source is None:
            missing += 1
            print(f"MISS  {entry_id} <- {gfx_file}", file=sys.stderr)
            entry_to_asset.pop(entry_id, None)
            continue
        if source.suffix.lower() == ".dds":
            image = decode_dds(source, Image, texture2ddecoder)
        else:
            image = Image.open(source).convert("RGBA")
        image = image.resize((args.size, args.size), Image.Resampling.LANCZOS)
        image.save(out_path, "WEBP", quality=82, method=4)
        converted += 1

    # drop entries whose asset failed
    entry_to_asset = {
        key: value
        for key, value in entry_to_asset.items()
        if (OUT_DIR / value).is_file()
    }

    payload = {
        "schema": 1,
        "size": args.size,
        "portraits": entry_to_asset,
    }
    OUT_MAP.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"entries={len(entry_to_asset)} converted={converted} "
        f"unique_sources={len(source_to_asset)} missing={missing} -> {OUT_MAP}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
