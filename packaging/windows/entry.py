"""PyInstaller entry: portable bootstrap, then Atlas UI."""

from __future__ import annotations

import sys


def main() -> int:
    from farever_atlas.portable import bootstrap_frozen, stop_bridge

    bootstrap_frozen()
    try:
        from farever_atlas.cli import main as atlas_main

        return int(atlas_main())
    finally:
        stop_bridge()


if __name__ == "__main__":
    raise SystemExit(main())
