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


def apply_always_on_top(widget: QtWidgets.QWidget, enabled: bool) -> None:
    """Toggle WindowStaysOnTopHint and re-show so WMs (incl. Linux) apply it."""
    enabled = bool(enabled)
    flag = QtCore.Qt.WindowType.WindowStaysOnTopHint
    currently = bool(widget.windowFlags() & flag)
    was_visible = widget.isVisible()
    if currently != enabled:
        widget.setWindowFlag(flag, enabled)
        handle = widget.windowHandle()
        if handle is not None:
            handle.setFlag(flag, enabled)
        if was_visible:
            widget.show()
    if enabled and widget.isVisible():
        widget.raise_()
        widget.activateWindow()


class PersistentWindow(QtWidgets.QMainWindow):
    def __init__(self, settings: QtCore.QSettings, settings_key: str):
        super().__init__()
        self._settings = settings
        self._settings_key = settings_key
        self._geometry_save_timer = QtCore.QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(400)
        self._geometry_save_timer.timeout.connect(self._persist_geometry)
        if _setting_bool(settings, "app/restore_window_positions", True):
            geometry = settings.value(f"windows/{settings_key}/geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)

    def _persist_geometry(self) -> None:
        if not _setting_bool(self._settings, "app/restore_window_positions", True):
            return
        self._settings.setValue(
            f"windows/{self._settings_key}/geometry", self.saveGeometry()
        )

    def _schedule_geometry_save(self) -> None:
        if not _setting_bool(self._settings, "app/restore_window_positions", True):
            return
        self._geometry_save_timer.start()

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:  # noqa: N802
        super().moveEvent(event)
        self._schedule_geometry_save()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._schedule_geometry_save()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._geometry_save_timer.stop()
        self._persist_geometry()
        super().closeEvent(event)
