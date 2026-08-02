"""Standalone custom-waypoint persistence and management dialogs."""

from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .config import (
    PROJECT_ROOT,
    WAYPOINT_COLORS,
    WAYPOINT_FILE_NAME,
    WAYPOINT_ICONS,
    discover_legacy_waypoint_files,
    safe_float,
    safe_int,
)


class WaypointStore(QtCore.QObject):
    """Standalone-owned custom waypoint persistence.

    The authoritative JSON file lives below the project root. Farever's native
    waypoint store and overlay are deliberately not used after the optional
    one-time import.
    """

    changed = QtCore.Signal()

    def __init__(self, file_path: Path | None = None) -> None:
        super().__init__()
        self.file_path = file_path or (PROJECT_ROOT / WAYPOINT_FILE_NAME)
        self.migration_source: Path | None = None
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
        source: Path | None = self.file_path if self.file_path.is_file() else None
        if source is None:
            legacy_files = discover_legacy_waypoint_files()
            source = legacy_files[0] if legacy_files else None
            self.migration_source = source
        if source is None:
            self._waypoints = []
            self.save(emit=False)
            return
        try:
            self._waypoints = self._load_file(source)
            self.last_error = ""
            if source != self.file_path:
                self.save(emit=False)
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


class WaypointEditDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        waypoint: dict[str, Any] | None,
        default_position: dict[str, Any],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Custom Waypoint" if waypoint else "Add Custom Waypoint")
        self.setModal(True)
        self.setMinimumWidth(360)
        values = dict(default_position)
        if waypoint:
            values.update(waypoint)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.name_edit = QtWidgets.QLineEdit(str(values.get("name") or ""))
        self.name_edit.setMaxLength(120)
        self.name_edit.selectAll()
        form.addRow("Name", self.name_edit)

        self.x_spin = self._coordinate_spin(safe_float(values.get("x")))
        self.y_spin = self._coordinate_spin(safe_float(values.get("y")))
        self.z_spin = self._coordinate_spin(safe_float(values.get("z")))
        form.addRow("X", self.x_spin)
        form.addRow("Y", self.y_spin)
        form.addRow("Z", self.z_spin)

        self.color_combo = QtWidgets.QComboBox()
        selected_color = str(values.get("color") or "cyan").lower()
        for color_name in WAYPOINT_COLORS:
            self.color_combo.addItem(
                _waypoint_color_icon(color_name), color_name.title(), color_name
            )
        color_index = self.color_combo.findData(selected_color)
        self.color_combo.setCurrentIndex(max(0, color_index))
        form.addRow("Color", self.color_combo)

        self.icon_combo = QtWidgets.QComboBox()
        selected_icon = str(values.get("icon") or "pin").lower()
        for icon_name in WAYPOINT_ICONS:
            self.icon_combo.addItem(icon_name.title(), icon_name)
        icon_index = self.icon_combo.findData(selected_icon)
        self.icon_combo.setCurrentIndex(max(0, icon_index))
        form.addRow("Marker", self.icon_combo)

        layout.addLayout(form)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _coordinate_spin(value: float) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(-1_000_000.0, 1_000_000.0)
        spin.setDecimals(3)
        spin.setSingleStep(1.0)
        spin.setValue(value)
        return spin

    def accept(self) -> None:
        if not self.name_edit.text().strip():
            QtWidgets.QMessageBox.warning(self, "Custom Waypoint", "A waypoint name is required.")
            self.name_edit.setFocus()
            return
        super().accept()

    def values(self) -> dict[str, Any]:
        return {
            "name": self.name_edit.text().strip(),
            "x": self.x_spin.value(),
            "y": self.y_spin.value(),
            "z": self.z_spin.value(),
            "color": str(self.color_combo.currentData()),
            "icon": str(self.icon_combo.currentData()),
        }


