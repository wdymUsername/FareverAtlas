"""Reusable custom controls used by the Atlas window."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .config import fmt_hp


class SlideSwitch(QtWidgets.QAbstractButton):
    """Compact animated two-state switch using the Atlas palette."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(34, 18)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Loot marker display mode")

        self._position = 0.0
        self._hovered = False
        self._off_color = QtGui.QColor("#33404b")
        self._on_color = QtGui.QColor("#315d7c")
        self._animation = QtCore.QVariantAnimation(self)
        self._animation.setDuration(135)
        self._animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._animation_value_changed)
        self.toggled.connect(self._animate_to_state)

    def set_track_colors(self, off_color: str, on_color: str) -> None:
        """Set state colors while retaining the standard switch rendering."""
        self._off_color = QtGui.QColor(off_color)
        self._on_color = QtGui.QColor(on_color)
        self.update()

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802
        return QtCore.QSize(34, 18)

    def sync_position(self) -> None:
        """Synchronize the thumb immediately after restoring saved state."""
        self._animation.stop()
        self._position = 1.0 if self.isChecked() else 0.0
        self.update()

    def _animate_to_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def _animation_value_changed(self, value: object) -> None:
        try:
            self._position = float(value)
        except (TypeError, ValueError):
            self._position = 1.0 if self.isChecked() else 0.0
        self.update()

    def enterEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        track = QtCore.QRectF(1.0, 3.0, self.width() - 2.0, self.height() - 6.0)
        radius = track.height() / 2.0

        off_color = QtGui.QColor(self._off_color)
        on_color = QtGui.QColor(self._on_color)
        if self._hovered:
            off_color = off_color.lighter(116)
            on_color = on_color.lighter(116)
        if not self.isEnabled():
            off_color = QtGui.QColor("#29343e")
            on_color = QtGui.QColor("#344e61")

        track_color = QtGui.QColor(
            round(off_color.red() + (on_color.red() - off_color.red()) * self._position),
            round(off_color.green() + (on_color.green() - off_color.green()) * self._position),
            round(off_color.blue() + (on_color.blue() - off_color.blue()) * self._position),
        )
        painter.setPen(QtGui.QPen(QtGui.QColor("#41515e"), 0.8))
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, radius, radius)

        thumb_diameter = 12.0
        thumb_margin = 1.5
        start_x = track.left() + thumb_margin
        end_x = track.right() - thumb_margin - thumb_diameter
        thumb_x = start_x + (end_x - start_x) * self._position
        thumb_y = (self.height() - thumb_diameter) / 2.0
        thumb = QtCore.QRectF(thumb_x, thumb_y, thumb_diameter, thumb_diameter)

        painter.setPen(QtGui.QPen(QtGui.QColor(8, 13, 18, 75), 0.7))
        painter.setBrush(QtGui.QColor("#aeb9c3") if self.isEnabled() else QtGui.QColor("#74818c"))
        painter.drawEllipse(thumb)

        if self.hasFocus():
            focus = track.adjusted(-1.0, -1.0, 1.0, 1.0)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor("#5f8cab"), 0.8))
            painter.drawRoundedRect(focus, radius + 1.0, radius + 1.0)


class PowerStatusButton(QtWidgets.QToolButton):
    """Title-bar power toggle with an inset connection-state indicator."""

    def __init__(
        self,
        icon_path: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(30, 27)
        self.setIcon(QtGui.QIcon(icon_path))
        self.setIconSize(QtCore.QSize(18, 18))
        self._status_color = QtGui.QColor("#77838d")

    def set_status_color(self, color: str) -> None:
        """Set the small status light drawn inside the power glyph."""
        next_color = QtGui.QColor(color)
        if next_color == self._status_color:
            return
        self._status_color = next_color
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # The SVG provides the bold power glyph. The only state decoration is
        # this compact light, inset into the lower centre of the glyph's ring.
        center = QtCore.QPointF(self.width() / 2.0, self.height() / 2.0 + 4.0)
        radius = 3.0
        dot = QtCore.QRectF(
            center.x() - radius,
            center.y() - radius,
            radius * 2.0,
            radius * 2.0,
        )
        painter.setPen(QtGui.QPen(QtGui.QColor("#111820"), 0.9))
        painter.setBrush(self._status_color)
        painter.drawEllipse(dot)


class ShieldOverlayBar(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._hp = 0.0
        self._shield = 0.0
        self._max_hp = 0.0
        self._display_text = "—"
        self._show_maximum = True
        self.setFixedHeight(13)
        self.setMinimumWidth(108)
        self.setMaximumWidth(164)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_values(
        self,
        hp: float,
        shield: float,
        max_hp: float,
        *,
        show_maximum: bool = True,
    ) -> None:
        next_hp = max(0.0, hp)
        next_shield = max(0.0, shield)
        next_max_hp = max(0.0, max_hp)
        if (
            next_hp == self._hp
            and next_shield == self._shield
            and next_max_hp == self._max_hp
            and show_maximum == self._show_maximum
        ):
            return
        self._hp = next_hp
        self._shield = next_shield
        self._max_hp = next_max_hp
        self._show_maximum = show_maximum
        if self._max_hp > 0.0 and not show_maximum:
            self._display_text = (
                f"{fmt_hp(self._hp)} + {fmt_hp(self._shield)}"
                if self._shield > 0.0
                else fmt_hp(self._hp)
            )
        elif self._max_hp > 0.0:
            if self._shield > 0.0:
                self._display_text = (
                    f"{fmt_hp(self._hp)} + {fmt_hp(self._shield)} / "
                    f"{fmt_hp(self._max_hp)}"
                )
            else:
                self._display_text = (
                    f"{fmt_hp(self._hp)} / {fmt_hp(self._max_hp)}"
                )
        else:
            self._display_text = "—"
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)

        rect = self.rect().adjusted(0, 0, -1, -1)
        radius = 3.5
        border = QtGui.QColor('#32404d')
        background = QtGui.QColor('#141b22')
        hp_color = QtGui.QColor('#78b56a')
        shield_color = QtGui.QColor('#5aa8d6')

        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), radius, radius)
        painter.fillPath(path, background)

        if self._max_hp > 1e-6 and rect.width() > 0:
            hp_ratio = max(0.0, min(1.0, self._hp / self._max_hp))
            shield_ratio = max(0.0, min(1.0, min(self._shield, self._hp) / self._max_hp))

            if hp_ratio > 0.0:
                hp_rect = QtCore.QRectF(rect.x(), rect.y(), rect.width() * hp_ratio, rect.height())
                hp_path = QtGui.QPainterPath()
                hp_path.addRoundedRect(hp_rect, radius, radius)
                painter.fillPath(hp_path, hp_color)

            if shield_ratio > 0.0:
                shield_rect = QtCore.QRectF(
                    rect.x(),
                    rect.y(),
                    rect.width() * shield_ratio,
                    rect.height(),
                )
                shield_path = QtGui.QPainterPath()
                shield_path.addRoundedRect(shield_rect, radius, radius)
                painter.fillPath(shield_path, shield_color)

        painter.setPen(QtGui.QPen(border, 1.0))
        painter.drawRoundedRect(QtCore.QRectF(rect), radius, radius)

        text_font = painter.font()
        text_font.setPointSizeF(7.0)
        text_font.setWeight(QtGui.QFont.Weight.DemiBold)
        painter.setFont(text_font)
        # Keep the centered value readable across both bar states. A mostly
        # filled bar places the text over the bright HP/shield colors, while
        # low health places it over the dark empty track.
        hp_ratio = (self._hp / self._max_hp) if self._max_hp > 1e-6 else 0.0
        text_color = QtGui.QColor('#172019') if hp_ratio >= 0.52 else QtGui.QColor('#dbe4eb')
        painter.setPen(text_color)
        painter.drawText(
            rect,
            QtCore.Qt.AlignmentFlag.AlignCenter,
            self._display_text,
        )
        painter.end()


