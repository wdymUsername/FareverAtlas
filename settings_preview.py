#!/usr/bin/env python3
"""Launch the inert Farever settings concept as a standalone window."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PySide6 import QtWidgets  # noqa: E402

from farever_standalone.cli import apply_palette  # noqa: E402
from farever_standalone.settings_window import SettingsWindow  # noqa: E402


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Farever Settings Preview")
    app.setOrganizationName("Local")
    apply_palette(app)

    window = SettingsWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
