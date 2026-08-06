"""Persistent top-level window support."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


def _setting_bool(settings: QtCore.QSettings, key: str, default: bool) -> bool:
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


class PersistentWindow(QtWidgets.QMainWindow):
    def __init__(self, settings: QtCore.QSettings, settings_key: str):
        super().__init__()
        self._settings = settings
        self._settings_key = settings_key
        if _setting_bool(settings, "app/restore_window_positions", True):
            geometry = settings.value(f"windows/{settings_key}/geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if _setting_bool(self._settings, "app/restore_window_positions", True):
            self._settings.setValue(
                f"windows/{self._settings_key}/geometry", self.saveGeometry()
            )
        super().closeEvent(event)