class LootFilterButton(QtWidgets.QPushButton):
    """Loot visibility button with an inset icon/dot mode switch."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("lootModeRow", True)
        self.mode_switch = SlideSwitch(self)
        self.mode_switch.setObjectName("lootModeSwitch")
        self.mode_switch.raise_()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        right_margin = 5
        x = max(0, self.width() - self.mode_switch.width() - right_margin)
        y = max(0, (self.height() - self.mode_switch.height()) // 2)
        self.mode_switch.move(x, y)
        self.mode_switch.raise_()


class FilterChipButton(QtWidgets.QPushButton):
    """Compact checkable filter chip with an optional leading map marker."""

    def __init__(
        self,
        text: str,
        *,
        color: str | None = None,
        colors: list[str] | None = None,
        marker: str = "dot",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarFilterChip")
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._marker = str(marker or "dot").strip().lower()
        palette = [str(item) for item in (colors or []) if str(item).strip()]
        if color:
            palette = [color, *palette]
        self._dot_colors = [QtGui.QColor(item) for item in palette if QtGui.QColor(item).isValid()]
        self._dot_color = self._dot_colors[0] if self._dot_colors else QtGui.QColor()
        self.setProperty("hasDot", bool(self._dot_colors))
        self.setProperty("multiDot", len(self._dot_colors) > 1)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._dot_colors:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        cy = self.height() / 2.0
        if len(self._dot_colors) > 1:
            diameter = 4.5
            start_x = 7.0
            gap = 1.2
            for index, base in enumerate(self._dot_colors[:4]):
                color = QtGui.QColor(base)
                if not self.isEnabled():
                    color.setAlpha(110)
                elif not self.isChecked():
                    color = color.darker(115)
                cx = start_x + index * (diameter + gap) + diameter / 2.0
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(
                    QtCore.QRectF(
                        cx - diameter / 2.0, cy - diameter / 2.0, diameter, diameter
                    )
                )
        else:
            color = QtGui.QColor(self._dot_colors[0])
            if not self.isEnabled():
                color.setAlpha(110)
            elif not self.isChecked():
                color = color.darker(115)
            cx = 11.0
            if self._marker == "diamond":
                size = 3.6
                diamond = QtGui.QPolygonF(
                    [
                        QtCore.QPointF(cx, cy - size),
                        QtCore.QPointF(cx + size, cy),
                        QtCore.QPointF(cx, cy + size),
                        QtCore.QPointF(cx - size, cy),
                    ]
                )
                painter.setPen(QtGui.QPen(QtGui.QColor("#1a1408"), 0.9))
                painter.setBrush(color)
                painter.drawPolygon(diamond)
            else:
                diameter = 6.0
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(
                    QtCore.QRectF(
                        cx - diameter / 2.0, cy - diameter / 2.0, diameter, diameter
                    )
                )
        painter.end()


class SidebarHeaderButton(QtWidgets.QPushButton):
    """Full-width sidebar header with independently aligned title and arrow."""

    def __init__(self, title: str, object_name: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setText("")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(9, 0, 8, 0)
        row.setSpacing(6)

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("sidebarHeaderTitle")
        self.title_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.arrow_label = QtWidgets.QLabel("▴")
        self.arrow_label.setObjectName("sidebarHeaderArrow")
        self.arrow_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.arrow_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        row.addWidget(self.title_label)
        row.addStretch(1)
        row.addWidget(self.arrow_label)

    def set_expanded(self, expanded: bool) -> None:
        self.arrow_label.setText("▴" if expanded else "▾")
