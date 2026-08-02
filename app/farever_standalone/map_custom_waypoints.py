"""Custom waypoint sidebar actions and map context menus."""

from __future__ import annotations

import math
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .config import safe_float, safe_int
from .waypoints import WaypointEditDialog, WaypointManagerDialog


class CustomWaypointMixin:
    """CRUD and visibility for standalone custom waypoints."""

    def _current_player_position(self) -> dict[str, Any] | None:
        state = self.latest_snapshot.state if isinstance(self.latest_snapshot.state, dict) else {}
        player = state.get("player", {}) if isinstance(state, dict) else {}
        if not isinstance(player, dict):
            return None
        x = safe_float(player.get("x"), math.nan)
        y = safe_float(player.get("y"), math.nan)
        z = safe_float(player.get("z"), 0.0)
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return {"x": x, "y": y, "z": z}

    def _default_waypoint_values(self, position: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": f"Waypoint {self.waypoint_store.next_id()}",
            "x": safe_float(position.get("x")),
            "y": safe_float(position.get("y")),
            "z": safe_float(position.get("z")),
            "color": "cyan",
            "icon": "pin",
        }

    def _add_custom_waypoint(self, position: dict[str, Any]) -> None:
        defaults = self._default_waypoint_values(position)
        dialog = WaypointEditDialog(self, None, defaults)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        waypoint = self.waypoint_store.add(dialog.values())
        if waypoint is None:
            QtWidgets.QMessageBox.critical(
                self,
                "Custom Waypoint",
                self.waypoint_store.last_error or "The waypoint could not be saved.",
            )
            return
        waypoint_id = safe_int(waypoint.get("id"), -1)
        if waypoint_id > 0:
            self._settings.setValue(
                f"map/show_custom_waypoint_{waypoint_id}", True
            )
            button = self.custom_waypoint_buttons.get(waypoint_id)
            if button is not None:
                button.setChecked(True)

    def _add_current_custom_waypoint(self, _checked: bool = False) -> None:
        player = self._current_player_position()
        if player is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Custom Waypoint",
                "Current player coordinates are unavailable. Wait for the bridge to connect.",
            )
            return
        self._add_custom_waypoint(player)

    def _edit_custom_waypoint(self, waypoint_id: int) -> None:
        waypoint = self.waypoint_store.get(waypoint_id)
        if waypoint is None:
            return
        dialog = WaypointEditDialog(self, waypoint, waypoint)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        if not self.waypoint_store.update_waypoint(waypoint_id, dialog.values()):
            QtWidgets.QMessageBox.critical(
                self,
                "Custom Waypoint",
                self.waypoint_store.last_error or "The waypoint could not be updated.",
            )

    def _delete_custom_waypoint(self, waypoint_id: int) -> None:
        waypoint = self.waypoint_store.get(waypoint_id)
        if waypoint is None:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Delete Custom Waypoint",
            f"Delete ‘{waypoint.get('name') or 'Unnamed'}’?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        if not self.waypoint_store.remove(waypoint_id):
            QtWidgets.QMessageBox.critical(
                self,
                "Custom Waypoint",
                self.waypoint_store.last_error or "The waypoint could not be deleted.",
            )
            return
        if self.active_custom_waypoint_id == waypoint_id:
            self._set_active_custom_waypoint(None)

    def _center_custom_waypoint(self, waypoint_id: int) -> None:
        waypoint = self.waypoint_store.get(waypoint_id)
        if waypoint is None:
            return
        self.radar.center_on(
            safe_float(waypoint.get("x"), math.nan),
            safe_float(waypoint.get("y"), math.nan),
        )

    def _set_active_custom_waypoint(self, waypoint_id: int | None) -> None:
        if waypoint_id is not None and self.waypoint_store.get(waypoint_id) is None:
            waypoint_id = None
        self.active_custom_waypoint_id = waypoint_id
        self._settings.setValue(
            "map/active_custom_waypoint_id", waypoint_id if waypoint_id is not None else -1
        )
        self._custom_waypoints_changed()

    def _active_custom_waypoint_id(self) -> int | None:
        return self.active_custom_waypoint_id

    def _open_waypoint_manager(self, _checked: bool = False) -> None:
        dialog = WaypointManagerDialog(
            self,
            self.waypoint_store,
            self._current_player_position,
            self._add_current_custom_waypoint,
            self._edit_custom_waypoint,
            self._delete_custom_waypoint,
            self._center_custom_waypoint,
            self._set_active_custom_waypoint,
            self._active_custom_waypoint_id,
        )
        self.waypoint_manager = dialog
        dialog.exec()
        self.waypoint_manager = None

    def _custom_waypoint_visible(self, waypoint_id: int) -> bool:
        button = self.custom_waypoint_buttons.get(waypoint_id)
        if button is not None:
            return button.isChecked()
        return self._setting_bool(f"map/show_custom_waypoint_{waypoint_id}", True)

    def _visible_custom_waypoints(self) -> list[dict[str, Any]]:
        return [
            waypoint
            for waypoint in self.waypoint_store.all()
            if self._custom_waypoint_visible(safe_int(waypoint.get("id"), -1))
        ]

    def _custom_waypoint_visibility_changed(
        self, waypoint_id: int, checked: bool
    ) -> None:
        self._settings.setValue(f"map/show_custom_waypoint_{waypoint_id}", checked)
        self._controls_changed()

    def _show_sidebar_custom_waypoint_menu(
        self, waypoint_id: int, position: QtCore.QPoint
    ) -> None:
        waypoint = self.waypoint_store.get(waypoint_id)
        button = self.custom_waypoint_buttons.get(waypoint_id)
        if waypoint is None or button is None:
            return
        menu = QtWidgets.QMenu(self)
        if self.active_custom_waypoint_id == waypoint_id:
            destination_action = menu.addAction("Clear Destination")
            destination_action.triggered.connect(
                lambda _checked=False: self._set_active_custom_waypoint(None)
            )
        else:
            destination_action = menu.addAction("Set as Destination")
            destination_action.triggered.connect(
                lambda _checked=False, wid=waypoint_id: self._set_active_custom_waypoint(wid)
            )
        center_action = menu.addAction("Center on Waypoint")
        center_action.triggered.connect(
            lambda _checked=False, wid=waypoint_id: self._center_custom_waypoint(wid)
        )
        edit_action = menu.addAction("Edit…")
        edit_action.triggered.connect(
            lambda _checked=False, wid=waypoint_id: self._edit_custom_waypoint(wid)
        )
        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(
            lambda _checked=False, wid=waypoint_id: self._delete_custom_waypoint(wid)
        )
        menu.exec(button.mapToGlobal(position))

    @QtCore.Slot()
    def _custom_waypoints_changed(self) -> None:
        waypoints = self.waypoint_store.all()
        if (
            self.active_custom_waypoint_id is not None
            and self.waypoint_store.get(self.active_custom_waypoint_id) is None
        ):
            self.active_custom_waypoint_id = None
            self._settings.setValue("map/active_custom_waypoint_id", -1)

        live_ids = {safe_int(item.get("id"), -1) for item in waypoints}
        for waypoint_id, button in list(self.custom_waypoint_buttons.items()):
            self.custom_filter_layout.removeWidget(button)
            button.deleteLater()
            if waypoint_id not in live_ids:
                self._settings.remove(f"map/show_custom_waypoint_{waypoint_id}")
        self.custom_waypoint_buttons.clear()

        for index, waypoint in enumerate(waypoints):
            waypoint_id = safe_int(waypoint.get("id"), -1)
            if waypoint_id <= 0:
                continue
            name = str(waypoint.get("name") or f"Waypoint {waypoint_id}")
            button = QtWidgets.QPushButton(name)
            button.setObjectName("sidebarSubItem")
            button.setCheckable(True)
            button.setChecked(
                self._setting_bool(f"map/show_custom_waypoint_{waypoint_id}", True)
            )
            button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            button.setToolTip(
                f"Show or hide {name}\n"
                "Right-click for destination, center, edit, or delete"
            )
            button.setContextMenuPolicy(
                QtCore.Qt.ContextMenuPolicy.CustomContextMenu
            )
            button.toggled.connect(
                lambda checked, wid=waypoint_id: self._custom_waypoint_visibility_changed(
                    wid, checked
                )
            )
            button.customContextMenuRequested.connect(
                lambda pos, wid=waypoint_id: self._show_sidebar_custom_waypoint_menu(
                    wid, pos
                )
            )
            self.custom_filter_layout.insertWidget(index, button)
            self.custom_waypoint_buttons[waypoint_id] = button

        if not self.custom_collapsed:
            self.custom_filter_container.setVisible(True)
            self.custom_filter_container.setMaximumHeight(16777215)
        self.custom_filter_container.updateGeometry()
        self.sidebar_content.updateGeometry()
        self.sidebar.updateGeometry()
        QtCore.QTimer.singleShot(0, self._position_map_overlays)

        self.radar.set_custom_waypoints(
            self._visible_custom_waypoints(),
            visible=True,
            active_id=self.active_custom_waypoint_id,
        )

    @QtCore.Slot(object, object)
    def _show_custom_waypoint_context_menu(
        self,
        world_position: dict[str, Any],
        waypoint: dict[str, Any] | None,
    ) -> None:
        menu = QtWidgets.QMenu(self)
        waypoint_id = safe_int(waypoint.get("id"), -1) if waypoint else -1
        if waypoint is not None and waypoint_id > 0:
            waypoint_name = str(waypoint.get("name") or "Custom Waypoint")
            title = menu.addAction(waypoint_name)
            title.setEnabled(False)
            if self.active_custom_waypoint_id == waypoint_id:
                destination_action = menu.addAction("Clear Destination")
                destination_action.triggered.connect(
                    lambda _checked=False: self._set_active_custom_waypoint(None)
                )
            else:
                destination_action = menu.addAction("Set as Destination")
                destination_action.triggered.connect(
                    lambda _checked=False, wid=waypoint_id: self._set_active_custom_waypoint(wid)
                )
            center_action = menu.addAction("Center on Waypoint")
            center_action.triggered.connect(
                lambda _checked=False, wid=waypoint_id: self._center_custom_waypoint(wid)
            )
            edit_action = menu.addAction("Edit…")
            edit_action.triggered.connect(
                lambda _checked=False, wid=waypoint_id: self._edit_custom_waypoint(wid)
            )
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(
                lambda _checked=False, wid=waypoint_id: self._delete_custom_waypoint(wid)
            )
            menu.addSeparator()
        add_action = menu.addAction("Add Custom Waypoint Here…")
        add_action.triggered.connect(
            lambda _checked=False, position=dict(world_position): (
                self._add_custom_waypoint(position)
            )
        )
        current_action = menu.addAction("Add at Current Position…")
        current_action.setEnabled(self._current_player_position() is not None)
        current_action.triggered.connect(self._add_current_custom_waypoint)
        menu.addSeparator()
        manage_action = menu.addAction("Manage Custom Waypoints…")
        manage_action.triggered.connect(self._open_waypoint_manager)
        menu.exec(QtGui.QCursor.pos())

