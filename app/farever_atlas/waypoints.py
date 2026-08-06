"""Custom-waypoint persistence and in-window management overlays."""

from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .config import (
    WAYPOINT_COLORS,
    WAYPOINT_ICONS,
    WAYPOINT_STORE_PATH,
    safe_float,
    safe_int,
)
from .toast import notify


class WaypointStore(QtCore.QObject):
    """Farever Atlas custom waypoint persistence.

    The authoritative JSON file lives at ``user_data/waypoints/``.
    """

    changed = QtCore.Signal()

    def __init__(self, file_path: Path | None = None) -> None:
        super().__init__()
        self.file_path = file_path or WAYPOINT_STORE_PATH
        self.last_error = ""
        self._waypoints: list[dict[str, Any]] = []
        self._load_initial()

    @staticmethod
    def _normalize_waypoint(raw: Any, fallback_id: int) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        x = safe_float(raw.get("x"), math.nan)
        y = safe_float(raw.get("y"), math.nan)
        z = safe_float(raw.get("z"), 0.0)
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            return None
        waypoint_id = safe_int(raw.get("id"), fallback_id)
        if waypoint_id <= 0:
            waypoint_id = fallback_id
        name = str(raw.get("name") or f"Waypoint {waypoint_id}").strip()
        if not name:
            name = f"Waypoint {waypoint_id}"
        color = str(raw.get("color") or "cyan").strip().lower()
        if color not in WAYPOINT_COLORS:
            color = "cyan"
        icon = str(raw.get("icon") or "pin").strip().lower()
        if icon not in WAYPOINT_ICONS:
            icon = "pin"
        return {
            "id": waypoint_id,
            "name": name[:120],
            "x": x,
            "y": y,
            "z": z,
            "color": color,
            "icon": icon,
        }

    @classmethod
    def _load_file(cls, path: Path) -> list[dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_waypoints = payload.get("waypoints", []) if isinstance(payload, dict) else []
        if not isinstance(raw_waypoints, list):
            raise ValueError("Waypoint file must contain a 'waypoints' array")
        normalized: list[dict[str, Any]] = []
        used_ids: set[int] = set()
        next_id = 1
        for raw in raw_waypoints:
            waypoint = cls._normalize_waypoint(raw, next_id)
            if waypoint is None:
                continue
            while waypoint["id"] in used_ids:
                waypoint["id"] += 1
            used_ids.add(waypoint["id"])
            next_id = max(next_id, waypoint["id"] + 1)
            normalized.append(waypoint)
        normalized.sort(key=lambda item: safe_int(item.get("id")))
        return normalized

    def _load_initial(self) -> None:
        if not self.file_path.is_file():
            self._waypoints = []
            self.save(emit=False)
            return
        try:
            self._waypoints = self._load_file(self.file_path)
            self.last_error = ""
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.last_error = str(exc)
            self._waypoints = []

    def all(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._waypoints]

    def get(self, waypoint_id: int) -> dict[str, Any] | None:
        for waypoint in self._waypoints:
            if safe_int(waypoint.get("id")) == waypoint_id:
                return dict(waypoint)
        return None

    def next_id(self) -> int:
        return max((safe_int(item.get("id")) for item in self._waypoints), default=0) + 1

    def save(self, *, emit: bool = True) -> bool:
        payload = {"waypoints": self.all()}
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.file_path.with_name(self.file_path.name + ".tmp")
            backup = self.file_path.with_name(self.file_path.name + ".bak")
            temporary.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            if self.file_path.is_file():
                shutil.copy2(self.file_path, backup)
            os.replace(temporary, self.file_path)
            self.last_error = ""
        except OSError as exc:
            self.last_error = str(exc)
            return False
        if emit:
            self.changed.emit()
        return True

    def add(self, values: dict[str, Any]) -> dict[str, Any] | None:
        candidate = dict(values)
        candidate["id"] = self.next_id()
        waypoint = self._normalize_waypoint(candidate, candidate["id"])
        if waypoint is None:
            return None
        self._waypoints.append(waypoint)
        self._waypoints.sort(key=lambda item: safe_int(item.get("id")))
        if not self.save():
            self._waypoints.remove(waypoint)
            return None
        return dict(waypoint)

    def update_waypoint(self, waypoint_id: int, values: dict[str, Any]) -> bool:
        for index, current in enumerate(self._waypoints):
            if safe_int(current.get("id")) != waypoint_id:
                continue
            candidate = dict(current)
            candidate.update(values)
            candidate["id"] = waypoint_id
            normalized = self._normalize_waypoint(candidate, waypoint_id)
            if normalized is None:
                return False
            old = self._waypoints[index]
            self._waypoints[index] = normalized
            if not self.save():
                self._waypoints[index] = old
                return False
            return True
        return False

    def remove(self, waypoint_id: int) -> bool:
        old = self._waypoints
        self._waypoints = [
            item for item in old if safe_int(item.get("id")) != waypoint_id
        ]
        if len(self._waypoints) == len(old):
            return False
        if not self.save():
            self._waypoints = old
            return False
        return True

    def import_file(self, path: Path, *, merge: bool) -> int:
        incoming = self._load_file(path)
        previous = self.all()
        if not merge:
            self._waypoints = []
        used_ids = {safe_int(item.get("id")) for item in self._waypoints}
        imported = 0
        for raw in incoming:
            waypoint = dict(raw)
            if safe_int(waypoint.get("id")) in used_ids:
                waypoint["id"] = self.next_id()
            used_ids.add(safe_int(waypoint.get("id")))
            self._waypoints.append(waypoint)
            imported += 1
        self._waypoints.sort(key=lambda item: safe_int(item.get("id")))
        if not self.save():
            self._waypoints = previous
            raise OSError(self.last_error or "Failed to save imported waypoints")
        return imported

    def export_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"waypoints": self.all()}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _waypoint_color_icon(color_name: str, size: int = 14) -> QtGui.QIcon:
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    color = QtGui.QColor(WAYPOINT_COLORS.get(color_name, WAYPOINT_COLORS["cyan"]))
    painter.setPen(QtGui.QPen(QtGui.QColor("#18212a"), 1.0))
    painter.setBrush(color)
    painter.drawEllipse(QtCore.QRectF(1.5, 1.5, size - 3.0, size - 3.0))
    painter.end()
    return QtGui.QIcon(pixmap)


