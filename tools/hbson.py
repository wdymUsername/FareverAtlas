"""Reader for Heaps/Hide HBSON prefab containers (`hxd.fmt.hbson`).

Format (verified against Farever world/instance/res.pak prefabs):

  ``HBSON`` | u8 version | one tagged value (the root)

Strings are a little-endian u32 whose top byte is a flag:

  ``0x40``  new string, length in low 24 bits, joins per-file cache
  ``0x80``  new string, length in low 24 bits, not cached
  ``0x00``  entire u32 is an index into that cache

Value tags:

  ``0x00`` zero   ``0x04`` true   ``0x08`` object (u8 field count)
  ``0x01`` i8     ``0x05`` false  ``0x09`` object (u32 field count)
  ``0x02`` i32    ``0x06`` null   ``0x0a`` string
  ``0x03`` f64    ``0x07`` {}     ``0x0b`` []
                  ``0x0c`` array (u8 count)
                  ``0x0d`` array (u32 count)

Object keys are bare strings (no tag); values are tagged.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from typing import Any


class HbsonError(ValueError):
    pass


def read_hbson(buf: bytes) -> dict[str, Any]:
    if len(buf) < 6 or buf[:5] != b"HBSON":
        raise HbsonError("not an HBSON file")
    pos = 5
    version = buf[pos]
    pos += 1
    cache: list[str] = []

    def read_str() -> str:
        nonlocal pos
        (raw,) = struct.unpack_from("<I", buf, pos)
        pos += 4
        flag = raw >> 24
        length = raw & 0xFFFFFF
        if flag == 0x00:
            if raw >= len(cache):
                raise HbsonError(f"string cache miss {raw} at {pos - 4}")
            return cache[raw]
        if flag not in (0x40, 0x80):
            raise HbsonError(f"string flag 0x{flag:02x} at {pos - 4}")
        end = pos + length
        if end > len(buf):
            raise HbsonError(f"string overrun at {pos - 4}")
        text = buf[pos:end].decode("utf-8")
        pos = end
        if flag == 0x40:
            cache.append(text)
        return text

    def read_u32() -> int:
        nonlocal pos
        (value,) = struct.unpack_from("<I", buf, pos)
        pos += 4
        return value

    def read_value() -> Any:
        nonlocal pos
        at = pos
        if pos >= len(buf):
            raise HbsonError(f"truncated value at {at}")
        tag = buf[pos]
        pos += 1
        if tag == 0x00:
            return 0
        if tag == 0x01:
            (value,) = struct.unpack_from("<b", buf, pos)
            pos += 1
            return value
        if tag == 0x02:
            (value,) = struct.unpack_from("<i", buf, pos)
            pos += 4
            return value
        if tag == 0x03:
            (value,) = struct.unpack_from("<d", buf, pos)
            pos += 8
            return value
        if tag == 0x04:
            return True
        if tag == 0x05:
            return False
        if tag == 0x06:
            return None
        if tag == 0x07:
            return {}
        if tag == 0x0A:
            return read_str()
        if tag == 0x0B:
            return []
        if tag in (0x08, 0x09):
            count = buf[pos] if tag == 0x08 else read_u32()
            if tag == 0x08:
                pos += 1
            obj: dict[str, Any] = {}
            for _ in range(count):
                key = read_str()
                obj[key] = read_value()
            return obj
        if tag in (0x0C, 0x0D):
            count = buf[pos] if tag == 0x0C else read_u32()
            if tag == 0x0C:
                pos += 1
            return [read_value() for _ in range(count)]
        ctx = bytes(
            b if 0x20 <= b <= 0x7E else 0x2E
            for b in buf[max(0, at - 24) : at + 24]
        ).decode("latin1")
        raise HbsonError(f"unknown tag 0x{tag:02x} at {at}: {ctx}")

    root = read_value()
    return {"version": version, "root": root, "bytes_read": pos, "size": len(buf)}


def walk_nodes(
    root: Any,
    callback: Callable[[dict[str, Any], float, float, float], None],
) -> None:
    """Walk a prefab node tree with parent-relative x/y/z (+ rotationZ).

    Farever/Heaps applies ``rotationZ`` on the horizontal plane as::

        dx = lx * sin(rot) - ly * cos(rot)
        dy = lx * cos(rot) + ly * sin(rot)

    (equivalently a standard CCW rotation by ``-rot + 90°``). The usual
    ``(lx cos - ly sin, lx sin + ly cos)`` form disagrees with live entity
    positions for nested Orb/Camp chests under rotated activity parents.
    """

    def visit(node: Any, ox: float, oy: float, oz: float, rot: float) -> None:
        if not isinstance(node, dict):
            return
        lx = float(node.get("x") or 0.0)
        ly = float(node.get("y") or 0.0)
        lz = float(node.get("z") or 0.0)
        dx, dy = lx, ly
        if rot:
            angle = math.radians(rot)
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            dx = lx * sin_a - ly * cos_a
            dy = lx * cos_a + ly * sin_a
        x = ox + dx
        y = oy + dy
        z = oz + lz
        callback(node, x, y, z)
        child_rot = rot + float(node.get("rotationZ") or 0.0)
        children = node.get("children") or []
        if isinstance(children, list):
            for child in children:
                visit(child, x, y, z, child_rot)

    children = root.get("children") if isinstance(root, dict) else None
    if isinstance(children, list):
        for child in children:
            visit(child, 0.0, 0.0, 0.0, 0.0)
