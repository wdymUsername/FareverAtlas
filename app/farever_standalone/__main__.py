"""Run Farever Standalone as a Python module."""

try:
    from .cli import main
except ModuleNotFoundError as exc:
    if exc.name != "PySide6":
        raise
    raise SystemExit(
        "PySide6 is not installed. Run ./setup.sh, then ./run.sh\n"
        f"Original error: {exc}"
    ) from exc

raise SystemExit(main())
