"""Persistent top-level window support."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class PersistentWindow(QtWidgets.QMainWindow):
    def __init__(self, settings: QtCore.QSettings, settings_key: str):
        super().__init__()
        self._settings = settings
        self._settings_key = settings_key
        geometry = settings.value(f"windows/{settings_key}/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._settings.setValue(
            f"windows/{self._settings_key}/geometry", self.saveGeometry()
        )
        super().closeEvent(event)
