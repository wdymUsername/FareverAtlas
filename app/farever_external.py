#!/usr/bin/env python3
"""Compatibility entry point for Farever Standalone."""

try:
    from farever_standalone.cli import main
except ModuleNotFoundError as exc:
    if exc.name != "PySide6":
        raise
    raise SystemExit(
        "PySide6 is not installed. Run setup.bat on Windows or ./setup.sh "
        "on Linux, then start the matching launcher.\n"
        f"Original error: {exc}"
    ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
