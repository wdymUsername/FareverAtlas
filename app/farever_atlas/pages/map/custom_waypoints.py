"""Custom waypoint sidebar actions and map context menus."""

from __future__ import annotations

import math
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import safe_float, safe_int
from ...toast import notify


class CustomWaypointMixin:
    """CRUD and visibility for custom waypoints."""

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
        self._open_waypoint_edit(create_defaults=defaults)

    def _add_current_custom_waypoint(self, _checked: bool = False) -> None:
        player = self._current_player_position()
        if player is None:
            notify(
                self,
                "Player coordinates unavailable — wait for the bridge",
                kind="warning",
            )
            return
        self._add_custom_waypoint(player)

    def _edit_custom_waypoint(self, waypoint_id: int) -> None:
        waypoint = self.waypoint_store.get(waypoint_id)
        if waypoint is None:
            return
        self._open_waypoint_edit(waypoint=waypoint)

    def _open_waypoint_edit(
        self,
        *,
        waypoint: dict[str, Any] | None = None,
        create_defaults: dict[str, Any] | None = None,
    ) -> None:
        overlay = getattr(self, "waypoint_edit_overlay", None)
        if overlay is None:
            return
        if waypoint is not None:
            overlay.open_edit(waypoint)
        elif create_defaults is not None:
            overlay.open_create(create_defaults)
        else:
            return
        self._set_waypoint_edit_visible(True)

    def _on_waypoint_edit_saved(self, values: dict[str, Any]) -> None:
        waypoint_id = safe_int(values.get("id"), -1)
        if waypoint_id > 0:
            if not self.waypoint_store.update_waypoint(waypoint_id, values):
                notify(
                    self,
                    self.waypoint_store.last_error or "Could not update waypoint",
                    kind="error",
                )
                return
            name = str(values.get("name") or "Unnamed")
            self._set_waypoint_edit_visible(False)
            notify(self, f"Waypoint updated: {name}")
            return

        waypoint = self.waypoint_store.add(values)
        if waypoint is None:
            notify(
                self,
                self.waypoint_store.last_error or "Could not save waypoint",
                kind="error",
            )
            return
        new_id = safe_int(waypoint.get("id"), -1)
        if new_id > 0:
            self._settings.setValue(f"map/show_custom_waypoint_{new_id}", True)
            button = self.custom_waypoint_buttons.get(new_id)
            if button is not None:
                button.setChecked(True)
        name = str(waypoint.get("name") or "Unnamed")
        self._set_waypoint_edit_visible(False)
        notify(self, f"Waypoint created: {name}")

    def _delete_custom_waypoint(
        self,
        waypoint_id: int,
        *,
        confirmed: bool = False,
    ) -> None:
        waypoint = self.waypoint_store.get(waypoint_id)
        if waypoint is None:
            return
        name = str(waypoint.get("name") or "Unnamed")
        if not confirmed:
            overlay = getattr(self, "waypoint_confirm_overlay", None)
            if overlay is None:
                return
            overlay.open_delete(name)
            overlay.setProperty("pendingDeleteId", waypoint_id)
            self._set_waypoint_confirm_visible(True)
            return

        if not self.waypoint_store.remove(waypoint_id):
            notify(
                self,
                self.waypoint_store.last_error or "Could not delete waypoint",
                kind="error",
            )
            return
        if self.active_custom_waypoint_id == waypoint_id:
            self._set_active_custom_waypoint(None)
        notify(self, f"Waypoint removed: {name}")

    def _on_waypoint_confirm(self, action: str) -> None:
        overlay = getattr(self, "waypoint_confirm_overlay", None)
        manager = getattr(self, "waypoint_manager_overlay", None)
        self._set_waypoint_confirm_visible(False)
        if overlay is None:
            return

        if action == "delete":
            waypoint_id = safe_int(overlay.property("pendingDeleteId"), -1)
            overlay.setProperty("pendingDeleteId", -1)
            if waypoint_id > 0:
                self._delete_custom_waypoint(waypoint_id, confirmed=True)
            return

        if action in {"merge", "replace"} and manager is not None:
            manager.finish_import(action)

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
            "map/active_custom_waypoint_id",
            waypoint_id if waypoint_id is not None else -1,
        )
        self._custom_waypoints_changed()

    def _active_custom_waypoint_id(self) -> int | None:
        return self.active_custom_waypoint_id

    def _open_waypoint_manager(self, _checked: bool = False) -> None:
        self._set_waypoint_manager_visible(True)

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
                lambda _checked=False, wid=waypoint_id: self._set_active_custom_waypoint(
                    wid
                )
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

        manager = getattr(self, "waypoint_manager_overlay", None)
        if manager is not None and manager.isVisible():
            manager.refresh()

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
                    lambda _checked=False, wid=waypoint_id: (
                        self._set_active_custom_waypoint(wid)
                    )
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