def _overlay_title_row(
    title_text: str,
    close_slot: Any,
) -> tuple[QtWidgets.QHBoxLayout, QtWidgets.QLabel, QtWidgets.QToolButton]:
    title_row = QtWidgets.QHBoxLayout()
    title_row.setContentsMargins(2, 0, 0, 0)
    title_row.setSpacing(8)

    title = QtWidgets.QLabel(title_text)
    title.setObjectName("waypointOverlayTitle")
    title_row.addWidget(title)
    title_row.addStretch(1)

    close_button = QtWidgets.QToolButton()
    close_button.setObjectName("waypointOverlayClose")
    close_button.setText("×")
    close_button.setToolTip("Close")
    close_button.setFixedSize(28, 28)
    close_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    close_button.clicked.connect(close_slot)
    title_row.addWidget(close_button)
    return title_row, title, close_button


class WaypointEditOverlay(QtWidgets.QFrame):
    """In-window create/edit form for a custom waypoint."""

    closeRequested = QtCore.Signal()
    saved = QtCore.Signal(dict)

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("waypointEditOverlay")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._waypoint_id: int | None = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        title_row, self._title_label, _close = _overlay_title_row(
            "CUSTOM WAYPOINT", self.closeRequested
        )
        root.addLayout(title_row)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(8)
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setObjectName("waypointOverlayField")
        self.name_edit.setMaxLength(120)
        form.addRow("Name", self.name_edit)

        self.x_spin = self._coordinate_spin()
        self.y_spin = self._coordinate_spin()
        self.z_spin = self._coordinate_spin()
        form.addRow("X", self.x_spin)
        form.addRow("Y", self.y_spin)
        form.addRow("Z", self.z_spin)

        self.color_combo = QtWidgets.QComboBox()
        self.color_combo.setObjectName("waypointOverlayField")
        for color_name in WAYPOINT_COLORS:
            self.color_combo.addItem(
                _waypoint_color_icon(color_name), color_name.title(), color_name
            )
        form.addRow("Color", self.color_combo)

        self.icon_combo = QtWidgets.QComboBox()
        self.icon_combo.setObjectName("waypointOverlayField")
        for icon_name in WAYPOINT_ICONS:
            self.icon_combo.addItem(icon_name.title(), icon_name)
        form.addRow("Marker", self.icon_combo)
        root.addLayout(form)
        root.addStretch(1)

        self._error = QtWidgets.QLabel("")
        self._error.setObjectName("waypointOverlayError")
        self._error.hide()
        root.addWidget(self._error)

        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)

        cancel = QtWidgets.QToolButton()
        cancel.setObjectName("waypointOverlaySecondaryButton")
        cancel.setText("Cancel")
        cancel.setFixedHeight(30)
        cancel.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.closeRequested)
        actions.addWidget(cancel)

        self._save_button = QtWidgets.QToolButton()
        self._save_button.setObjectName("waypointOverlayPrimaryButton")
        self._save_button.setText("Save")
        self._save_button.setFixedHeight(30)
        self._save_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._save_button.clicked.connect(self._save)
        actions.addWidget(self._save_button)
        root.addLayout(actions)

        escape = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self)
        escape.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.closeRequested)

        enter = QtGui.QShortcut(QtGui.QKeySequence("Return"), self)
        enter.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        enter.activated.connect(self._save)

        self.hide()

    @staticmethod
    def _coordinate_spin() -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setObjectName("waypointOverlayField")
        spin.setRange(-1_000_000.0, 1_000_000.0)
        spin.setDecimals(3)
        spin.setSingleStep(1.0)
        return spin

    def open_create(self, defaults: dict[str, Any]) -> None:
        self._waypoint_id = None
        self._title_label.setText("ADD CUSTOM WAYPOINT")
        self._save_button.setText("Create")
        self._load_values(defaults)
        self._show()

    def open_edit(self, waypoint: dict[str, Any]) -> None:
        self._waypoint_id = safe_int(waypoint.get("id"), -1)
        if self._waypoint_id <= 0:
            self._waypoint_id = None
        self._title_label.setText("EDIT CUSTOM WAYPOINT")
        self._save_button.setText("Save")
        self._load_values(waypoint)
        self._show()

    def _load_values(self, values: dict[str, Any]) -> None:
        self._error.hide()
        self.name_edit.setText(str(values.get("name") or ""))
        self.x_spin.setValue(safe_float(values.get("x")))
        self.y_spin.setValue(safe_float(values.get("y")))
        self.z_spin.setValue(safe_float(values.get("z")))
        color_index = self.color_combo.findData(
            str(values.get("color") or "cyan").lower()
        )
        self.color_combo.setCurrentIndex(max(0, color_index))
        icon_index = self.icon_combo.findData(
            str(values.get("icon") or "pin").lower()
        )
        self.icon_combo.setCurrentIndex(max(0, icon_index))
        self.name_edit.selectAll()

    def _show(self) -> None:
        self.show()
        self.raise_()
        self.name_edit.setFocus()

    def values(self) -> dict[str, Any]:
        payload = {
            "name": self.name_edit.text().strip(),
            "x": self.x_spin.value(),
            "y": self.y_spin.value(),
            "z": self.z_spin.value(),
            "color": str(self.color_combo.currentData()),
            "icon": str(self.icon_combo.currentData()),
        }
        if self._waypoint_id is not None:
            payload["id"] = self._waypoint_id
        return payload

    def _save(self) -> None:
        if not self.name_edit.text().strip():
            self._error.setText("A waypoint name is required.")
            self._error.show()
            self.name_edit.setFocus()
            return
        self._error.hide()
        self.saved.emit(self.values())


