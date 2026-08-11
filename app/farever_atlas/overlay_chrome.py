"""Overlay UI chrome: square resize grips and zoom panel styling."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

# Same ladder as the main map; overlay zoom is independent.
OVERLAY_ZOOM_LEVELS = (
    (25, "8x"),
    (50, "4x"),
    (100, "2x"),
    (200, "1x"),
    (300, "0.7x"),
    (450, "0.5x"),
    (650, "0.35x"),
    (900, "0.25x"),
    (1250, "0.2x"),
    (1600, "0.15x"),
    (2000, "0.1x"),
)

ZOOM_PANEL_STYLE = """
QWidget#mapControlsOverlay {
    background: transparent;
}
QWidget#zoomPanel {
    background: rgba(16, 23, 31, 218);
    border: 1px solid #3a4856;
    border-radius: 5px;
}
QFrame#zoomDivider {
    background: #3a4856;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QWidget#mapControlsOverlay QToolButton#zoomButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
    margin: 0;
    color: #8493a2;
    background: transparent;
    border: none;
    border-radius: 0;
}
QWidget#mapControlsOverlay QToolButton#zoomButton:hover {
    background: #263440;
}
QWidget#mapControlsOverlay QToolButton#zoomButton:disabled {
    color: #687582;
    background: transparent;
}
"""


class SquareResizeGrip(QtWidgets.QWidget):
    """Edge/corner grip that resizes the overlay while keeping width == height.

    Native ``startSystemResize`` ignores aspect ratio (KWin will leave a tall
    rectangle), so the overlay drives geometry itself.
    """

    def __init__(
        self,
        window: QtWidgets.QWidget,
        edges: QtCore.Qt.Edge,
        cursor: QtCore.Qt.CursorShape,
    ) -> None:
        super().__init__(window)
        self._host = window
        self.edges = edges
        self.setCursor(cursor)
        self._press_global: QtCore.QPoint | None = None
        self._start_geo: QtCore.QRect | None = None

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._start_geo = QtCore.QRect(self._host.geometry())
            if hasattr(self._host, "_set_follow_drag_active"):
                self._host._set_follow_drag_active(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._press_global is None or self._start_geo is None:
            super().mouseMoveEvent(event)
            return
        delta = event.globalPosition().toPoint() - self._press_global
        start = self._start_geo
        edges = self.edges
        min_side = int(getattr(self._host, "MIN_SIZE", 120))

        proposals: list[int] = []
        if edges & QtCore.Qt.Edge.RightEdge:
            proposals.append(start.width() + delta.x())
        if edges & QtCore.Qt.Edge.LeftEdge:
            proposals.append(start.width() - delta.x())
        if edges & QtCore.Qt.Edge.BottomEdge:
            proposals.append(start.height() + delta.y())
        if edges & QtCore.Qt.Edge.TopEdge:
            proposals.append(start.height() - delta.y())
        if not proposals:
            event.accept()
            return

        side = max(proposals) if len(proposals) > 1 else proposals[0]
        side = max(min_side, int(side))

        x = start.x()
        y = start.y()
        if edges & QtCore.Qt.Edge.LeftEdge:
            x = start.x() + start.width() - side
        if edges & QtCore.Qt.Edge.TopEdge:
            y = start.y() + start.height() - side

        enforcing = getattr(self._host, "_enforcing_square", False)
        self._host._enforcing_square = True  # type: ignore[attr-defined]
        try:
            self._host.setGeometry(x, y, side, side)
        finally:
            self._host._enforcing_square = enforcing  # type: ignore[attr-defined]
        event.accept()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self._press_global is not None
        ):
            self._press_global = None
            self._start_geo = None
            schedule = getattr(self._host, "_schedule_geometry_save", None)
            if callable(schedule):
                schedule()
            if hasattr(self._host, "_set_follow_drag_active"):
                self._host._set_follow_drag_active(False)
            if hasattr(self._host, "_capture_follow_offset_from_geometry"):
                self._host._capture_follow_offset_from_geometry()
            event.accept()
            return
        super().mouseReleaseEvent(event)