class WaypointManagerDialog(QtWidgets.QDialog):
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
        self.store = store
        self.current_player = current_player
        self.add_current_waypoint_callback = add_current_waypoint
        self.edit_waypoint_callback = edit_waypoint
        self.delete_waypoint_callback = delete_waypoint
        self.center_waypoint_callback = center_waypoint
        self.set_active_waypoint_callback = set_active_waypoint
        self.active_waypoint_id_callback = active_waypoint_id
        self.setWindowTitle("Custom Waypoints")
        self.resize(830, 470)
        self.setMinimumSize(660, 360)

        layout = QtWidgets.QVBoxLayout(self)
        location = QtWidgets.QLabel(str(self.store.file_path))
        location.setObjectName("waypointStoragePath")
        location.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        location.setToolTip("Standalone-owned waypoint storage")
        layout.addWidget(location)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Name", "X", "Y", "Z", "Color", "Marker", "Distance"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)

        controls = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("Add Current")
        self.edit_button = QtWidgets.QPushButton("Edit")
        self.delete_button = QtWidgets.QPushButton("Delete")
        self.center_button = QtWidgets.QPushButton("Center")
        self.navigate_button = QtWidgets.QPushButton("Set Destination")
        self.import_button = QtWidgets.QPushButton("Import…")
        self.export_button = QtWidgets.QPushButton("Export…")
        close_button = QtWidgets.QPushButton("Close")
        controls.addWidget(self.add_button)
        controls.addWidget(self.edit_button)
        controls.addWidget(self.delete_button)
        controls.addWidget(self.center_button)
        controls.addWidget(self.navigate_button)
        controls.addStretch(1)
        controls.addWidget(self.import_button)
        controls.addWidget(self.export_button)
        controls.addWidget(close_button)
        layout.addLayout(controls)

        self.add_button.clicked.connect(self._add_current)
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)
        self.center_button.clicked.connect(self._center)
        self.navigate_button.clicked.connect(self._navigate)
        self.import_button.clicked.connect(self._import)
        self.export_button.clicked.connect(self._export)
        close_button.clicked.connect(self.accept)
        self.store.changed.connect(self.refresh)
        self.refresh()

    def _selected_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        if item is None:
            return None
        waypoint_id = safe_int(item.data(QtCore.Qt.ItemDataRole.UserRole), -1)
        return waypoint_id if waypoint_id > 0 else None

    def _selection_changed(self) -> None:
        selected_id = self._selected_id()
        enabled = selected_id is not None
        self.edit_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.center_button.setEnabled(enabled)
        self.navigate_button.setEnabled(enabled)
        active_id = self.active_waypoint_id_callback()
        self.navigate_button.setText(
            "Clear Destination" if enabled and selected_id == active_id else "Set Destination"
        )

    def refresh(self) -> None:
        selected_id = self._selected_id()
        player = self.current_player()
        px = safe_float(player.get("x"), math.nan) if isinstance(player, dict) else math.nan
        py = safe_float(player.get("y"), math.nan) if isinstance(player, dict) else math.nan
        active_id = self.active_waypoint_id_callback()
        waypoints = self.store.all()
        self.table.setRowCount(len(waypoints))
        row_to_select = -1
        for row, waypoint in enumerate(waypoints):
            waypoint_id = safe_int(waypoint.get("id"))
            name = str(waypoint.get("name") or "Unnamed")
            if waypoint_id == active_id:
                name = f"▶ {name}"
            values = [
                name,
                f"{safe_float(waypoint.get('x')):.3f}",
                f"{safe_float(waypoint.get('y')):.3f}",
                f"{safe_float(waypoint.get('z')):.3f}",
                str(waypoint.get("color") or "cyan").title(),
                str(waypoint.get("icon") or "pin").title(),
                "—",
            ]
            if math.isfinite(px) and math.isfinite(py):
                distance = math.hypot(
                    safe_float(waypoint.get("x")) - px,
                    safe_float(waypoint.get("y")) - py,
                )
                values[-1] = f"{distance:.1f} m"
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column == 0:
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, waypoint_id)
                if column in {1, 2, 3, 6}:
                    item.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignRight
                        | QtCore.Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
            if waypoint_id == selected_id:
                row_to_select = row
        self.table.resizeColumnsToContents()
        if row_to_select >= 0:
            self.table.selectRow(row_to_select)
        self._selection_changed()

    def _add_current(self) -> None:
        self.add_current_waypoint_callback()

    def _edit(self, _index: QtCore.QModelIndex | None = None) -> None:
        waypoint_id = self._selected_id()
        if waypoint_id is not None:
            self.edit_waypoint_callback(waypoint_id)

    def _delete(self) -> None:
        waypoint_id = self._selected_id()
        if waypoint_id is not None:
            self.delete_waypoint_callback(waypoint_id)

    def _center(self) -> None:
        waypoint_id = self._selected_id()
        if waypoint_id is not None:
            self.center_waypoint_callback(waypoint_id)

    def _navigate(self) -> None:
        waypoint_id = self._selected_id()
        if waypoint_id is None:
            return
        active_id = self.active_waypoint_id_callback()
        self.set_active_waypoint_callback(None if waypoint_id == active_id else waypoint_id)
        self.refresh()

    def _import(self) -> None:
        filename, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import Custom Waypoints",
            str(self.store.file_path.parent),
            "Waypoint JSON (*.json);;All files (*)",
        )
        if not filename:
            return
        choice = QtWidgets.QMessageBox.question(
            self,
            "Import Custom Waypoints",
            "Merge imported waypoints with the current list?\n\n"
            "Choose No to replace the current list.",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )
        if choice == QtWidgets.QMessageBox.StandardButton.Cancel:
            return
        try:
            count = self.store.import_file(
                Path(filename), merge=choice == QtWidgets.QMessageBox.StandardButton.Yes
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QtWidgets.QMessageBox.critical(self, "Import Custom Waypoints", str(exc))
            return
        QtWidgets.QMessageBox.information(
            self, "Import Custom Waypoints", f"Imported {count} waypoint(s)."
        )

    def _export(self) -> None:
        filename, _selected_filter = QtWidgets.QFileDialog.getSaveFileName(
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
            QtWidgets.QMessageBox.critical(self, "Export Custom Waypoints", str(exc))
