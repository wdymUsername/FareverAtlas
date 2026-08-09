"""Lightweight toast notifications for Farever Atlas."""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore, QtGui, QtWidgets


class ToastCard(QtWidgets.QFrame):
    """One ephemeral toast row."""

    dismissed = QtCore.Signal(object)

    # Fixed footprint so action / non-action toasts align in the top stack.
    CARD_WIDTH = 360
    CARD_MIN_HEIGHT = 34

    def __init__(
        self,
        message: str,
        *,
        kind: str = "success",
        duration_ms: int = 2800,
        action_label: str | None = None,
        on_action: Callable[[], None] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toastCard")
        self.setProperty("toastKind", kind)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self._on_action = on_action
        has_action = bool(action_label) and callable(on_action)
        self.setFixedWidth(self.CARD_WIDTH)
        self.setMinimumHeight(self.CARD_MIN_HEIGHT)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 18, 7)
        layout.setSpacing(8)

        label = QtWidgets.QLabel(message)
        label.setObjectName("toastMessage")
        label.setWordWrap(True)
        label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft
        )
        layout.addWidget(label, 1)

        if has_action:
            action = QtWidgets.QToolButton()
            action.setObjectName("toastAction")
            action.setText(str(action_label))
            action.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            action.setFixedHeight(22)
            action.clicked.connect(self._run_action)
            layout.addWidget(action, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        # Corner chip — not a layout column, so it doesn't eat message width.
        close = QtWidgets.QToolButton(self)
        close.setObjectName("toastClose")
        close.setText("×")
        close.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close.setFixedSize(12, 12)
        close.setAutoRaise(True)
        close.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        close.clicked.connect(self._dismiss)
        self._close_button = close

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
        self._position_close_button()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_close_button()

    def _position_close_button(self) -> None:
        close = getattr(self, "_close_button", None)
        if close is None:
            return
        close.move(max(0, self.width() - close.width() - 4), 3)
        close.raise_()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self._dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def _run_action(self) -> None:
        callback = self._on_action
        self._on_action = None
        if callable(callback):
            callback()
        self._dismiss()

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
    """Top-centered toast stack, anchored just under the map's north cardinal."""

    MAX_VISIBLE = 4
    # Radar paints N at viewport.top+7 with height 20; viewport inset is 3px.
    _NORTH_LABEL_BOTTOM = 3 + 7 + 20
    _GAP_BELOW_NORTH = 8

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toastHost")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._stack = QtWidgets.QVBoxLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(4)
        self._stack.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop
        )

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

    def _anchor_top_y(self, parent: QtWidgets.QWidget) -> int:
        """Y just below the painted N cardinal when the map radar is visible."""
        radar = getattr(parent, "radar", None)
        if (
            isinstance(radar, QtWidgets.QWidget)
            and radar.isVisible()
            and radar.height() > 40
        ):
            top_left = radar.mapTo(parent, QtCore.QPoint(0, 0))
            return int(top_left.y() + self._NORTH_LABEL_BOTTOM + self._GAP_BELOW_NORTH)

        title = getattr(parent, "app_title_bar", None)
        title_h = int(title.height()) if isinstance(title, QtWidgets.QWidget) else 32
        context = getattr(parent, "context_stack", None)
        context_h = (
            int(context.height()) if isinstance(context, QtWidgets.QWidget) else 0
        )
        return title_h + context_h + 12

    def _sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is None or not self._cards:
            return
        width = ToastCard.CARD_WIDTH
        # Prefer explicit stack height over sizeHint — newly inserted cards can
        # report a collapsed hint before the layout finishes a pass.
        heights = [
            max(card.sizeHint().height(), ToastCard.CARD_MIN_HEIGHT)
            for card in self._cards
        ]
        height = sum(heights) + self._stack.spacing() * max(0, len(self._cards) - 1)
        x = max(12, (parent.width() - width) // 2)
        y = max(8, self._anchor_top_y(parent))
        # Keep the stack on-screen if the window is short.
        max_y = max(8, parent.height() - height - 8)
        y = min(y, max_y)
        self.setGeometry(x, y, width, height)
        self.raise_()

    def show_message(
        self,
        message: str,
        *,
        kind: str = "success",
        duration_ms: int = 2800,
        action_label: str | None = None,
        on_action: Callable[[], None] | None = None,
        on_dismiss: Callable[[], None] | None = None,
    ) -> None:
        text = str(message).strip()
        if not text:
            return

        while len(self._cards) >= self.MAX_VISIBLE:
            # Evict synchronously. ToastCard._dismiss() only starts a fade and
            # leaves the card in ``_cards`` until the animation finishes — so a
            # naive ``while`` over ``_dismiss()`` spins forever once the oldest
            # card is already closing (common when proximity alerts fire >4
            # toasts in one poll).
            self._evict_card(self._cards[-1])

        card = ToastCard(
            text,
            kind=kind,
            duration_ms=duration_ms,
            action_label=action_label,
            on_action=on_action,
            parent=self,
        )
        card.dismissed.connect(self._remove_card)
        if callable(on_dismiss):
            card.dismissed.connect(lambda _card: on_dismiss())
        # Newest sits nearest the N marker; older toasts push downward.
        self._cards.insert(0, card)
        self._stack.insertWidget(0, card)
        self.show()
        self._sync_geometry()
        self.raise_()

    def _evict_card(self, card: ToastCard) -> None:
        """Drop a card immediately so the stack can accept a new toast."""
        card._timer.stop()
        card._fade.stop()
        try:
            card._fade.finished.disconnect(card._on_fade_finished)
        except (RuntimeError, TypeError):
            pass
        card._closing = True
        # ``dismissed`` runs ``_remove_card`` and any ``on_dismiss`` hooks.
        card.dismissed.emit(card)
        card.deleteLater()

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
    action_label: str | None = None,
    on_action: Callable[[], None] | None = None,
    on_dismiss: Callable[[], None] | None = None,
) -> None:
    """Show a toast on the nearest ancestor that exposes ``show_toast``."""
    if widget is None:
        return
    current: QtWidgets.QWidget | None = widget
    while current is not None:
        show = getattr(current, "show_toast", None)
        if callable(show):
            show(
                message,
                kind=kind,
                duration_ms=duration_ms,
                action_label=action_label,
                on_action=on_action,
                on_dismiss=on_dismiss,
            )
            return
        current = current.parentWidget()