class WaypointConfirmOverlay(QtWidgets.QFrame):
    """Compact in-window confirmation (delete / import mode)."""

    closeRequested = QtCore.Signal()
    confirmed = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("waypointConfirmOverlay")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._action = ""

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(12)

        title_row, self._title_label, _close = _overlay_title_row(
            "CONFIRM", self.closeRequested
        )
        root.addLayout(title_row)

        self._message = QtWidgets.QLabel("")
        self._message.setObjectName("waypointOverlayBody")
        self._message.setWordWrap(True)
        root.addWidget(self._message)
        root.addStretch(1)

        self._actions = QtWidgets.QHBoxLayout()
        self._actions.setSpacing(8)
        self._actions.addStretch(1)
        root.addLayout(self._actions)

        escape = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self)
        escape.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.closeRequested)
        self.hide()

    def open_delete(self, waypoint_name: str) -> None:
        self._action = "delete"
        self._title_label.setText("DELETE WAYPOINT")
        self._message.setText(f"Delete ‘{waypoint_name}’? This cannot be undone.")
        self._rebuild_actions(
            (
                ("Cancel", "waypointOverlaySecondaryButton", ""),
                ("Delete", "waypointOverlayDangerButton", "delete"),
            )
        )
        self._show()

    def open_import_mode(self) -> None:
        self._action = "import"
        self._title_label.setText("IMPORT WAYPOINTS")
        self._message.setText(
            "Merge imported waypoints with the current list, or replace the list?"
        )
        self._rebuild_actions(
            (
                ("Cancel", "waypointOverlaySecondaryButton", ""),
                ("Replace", "waypointOverlaySecondaryButton", "replace"),
                ("Merge", "waypointOverlayPrimaryButton", "merge"),
            )
        )
        self._show()

    def _rebuild_actions(
        self,
        buttons: tuple[tuple[str, str, str], ...],
    ) -> None:
        while self._actions.count():
            item = self._actions.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._actions.addStretch(1)
        for label, object_name, action in buttons:
            button = QtWidgets.QToolButton()
            button.setObjectName(object_name)
            button.setText(label)
            button.setFixedHeight(30)
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            if action:
                button.clicked.connect(
                    lambda _checked=False, value=action: self.confirmed.emit(value)
                )
            else:
                button.clicked.connect(self.closeRequested)
            self._actions.addWidget(button)

    def _show(self) -> None:
        self.show()
        self.raise_()
        self.setFocus()


