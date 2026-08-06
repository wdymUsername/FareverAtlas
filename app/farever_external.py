#!/usr/bin/env python3
"""Compatibility entry point for Farever Atlas."""

try:
    from farever_atlas.cli import main
except ModuleNotFoundError as exc:
    if exc.name != "PySide6":
        raise
    raise SystemExit(
        "PySide6 is not installed. Run ./farever setup (Linux) or "
        "farever.bat setup (Windows), then start with the matching launcher.\n"
        f"Original error: {exc}"
    ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
