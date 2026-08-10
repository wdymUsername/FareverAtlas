"""Reusable Planner page widgets and overlays."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import (
    ASSET_ROOT,
    CLASS_BLANK_RELATIVE_PATH,
    PLANNER_TALENT_GOLD_RELATIVE_PATH,
    PLANNER_TALENT_SILVER_RELATIVE_PATH,
)
from ...toast import notify


class PlannerClassButton(QtWidgets.QAbstractButton):
    """Fixed-layout class selector button matching the Planner concept."""

    TEXT_RECT = QtCore.QRect(66, 0, 90, 32)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("plannerClassButton")
        self.setFixedSize(178, 32)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._class_name = ""
        self._hovered = False

    def set_class_name(self, class_name: str) -> None:
        self._class_name = class_name
        self.update()

    def display_text(self) -> str:
        return self._class_name if self._class_name else "Select class"

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
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)

        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        background = QtGui.QColor("#10171e")
        border = QtGui.QColor("#344352")
        if self.isDown():
            background = QtGui.QColor("#1d2a35")
            border = QtGui.QColor("#66849a")
        elif self._hovered:
            background = QtGui.QColor("#141e27")
            border = QtGui.QColor("#587083")

        painter.setPen(QtGui.QPen(border, 1.0))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 4.0, 4.0)

        font = painter.font()
        font.setPointSizeF(8.2)
        font.setWeight(QtGui.QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#dce6ee"))
        painter.drawText(
            self.TEXT_RECT,
            QtCore.Qt.AlignmentFlag.AlignCenter,
            self.display_text(),
        )

        # Small built-in arrow; the popup itself contains plain text only.
        arrow_center = QtCore.QPointF(168.0, 16.0)
        arrow = QtGui.QPolygonF(
            (
                QtCore.QPointF(arrow_center.x() - 3.0, arrow_center.y() - 1.5),
                QtCore.QPointF(arrow_center.x() + 3.0, arrow_center.y() - 1.5),
                QtCore.QPointF(arrow_center.x(), arrow_center.y() + 2.0),
            )
        )
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#aebbc6"))
        painter.drawPolygon(arrow)

        if self.hasFocus():
            focus = rect.adjusted(1.5, 1.5, -1.5, -1.5)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor("#5f8cab"), 1.0))
            painter.drawRoundedRect(focus, 3.0, 3.0)


class PlannerClassSelector(QtWidgets.QWidget):
    """Custom class selector with a shared badge overlay and in-page popup."""

    classChanged = QtCore.Signal(str)

    WIDTH = 178
    HEIGHT = 46
    BUTTON_Y = 7
    ICON_SIZE = 56
    ICON_X = 10
    ICON_Y = -5
    POPUP_Y = 39
    ROW_HEIGHT = 32

    def __init__(
        self,
        overlay_parent: QtWidgets.QWidget,
        classes: tuple[tuple[str, str, str], ...],
        initial_class: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("plannerClassSelectorShell")
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._overlay_parent = overlay_parent
        self._classes = classes
        self._current_class = ""
        self._class_labels = {class_id: label for class_id, label, _ in classes}
        self._class_pixmaps: dict[str, QtGui.QPixmap] = {
            "": QtGui.QPixmap(str(ASSET_ROOT / CLASS_BLANK_RELATIVE_PATH))
        }
        for class_id, _label, icon_file in classes:
            self._class_pixmaps[class_id] = QtGui.QPixmap(
                str(ASSET_ROOT / icon_file)
            )

        self.button = PlannerClassButton(self)
        self.button.move(0, self.BUTTON_Y)
        self.button.setToolTip("Build class")
        self.button.clicked.connect(self.toggle_popup)

        # Parent the badge to the Planner page, not to the toolbar. This allows
        # it to overlap the toolbar edge, content area, and popup.
        self.badge = QtWidgets.QLabel(self._overlay_parent)
        self.badge.setObjectName("plannerClassBadge")
        self.badge.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        self.badge.setScaledContents(True)
        self.badge.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        self.popup = QtWidgets.QFrame(self._overlay_parent)
        self.popup.setObjectName("plannerClassPopup")
        self.popup.setFixedWidth(self.WIDTH)
        popup_layout = QtWidgets.QVBoxLayout(self.popup)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout.setSpacing(0)

        self._rows: dict[str, QtWidgets.QToolButton] = {}
        for class_id, label, _icon_file in classes:
            row = QtWidgets.QToolButton(self.popup)
            row.setObjectName("plannerClassPopupRow")
            row.setText(label)
            row.setCheckable(True)
            row.setAutoExclusive(False)
            row.setFixedHeight(self.ROW_HEIGHT)
            row.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            row.clicked.connect(
                lambda _checked=False, selected=class_id: self.set_class(selected)
            )
            popup_layout.addWidget(row)
            self._rows[class_id] = row

        self.popup.setFixedHeight(self.ROW_HEIGHT * len(classes) + 2)
        self.popup.hide()

        self.set_class(initial_class, emit=False)
        QtCore.QTimer.singleShot(0, self._position_overlays)

    def current_class(self) -> str:
        return self._current_class

    def set_class(self, class_id: str, *, emit: bool = True) -> None:
        if class_id not in self._class_labels:
            class_id = ""

        changed = class_id != self._current_class
        self._current_class = class_id
        self.button.set_class_name(self._class_labels.get(class_id, ""))
        self.badge.setPixmap(self._class_pixmaps[class_id])

        for row_class, row in self._rows.items():
            selected = row_class == class_id
            row.setChecked(selected)
            row.setProperty("selected", selected)
            row.style().unpolish(row)
            row.style().polish(row)

        self.hide_popup()
        self._position_overlays()
        if self.isVisible():
            self.badge.show()
            self.badge.raise_()

        if emit and changed:
            self.classChanged.emit(class_id)

    def reset(self) -> None:
        self.set_class("")

    def toggle_popup(self) -> None:
        if self.popup.isVisible():
            self.hide_popup()
        else:
            self.show_popup()

    def show_popup(self) -> None:
        self._position_overlays()
        self.popup.show()
        self.popup.raise_()
        # The badge intentionally sits above both the selector and popup.
        self.badge.show()
        self.badge.raise_()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def hide_popup(self) -> None:
        if not self.popup.isVisible():
            return
        self.popup.hide()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def _position_overlays(self) -> None:
        origin = self._overlay_parent.mapFromGlobal(
            self.mapToGlobal(QtCore.QPoint(0, 0))
        )
        self.badge.move(
            origin.x() + self.ICON_X,
            origin.y() + self.ICON_Y,
        )
        self.popup.move(
            origin.x(),
            origin.y() + self.POPUP_Y,
        )

    def eventFilter(self, watched: object, event: QtCore.QEvent) -> bool:  # noqa: N802
        del watched
        if (
            self.popup.isVisible()
            and event.type() == QtCore.QEvent.Type.MouseButtonPress
        ):
            mouse_event = event
            try:
                global_pos = mouse_event.globalPosition().toPoint()
            except AttributeError:
                global_pos = mouse_event.globalPos()

            button_rect = QtCore.QRect(
                self.button.mapToGlobal(QtCore.QPoint(0, 0)),
                self.button.size(),
            )
            popup_rect = QtCore.QRect(
                self.popup.mapToGlobal(QtCore.QPoint(0, 0)),
                self.popup.size(),
            )
            if not button_rect.contains(global_pos) and not popup_rect.contains(
                global_pos
            ):
                self.hide_popup()
        return False

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:  # noqa: N802
        super().moveEvent(event)
        QtCore.QTimer.singleShot(0, self._position_overlays)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._position_overlays)

    def _restore_badge(self) -> None:
        """Restore the external badge after returning to the Planner page."""
        if not self.isVisible():
            return
        self._position_overlays()
        self.badge.show()
        self.badge.raise_()

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        # The badge is parented outside this widget so it can overflow the
        # toolbar. Hiding the Planner page therefore hides it explicitly, and
        # returning to Planner must explicitly restore it.
        QtCore.QTimer.singleShot(0, self._restore_badge)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:  # noqa: N802
        self.hide_popup()
        self.badge.hide()
        super().hideEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self.hide_popup()
        self.popup.deleteLater()
        self.badge.deleteLater()
        super().closeEvent(event)


class PlannerBuildLoadOverlay(QtWidgets.QFrame):
    """In-window browser for Planner builds stored in user_data/builds."""

    closeRequested = QtCore.Signal()
    buildSelected = QtCore.Signal(object)

    def __init__(
        self,
        builds_dir: Path,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("plannerBuildLoadOverlay")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        self._builds_dir = builds_dir
        self._pending_delete_path: Path | None = None
        self._pending_delete_button: QtWidgets.QToolButton | None = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        title_row = QtWidgets.QHBoxLayout()
        title_row.setContentsMargins(2, 0, 0, 0)
        title_row.setSpacing(8)

        title = QtWidgets.QLabel("SAVED BUILDS")
        title.setObjectName("plannerBuildDialogTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)

        close_button = QtWidgets.QToolButton()
        close_button.setObjectName("plannerBuildDialogClose")
        close_button.setText("×")
        close_button.setToolTip("Close")
        close_button.setFixedSize(28, 28)
        close_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.closeRequested)
        title_row.addWidget(close_button)
        root.addLayout(title_row)

        header = QtWidgets.QFrame()
        header.setObjectName("plannerBuildListHeader")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 8, 0)
        header_layout.setSpacing(8)

        name_header = QtWidgets.QLabel("BUILD NAME")
        class_header = QtWidgets.QLabel("CLASS")
        saved_header = QtWidgets.QLabel("DATE / TIME SAVED")
        load_header = QtWidgets.QLabel("LOAD")
        delete_header = QtWidgets.QLabel("DELETE")

        for label in (
            name_header,
            class_header,
            saved_header,
            load_header,
            delete_header,
        ):
            label.setObjectName("plannerBuildColumnHeader")

        header_layout.addWidget(name_header, 1)

        class_header.setFixedWidth(84)
        class_header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(class_header)

        saved_header.setFixedWidth(150)
        saved_header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(saved_header)

        load_header.setFixedWidth(54)
        load_header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(load_header)

        delete_header.setFixedWidth(62)
        delete_header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(delete_header)
        root.addWidget(header)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setObjectName("plannerBuildScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._list_widget = QtWidgets.QWidget()
        self._list_widget.setObjectName("plannerBuildList")
        self._list_layout = QtWidgets.QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll, 1)

        escape = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self)
        escape.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.closeRequested)

        self.hide()

    def show_overlay(self) -> None:
        self._reload_builds()
        self.show()
        self.raise_()
        self.setFocus()

    def _clear_rows(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _available_builds(
        self,
    ) -> list[tuple[Path, str, str, float]]:
        builds: list[tuple[Path, str, str, float]] = []
        for path in self._builds_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue

                build_name = str(payload.get("name", "")).strip()
                if not build_name:
                    build_name = path.stem

                build_class = str(payload.get("class", "")).strip()
                if not build_class:
                    build_class = "—"

                saved_timestamp = path.stat().st_mtime
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue

            builds.append(
                (path, build_name, build_class, saved_timestamp)
            )

        builds.sort(key=lambda build: build[3], reverse=True)
        return builds

    def _reload_builds(self) -> None:
        self._reset_pending_delete()
        self._clear_rows()
        builds = self._available_builds()

        if not builds:
            empty = QtWidgets.QLabel("No saved builds found.")
            empty.setObjectName("plannerBuildEmptyState")
            empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(150)
            self._list_layout.addWidget(empty)
            return

        for path, build_name, build_class, saved_timestamp in builds:
            self._add_build_row(
                path,
                build_name,
                build_class,
                saved_timestamp,
            )

    def _add_build_row(
        self,
        path: Path,
        build_name: str,
        build_class: str,
        saved_timestamp: float,
    ) -> None:
        row = QtWidgets.QFrame()
        row.setObjectName("plannerBuildRow")
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(12, 6, 8, 6)
        row_layout.setSpacing(8)

        name_label = QtWidgets.QLabel(build_name)
        name_label.setObjectName("plannerBuildRowName")
        name_label.setToolTip(build_name)
        name_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        row_layout.addWidget(name_label, 1)

        class_label = QtWidgets.QLabel(build_class)
        class_label.setObjectName("plannerBuildRowClass")
        class_label.setFixedWidth(84)
        class_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(class_label)

        saved_datetime = QtCore.QDateTime.fromSecsSinceEpoch(
            int(saved_timestamp)
        )
        saved_label = QtWidgets.QLabel(
            saved_datetime.toString("yyyy-MM-dd  HH:mm")
        )
        saved_label.setObjectName("plannerBuildRowDate")
        saved_label.setFixedWidth(150)
        saved_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(saved_label)

        load_button = QtWidgets.QToolButton()
        load_button.setObjectName("plannerBuildLoadButton")
        load_button.setText("Load")
        load_button.setFixedSize(54, 28)
        load_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        load_button.clicked.connect(
            lambda _checked=False, build_path=path:
                self._select_build(build_path)
        )
        row_layout.addWidget(load_button)

        delete_button = QtWidgets.QToolButton()
        delete_button.setObjectName("plannerBuildDeleteButton")
        delete_button.setText("Delete")
        delete_button.setFixedSize(62, 28)
        delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        delete_button.clicked.connect(
            lambda _checked=False, build_path=path, button=delete_button:
                self._delete_build(build_path, button)
        )
        row_layout.addWidget(delete_button)

        self._list_layout.addWidget(row)

    def _reset_pending_delete(self) -> None:
        button = self._pending_delete_button
        if button is not None:
            button.setText("Delete")
            button.setProperty("confirmDelete", False)
            button.style().unpolish(button)
            button.style().polish(button)

        self._pending_delete_path = None
        self._pending_delete_button = None

    def _delete_build(
        self,
        path: Path,
        button: QtWidgets.QToolButton,
    ) -> None:
        # First click arms this row. A second click on the same button performs
        # the deletion without opening an external confirmation dialog.
        if (
            self._pending_delete_path != path
            or self._pending_delete_button is not button
        ):
            self._reset_pending_delete()
            self._pending_delete_path = path
            self._pending_delete_button = button
            button.setText("Confirm")
            button.setProperty("confirmDelete", True)
            button.style().unpolish(button)
            button.style().polish(button)
            return

        build_label = path.stem.replace("_", " ")
        try:
            path.unlink()
        except OSError as error:
            self._reset_pending_delete()
            notify(self, f"Could not delete build: {error}", kind="error")
            return

        self._reset_pending_delete()
        self._reload_builds()
        notify(self, f"Build deleted: {build_label}")

    def _select_build(self, path: Path) -> None:
        self.buildSelected.emit(path)


class PlannerStatRow(QtWidgets.QWidget):
    """Compact Planner stat label/value row."""

    def __init__(
        self,
        label: str,
        value: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("plannerStatRow")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.label = QtWidgets.QLabel(label)
        self.label.setObjectName("plannerStatLabel")
        layout.addWidget(self.label, 1)

        self.value = QtWidgets.QLabel(value)
        self.value.setObjectName("plannerStatValue")
        self.value.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.value.setMinimumWidth(72)
        layout.addWidget(self.value)


class PlannerEquipmentSlot(QtWidgets.QToolButton):
    """Empty equipment slot prepared for later item-selection behavior."""

    def __init__(
        self,
        slot_name: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("plannerEquipmentSlot")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        )
        self.setText(slot_name)
        self.setToolTip(f"{slot_name} slot")
        self.setMinimumSize(118, 64)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )


class PlannerClassSkillSlot(QtWidgets.QToolButton):
    """Compact class-skill slot with a reliable two-line layout."""

    def __init__(
        self,
        index: int,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("plannerClassSkillSlot")
        self.setProperty("skillIndex", index)
        self.setText("")
        self.setToolTip(f"Class skill {index}")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(48)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        content_layout = QtWidgets.QVBoxLayout(self)
        content_layout.setContentsMargins(10, 5, 10, 4)
        content_layout.setSpacing(0)

        self.title_label = QtWidgets.QLabel(f"Skill {index}")
        self.title_label.setObjectName("plannerClassSkillTitle")
        self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.title_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        content_layout.addWidget(self.title_label, 1)

        self.unlock_note = QtWidgets.QLabel()
        self.unlock_note.setObjectName("plannerClassSkillUnlockNote")
        self.unlock_note.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.unlock_note.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.unlock_note.setFixedHeight(14)
        self.unlock_note.hide()
        content_layout.addWidget(self.unlock_note)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.property("locked") is True:
            event.ignore()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if self.property("locked") is True:
            event.ignore()
            return
        super().keyPressEvent(event)


class PlannerTalentChoice(QtWidgets.QWidget):
    """One talent choice with an icon placeholder and rank readout."""

    def __init__(
        self,
        index: int,
        maximum_rank: int,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.index = index
        self.maximum_rank = maximum_rank
        self.setFixedSize(42, 52)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 0)
        layout.setSpacing(1)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.button = QtWidgets.QToolButton()
        self.button.setObjectName("plannerTalentChoice")
        self.button.setProperty("talentIndex", index)
        self.button.setProperty("maximumRank", maximum_rank)
        self.button.setText("")
        self.button.setToolTip(f"Talent {index}")
        self.button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self.button.setFixedSize(28, 28)
        self.button.setIconSize(QtCore.QSize(26, 26))

        asset_root = ASSET_ROOT
        self.button._talent_icon_unranked = QtGui.QIcon(
            str(asset_root / PLANNER_TALENT_SILVER_RELATIVE_PATH)
        )
        self.button._talent_icon_ranked = QtGui.QIcon(
            str(asset_root / PLANNER_TALENT_GOLD_RELATIVE_PATH)
        )
        self.button.setIcon(self.button._talent_icon_unranked)

        layout.addWidget(
            self.button,
            0,
            QtCore.Qt.AlignmentFlag.AlignHCenter,
        )

        self.rank = QtWidgets.QLabel(f"0/{maximum_rank}")
        self.rank.setObjectName("plannerTalentRank")
        self.rank.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.rank.setFixedHeight(14)
        layout.addWidget(self.rank)


class PlannerTalentNode(QtWidgets.QWidget):
    """Visual talent-tree node containing one, two, or three choices."""

    def __init__(
        self,
        choices: tuple[tuple[int, int], ...],
        shape: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.shape = shape
        self.choices: list[PlannerTalentChoice] = [
            PlannerTalentChoice(index, maximum_rank, self)
            for index, maximum_rank in choices
        ]

        if len(self.choices) == 1:
            self.setFixedSize(74, 74)
        elif len(self.choices) == 2:
            self.setFixedSize(108, 78)
        else:
            self.setFixedSize(116, 106)

        self._position_choices()

    def _position_choices(self) -> None:
        if len(self.choices) == 1:
            self.choices[0].move(
                (self.width() - self.choices[0].width()) // 2,
                10,
            )
            return

        if len(self.choices) == 2:
            self.choices[0].move(9, 12)
            self.choices[1].move(self.width() - 51, 12)
            return

        self.choices[0].move(8, 8)
        self.choices[1].move(self.width() - 50, 8)
        self.choices[2].move(
            (self.width() - self.choices[2].width()) // 2,
            50,
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        fill = QtGui.QColor("#121b23")
        border = QtGui.QColor("#405563")
        painter.setBrush(fill)
        painter.setPen(QtGui.QPen(border, 1.4))

        path = QtGui.QPainterPath()
        width = float(self.width())
        height = float(self.height())

        if self.shape == "triangle":
            path.moveTo(8.0, 5.0)
            path.lineTo(width - 8.0, 5.0)
            path.lineTo(width / 2.0, height - 5.0)
            path.closeSubpath()
        else:
            path.moveTo(width / 2.0, 4.0)
            path.lineTo(width - 4.0, height / 2.0)
            path.lineTo(width / 2.0, height - 4.0)
            path.lineTo(4.0, height / 2.0)
            path.closeSubpath()

        painter.drawPath(path)


class PlannerTalentTree(QtWidgets.QWidget):
    """Shared five-tier talent-tree layout used by every class."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("plannerTalentTree")
        self.setMinimumSize(260, 610)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        specifications = (
            ("root", ((1, 1),), "diamond"),
            ("tier2_left", ((2, 1),), "diamond"),
            ("tier2_center", ((3, 1),), "diamond"),
            ("tier2_right", ((4, 1),), "diamond"),
            ("tier3_left", ((5, 2), (6, 2)), "diamond"),
            ("tier3_center", ((7, 2), (8, 2)), "diamond"),
            ("tier3_right", ((9, 2), (10, 2)), "diamond"),
            ("tier4_left", ((11, 1), (12, 2), (13, 2)), "triangle"),
            ("tier4_center", ((14, 1), (15, 2), (16, 2)), "triangle"),
            ("tier4_right", ((17, 1), (18, 2), (19, 2)), "triangle"),
            ("tier5_left", ((20, 1),), "diamond"),
            ("tier5_center", ((21, 1),), "diamond"),
            ("tier5_right", ((22, 1),), "diamond"),
        )

        self.nodes: dict[str, PlannerTalentNode] = {}
        self.talent_buttons: dict[int, QtWidgets.QToolButton] = {}
        self.rank_labels: dict[int, QtWidgets.QLabel] = {}

        for node_id, choices, shape in specifications:
            node = PlannerTalentNode(choices, shape, self)
            self.nodes[node_id] = node
            for choice in node.choices:
                self.talent_buttons[choice.index] = choice.button
                self.rank_labels[choice.index] = choice.rank

        self._position_nodes()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_nodes()

    def _branch_centers(self) -> tuple[int, int, int]:
        margin = 50
        usable = max(120, self.width() - (margin * 2))
        return (
            margin,
            margin + (usable // 2),
            self.width() - margin,
        )

    def _move_centered(
        self,
        node_id: str,
        center_x: int,
        top: int,
    ) -> None:
        node = self.nodes[node_id]
        node.move(center_x - (node.width() // 2), top)

    def _position_nodes(self) -> None:
        left, center, right = self._branch_centers()

        self._move_centered("root", center, 10)

        self._move_centered("tier2_left", left, 116)
        self._move_centered("tier2_center", center, 116)
        self._move_centered("tier2_right", right, 116)

        self._move_centered("tier3_left", left, 228)
        self._move_centered("tier3_center", center, 228)
        self._move_centered("tier3_right", right, 228)

        self._move_centered("tier4_left", left, 348)
        self._move_centered("tier4_center", center, 348)
        self._move_centered("tier4_right", right, 348)

        self._move_centered("tier5_left", left, 516)
        self._move_centered("tier5_center", center, 516)
        self._move_centered("tier5_right", right, 516)

        self.update()

    def _node_top_center(self, node_id: str) -> QtCore.QPointF:
        node = self.nodes[node_id]
        return QtCore.QPointF(
            node.x() + (node.width() / 2.0),
            node.y(),
        )

    def _node_bottom_center(self, node_id: str) -> QtCore.QPointF:
        node = self.nodes[node_id]
        return QtCore.QPointF(
            node.x() + (node.width() / 2.0),
            node.y() + node.height(),
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor("#465b68"), 1.4))

        root_bottom = self._node_bottom_center("root")
        tier2_tops = (
            self._node_top_center("tier2_left"),
            self._node_top_center("tier2_center"),
            self._node_top_center("tier2_right"),
        )
        junction_y = 96.0

        painter.drawLine(
            root_bottom,
            QtCore.QPointF(root_bottom.x(), junction_y),
        )
        painter.drawLine(
            QtCore.QPointF(tier2_tops[0].x(), junction_y),
            QtCore.QPointF(tier2_tops[2].x(), junction_y),
        )
        for top in tier2_tops:
            painter.drawLine(
                QtCore.QPointF(top.x(), junction_y),
                top,
            )

        for branch in ("left", "center", "right"):
            painter.drawLine(
                self._node_bottom_center(f"tier2_{branch}"),
                self._node_top_center(f"tier3_{branch}"),
            )
            painter.drawLine(
                self._node_bottom_center(f"tier3_{branch}"),
                self._node_top_center(f"tier4_{branch}"),
            )
            painter.drawLine(
                self._node_bottom_center(f"tier4_{branch}"),
                self._node_top_center(f"tier5_{branch}"),
            )