class WaypointManagerOverlay(QtWidgets.QFrame):
    """In-window browser for custom waypoints."""

    closeRequested = QtCore.Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        store: WaypointStore,
        current_player: Any,
        add_current_waypoint: Any,
        edit_waypoint: Any,
        delete_waypoint: Any,
        center_waypoint: Any,
        set_active_waypoint: Any,
        active_waypoint_id: Any,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("waypointManagerOverlay")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        self.store = store
        self.current_player = current_player
        self.add_current_waypoint_callback = add_current_waypoint
        self.edit_waypoint_callback = edit_waypoint
        self.delete_waypoint_callback = delete_waypoint
        self.center_waypoint_callback = center_waypoint
        self.set_active_waypoint_callback = set_active_waypoint
        self.active_waypoint_id_callback = active_waypoint_id
        self._pending_delete_id: int | None = None
        self._pending_delete_button: QtWidgets.QToolButton | None = None
        self._pending_import_path: Path | None = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        title_row, _title, _close = _overlay_title_row(
            "CUSTOM WAYPOINTS", self.closeRequested
        )
        root.addLayout(title_row)

        location = QtWidgets.QLabel(str(self.store.file_path))
        location.setObjectName("waypointStoragePath")
        location.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        location.setToolTip("Farever Atlas waypoint storage")
        root.addWidget(location)

        header = QtWidgets.QFrame()
        header.setObjectName("waypointListHeader")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 8, 0)
        header_layout.setSpacing(8)

        for text, stretch, width in (
            ("NAME", 1, None),
            ("DISTANCE", 0, 78),
            ("COLOR", 0, 70),
            ("MARKER", 0, 64),
            ("", 0, 54),
            ("", 0, 62),
        ):
            label = QtWidgets.QLabel(text)
            label.setObjectName("waypointColumnHeader")
            if width is not None:
                label.setFixedWidth(width)
                label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            if stretch:
                header_layout.addWidget(label, stretch)
            else:
                header_layout.addWidget(label)
        root.addWidget(header)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setObjectName("waypointScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._list_widget = QtWidgets.QWidget()
        self._list_widget.setObjectName("waypointList")
        self._list_layout = QtWidgets.QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll, 1)

        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(8)

        self.add_button = QtWidgets.QToolButton()
        self.add_button.setObjectName("waypointOverlayPrimaryButton")
        self.add_button.setText("Add Current")
        self.add_button.setFixedHeight(30)
        self.add_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        self.import_button = QtWidgets.QToolButton()
        self.import_button.setObjectName("waypointOverlaySecondaryButton")
        self.import_button.setText("Import…")
        self.import_button.setFixedHeight(30)
        self.import_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        self.export_button = QtWidgets.QToolButton()
        self.export_button.setObjectName("waypointOverlaySecondaryButton")
        self.export_button.setText("Export…")
        self.export_button.setFixedHeight(30)
        self.export_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        controls.addWidget(self.add_button)
        controls.addStretch(1)
        controls.addWidget(self.import_button)
        controls.addWidget(self.export_button)
        root.addLayout(controls)

        self.add_button.clicked.connect(self._add_current)
        self.import_button.clicked.connect(self._import)
        self.export_button.clicked.connect(self._export)
        self.store.changed.connect(self.refresh)

        escape = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self)
        escape.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.closeRequested)
        self.hide()

    def show_overlay(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.setFocus()

    def _clear_rows(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _reset_pending_delete(self) -> None:
        button = self._pending_delete_button
        if button is not None:
            button.setText("Delete")
            button.setProperty("confirmDelete", False)
            button.style().unpolish(button)
            button.style().polish(button)
        self._pending_delete_id = None
        self._pending_delete_button = None

    def refresh(self) -> None:
        self._reset_pending_delete()
        self._clear_rows()
        player = self.current_player()
        px = (
            safe_float(player.get("x"), math.nan)
            if isinstance(player, dict)
            else math.nan
        )
        py = (
            safe_float(player.get("y"), math.nan)
            if isinstance(player, dict)
            else math.nan
        )
        active_id = self.active_waypoint_id_callback()
        waypoints = self.store.all()

        if not waypoints:
            empty = QtWidgets.QLabel("No custom waypoints yet.")
            empty.setObjectName("waypointEmptyState")
            empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(120)
            self._list_layout.addWidget(empty)
            return

        for waypoint in waypoints:
            self._add_row(waypoint, px, py, active_id)

    def _add_row(
        self,
        waypoint: dict[str, Any],
        px: float,
        py: float,
        active_id: int | None,
    ) -> None:
        waypoint_id = safe_int(waypoint.get("id"), -1)
        name = str(waypoint.get("name") or "Unnamed")
        if waypoint_id == active_id:
            name = f"▶ {name}"

        row = QtWidgets.QFrame()
        row.setObjectName("waypointRow")
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(12, 6, 8, 6)
        layout.setSpacing(8)

        name_label = QtWidgets.QLabel(name)
        name_label.setObjectName("waypointRowName")
        name_label.setToolTip(str(waypoint.get("name") or "Unnamed"))
        layout.addWidget(name_label, 1)

        distance = "—"
        if math.isfinite(px) and math.isfinite(py):
            distance = (
                f"{math.hypot(safe_float(waypoint.get('x')) - px, safe_float(waypoint.get('y')) - py):.1f} m"
            )
        distance_label = QtWidgets.QLabel(distance)
        distance_label.setObjectName("waypointRowMeta")
        distance_label.setFixedWidth(78)
        distance_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(distance_label)

        color_name = str(waypoint.get("color") or "cyan")
        color_label = QtWidgets.QLabel(color_name.title())
        color_label.setObjectName("waypointRowMeta")
        color_label.setFixedWidth(70)
        color_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(color_label)

        marker_label = QtWidgets.QLabel(str(waypoint.get("icon") or "pin").title())
        marker_label.setObjectName("waypointRowMeta")
        marker_label.setFixedWidth(64)
        marker_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(marker_label)

        edit_button = QtWidgets.QToolButton()
        edit_button.setObjectName("waypointRowButton")
        edit_button.setText("Edit")
        edit_button.setFixedSize(54, 28)
        edit_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        edit_button.clicked.connect(
            lambda _checked=False, wid=waypoint_id: self.edit_waypoint_callback(wid)
        )
        layout.addWidget(edit_button)

        delete_button = QtWidgets.QToolButton()
        delete_button.setObjectName("waypointRowDeleteButton")
        delete_button.setText("Delete")
        delete_button.setFixedSize(62, 28)
        delete_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        delete_button.clicked.connect(
            lambda _checked=False, wid=waypoint_id, button=delete_button: (
                self._delete_row(wid, button)
            )
        )
        layout.addWidget(delete_button)

        row.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        row.customContextMenuRequested.connect(
            lambda pos, wid=waypoint_id, widget=row: self._row_menu(wid, widget, pos)
        )
        self._list_layout.addWidget(row)

    def _row_menu(
        self,
        waypoint_id: int,
        widget: QtWidgets.QWidget,
        position: QtCore.QPoint,
    ) -> None:
        menu = QtWidgets.QMenu(self)
        active_id = self.active_waypoint_id_callback()
        if waypoint_id == active_id:
            clear = menu.addAction("Clear Destination")
            clear.triggered.connect(
                lambda _checked=False: self.set_active_waypoint_callback(None)
            )
        else:
            navigate = menu.addAction("Set as Destination")
            navigate.triggered.connect(
                lambda _checked=False, wid=waypoint_id: (
                    self.set_active_waypoint_callback(wid)
                )
            )
        center = menu.addAction("Center on Waypoint")
        center.triggered.connect(
            lambda _checked=False, wid=waypoint_id: self.center_waypoint_callback(wid)
        )
        menu.exec(widget.mapToGlobal(position))

    def _delete_row(
        self,
        waypoint_id: int,
        button: QtWidgets.QToolButton,
    ) -> None:
        if (
            self._pending_delete_id != waypoint_id
            or self._pending_delete_button is not button
        ):
            self._reset_pending_delete()
            self._pending_delete_id = waypoint_id
            self._pending_delete_button = button
            button.setText("Confirm")
            button.setProperty("confirmDelete", True)
            button.style().unpolish(button)
            button.style().polish(button)
            return
        self._reset_pending_delete()
        self.delete_waypoint_callback(waypoint_id, confirmed=True)

    def _add_current(self) -> None:
        self.add_current_waypoint_callback()

    def _import(self) -> None:
        filename, _selected = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import Custom Waypoints",
            str(self.store.file_path.parent),
            "Waypoint JSON (*.json);;All files (*)",
        )
        if not filename:
            return
        self._pending_import_path = Path(filename)
        confirm = getattr(self.parent(), "waypoint_confirm_overlay", None)
        show = getattr(self.parent(), "_set_waypoint_confirm_visible", None)
        if callable(show) and confirm is not None:
            confirm.open_import_mode()
            show(True)
            return
        # Fallback if host wiring is missing.
        self._finish_import("merge")

    def finish_import(self, action: str) -> None:
        self._finish_import(action)

    def _finish_import(self, action: str) -> None:
        path = self._pending_import_path
        self._pending_import_path = None
        if path is None or action not in {"merge", "replace"}:
            return
        try:
            count = self.store.import_file(path, merge=action == "merge")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            notify(self, f"Import failed: {exc}", kind="error")
            return
        notify(self, f"Imported {count} waypoint(s)")

    def _export(self) -> None:
        filename, _selected = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Custom Waypoints",
            str(self.store.file_path.with_name("custom_waypoints_export.json")),
            "Waypoint JSON (*.json)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        try:
            self.store.export_file(path)
        except OSError as exc:
            notify(self, f"Export failed: {exc}", kind="error")
            return
        notify(self, f"Waypoints exported to {path.name}")
