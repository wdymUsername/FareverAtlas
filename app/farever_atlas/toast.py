"""Lightweight toast notifications for Farever Atlas."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class ToastCard(QtWidgets.QFrame):
    """One ephemeral toast row."""

    dismissed = QtCore.Signal(object)

    def __init__(
        self,
        message: str,
        *,
        kind: str = "success",
        duration_ms: int = 2800,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toastCard")
        self.setProperty("toastKind", kind)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(360)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(8)

        label = QtWidgets.QLabel(message)
        label.setObjectName("toastMessage")
        label.setWordWrap(True)
        layout.addWidget(label, 1)

        close = QtWidgets.QToolButton()
        close.setObjectName("toastClose")
        close.setText("×")
        close.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close.setFixedSize(20, 20)
        close.clicked.connect(self._dismiss)
        layout.addWidget(close, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        self._opacity = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._fade = QtCore.QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(180)
        self._fade.finished.connect(self._on_fade_finished)
        self._closing = False

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)
        self._timer.start(max(800, int(duration_ms)))

        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._closing:
            self.dismissed.emit(self)
            self.deleteLater()


class ToastHost(QtWidgets.QWidget):
    """Bottom-centered toast stack sized only to its cards."""

    MAX_VISIBLE = 4

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toastHost")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._stack = QtWidgets.QVBoxLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(8)

        self._cards: list[ToastCard] = []
        parent.installEventFilter(self)
        self.hide()

    def eventFilter(self, watched: object, event: QtCore.QEvent) -> bool:  # noqa: N802
        if watched is self.parent() and event.type() in {
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Show,
        }:
            self._sync_geometry()
            self.raise_()
        return False

    def _sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is None or not self._cards:
            return
        hint = self.sizeHint()
        width = max(hint.width(), 360)
        height = max(hint.height(), 1)
        x = max(12, (parent.width() - width) // 2)
        y = max(12, parent.height() - height - 18)
        self.setGeometry(x, y, width, height)
        self.raise_()

    def show_message(
        self,
        message: str,
        *,
        kind: str = "success",
        duration_ms: int = 2800,
    ) -> None:
        text = str(message).strip()
        if not text:
            return

        while len(self._cards) >= self.MAX_VISIBLE:
            self._cards[0]._dismiss()

        card = ToastCard(
            text,
            kind=kind,
            duration_ms=duration_ms,
            parent=self,
        )
        card.dismissed.connect(self._remove_card)
        self._cards.append(card)
        self._stack.addWidget(card)
        self.show()
        self._sync_geometry()
        self.raise_()

    def _remove_card(self, card: ToastCard) -> None:
        if card in self._cards:
            self._cards.remove(card)
        self._stack.removeWidget(card)
        if self._cards:
            self._sync_geometry()
        else:
            self.hide()


def notify(
    widget: QtWidgets.QWidget | None,
    message: str,
    *,
    kind: str = "success",
    duration_ms: int = 2800,
) -> None:
    """Show a toast on the nearest ancestor that exposes ``show_toast``."""
    if widget is None:
        return
    current: QtWidgets.QWidget | None = widget
    while current is not None:
        show = getattr(current, "show_toast", None)
        if callable(show):
            show(message, kind=kind, duration_ms=duration_ms)
            return
        current = current.parentWidget()
