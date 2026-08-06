"""Run Farever Atlas as a Python module."""

try:
    from .cli import main
except ModuleNotFoundError as exc:
    if exc.name != "PySide6":
        raise
    raise SystemExit(
        "PySide6 is not installed. Run ./farever setup, then ./farever start\n"
        f"Original error: {exc}"
    ) from exc

raise SystemExit(main())
