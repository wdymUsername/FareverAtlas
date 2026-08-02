"""Reusable map overlay and window chrome widgets."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

class DraggableMapOverlay(QtWidgets.QFrame):
    """Map-bound overlay that can be repositioned with a left-button drag."""

    moved = QtCore.Signal(object)
    SAFE_INSET = 12

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self._drag_offset: QtCore.QPoint | None = None

    @property
    def dragging(self) -> bool:
        return self._drag_offset is not None

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and self.parentWidget() is not None:
            requested = self.mapToParent(event.position().toPoint()) - self._drag_offset
            parent = self.parentWidget()
            min_x = self.SAFE_INSET
            min_y = self.SAFE_INSET
            max_x = max(min_x, parent.width() - self.width() - self.SAFE_INSET)
            max_y = max(min_y, parent.height() - self.height() - self.SAFE_INSET)
            x = max(min_x, min(requested.x(), max_x))
            y = max(min_y, min(requested.y(), max_y))
            self.move(x, y)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            self._drag_offset = None
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            self.moved.emit(self.pos())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class WindowResizeGrip(QtWidgets.QWidget):
    """Invisible edge that starts the platform's native window resize."""

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        edges: QtCore.Qt.Edge,
        cursor: QtCore.Qt.CursorShape,
    ) -> None:
        super().__init__(parent)
        self.edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            window = self.window().windowHandle()
            if window is not None and window.startSystemResize(self.edges):
                event.accept()
                return
        super().mousePressEvent(event)
