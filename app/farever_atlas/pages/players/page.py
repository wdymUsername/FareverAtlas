"""Players page: instance/layer roster with toolbar filters."""

from __future__ import annotations

import math
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import CLASS_ICON_FILES, discover_project_asset, safe_float, safe_int
from .friends import FRIENDS_CACHE_DIR, FriendStore
from .steam import (
    SteamFriendListCache,
    SteamProfileCache,
    farever_uid_to_steamid64,
    normalize_steamid64,
    open_steam_profile,
    steam_persona_label,
)
from .widgets import PlayerListRow

_PLAYER_CLASS_PIN_ORDER = ("priest", "mage", "warrior", "rogue")


class PlayersPageMixin:
    """Players page construction and live roster updates."""

    def _init_players_page(self) -> None:
        # Context bar (shell-hosted) and body (page stack) are separate so the
        # shell can swap toolbars independently of page content.
        self.players_toolbar = QtWidgets.QWidget()
        self.players_toolbar.setObjectName("playersToolbar")
        self.players_toolbar.setFixedHeight(46)
        toolbar_layout = QtWidgets.QHBoxLayout(self.players_toolbar)
        toolbar_layout.setContentsMargins(7, 0, 7, 0)
        toolbar_layout.setSpacing(7)

        self.players_summary_label = QtWidgets.QLabel("Players")
        self.players_summary_label.setObjectName("playersSummaryLabel")
        self.players_summary_label.setMinimumWidth(120)

        self.players_search = QtWidgets.QLineEdit()
        self.players_search.setObjectName("playersSearchField")
        self.players_search.setPlaceholderText("Search…")
        self.players_search.setClearButtonEnabled(True)
        self.players_search.setFixedHeight(28)
        self.players_search.setMinimumWidth(120)
        self.players_search.setMaximumWidth(180)

        self.players_sort_combo = QtWidgets.QComboBox()
        self.players_sort_combo.setObjectName("playersSortCombo")
        self.players_sort_combo.setFixedHeight(28)
        self.players_sort_combo.setFixedWidth(110)
        self.players_sort_combo.setToolTip("Sort roster")
        self.players_sort_combo.addItem("Distance", "distance")
        self.players_sort_combo.addItem("Name", "name")
        self.players_sort_combo.addItem("Level", "level")
        saved_sort = str(
            self._settings.value("players/sort_mode", "distance") or "distance"
        ).strip().lower()
        sort_index = max(0, self.players_sort_combo.findData(saved_sort))
        self.players_sort_combo.setCurrentIndex(sort_index)

        saved_pin = self._players_load_class_pin()
        self.players_class_pin_buttons: dict[str, QtWidgets.QToolButton] = {}
        self._players_class_pin_updating = False
        for class_id in _PLAYER_CLASS_PIN_ORDER:
            button = QtWidgets.QToolButton()
            button.setObjectName("playersClassPinButton")
            button.setCheckable(True)
            button.setAutoExclusive(False)
            button.setFixedSize(28, 28)
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"Pin {class_id.title()} to top")
            button.setChecked(class_id == saved_pin)
            icon_name = CLASS_ICON_FILES.get(class_id)
            icon_path = discover_project_asset(icon_name) if icon_name else None
            if icon_path is not None:
                pixmap = QtGui.QPixmap(str(icon_path))
                if not pixmap.isNull():
                    button.setIcon(
                        QtGui.QIcon(
                            pixmap.scaled(
                                18,
                                18,
                                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                QtCore.Qt.TransformationMode.SmoothTransformation,
                            )
                        )
                    )
                    button.setIconSize(QtCore.QSize(18, 18))
            else:
                button.setText(class_id[:1].upper())
            self.players_class_pin_buttons[class_id] = button

        self.players_party_only_button = QtWidgets.QToolButton()
        self.players_party_only_button.setObjectName("playersPartyOnlyButton")
        self.players_party_only_button.setText("Party")
        self.players_party_only_button.setCheckable(True)
        self.players_party_only_button.setFixedSize(52, 28)
        self.players_party_only_button.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self.players_party_only_button.setToolTip("Show party members only")
        self.players_party_only_button.setChecked(
            self._setting_bool("players/party_only", False)
        )

        # Order: search | class | filter (sort) | party
        toolbar_layout.addWidget(self.players_summary_label, 0)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.players_search, 0)
        for class_id in _PLAYER_CLASS_PIN_ORDER:
            toolbar_layout.addWidget(self.players_class_pin_buttons[class_id], 0)
        toolbar_layout.addWidget(self.players_sort_combo, 0)
        toolbar_layout.addWidget(self.players_party_only_button, 0)

        self.players_body = QtWidgets.QWidget()
        self.players_body.setObjectName("playersPage")
        body_layout = QtWidgets.QVBoxLayout(self.players_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        columns_host = QtWidgets.QWidget()
        columns_host.setObjectName("playersColumnsHost")
        columns_layout = QtWidgets.QHBoxLayout(columns_host)
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(0)

        self.players_world_column, self.players_scroll, self.players_list_host, self.players_list_layout, self.players_empty_label, self.players_column_title = (
            self._players_make_column("World")
        )
        gutter = QtWidgets.QWidget()
        gutter.setObjectName("playersColumnGutter")
        gutter.setFixedWidth(10)
        gutter.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.players_friends_column, self.friends_scroll, self.friends_list_host, self.friends_list_layout, self.friends_empty_label, self.friends_column_title = (
            self._players_make_column("Friends")
        )
        columns_layout.addWidget(self.players_world_column, 1)
        columns_layout.addWidget(gutter, 0)
        columns_layout.addWidget(self.players_friends_column, 1)
        world_layout = self.players_world_column.layout()
        friends_layout = self.players_friends_column.layout()
        if isinstance(world_layout, QtWidgets.QVBoxLayout):
            world_layout.setContentsMargins(0, 0, 4, 0)
        if isinstance(friends_layout, QtWidgets.QVBoxLayout):
            friends_layout.setContentsMargins(4, 0, 0, 0)
        body_layout.addWidget(columns_host, 1)

        self._players_row_widgets: list[PlayerListRow] = []
        self._friends_row_widgets: list[PlayerListRow] = []
        self._players_roster_signature: tuple[object, ...] | None = None
        self._friends_roster_signature: tuple[object, ...] | None = None
        self._players_selected_key: str | None = None
        self._players_selected_entry: dict[str, Any] | None = None
        self._players_last_state: dict[str, Any] | None = None
        self._players_online = True
        self._players_connected = False
        self._players_layer_by_uid: dict[str, dict[str, Any]] = {}
        self._players_layer_by_name: dict[str, dict[str, Any]] = {}
        self._players_interaction_guard = False
        self._players_last_focus_key: str | None = None

        self._friend_store = FriendStore()
        self._steam_cache = SteamProfileCache(FRIENDS_CACHE_DIR)
        self._steam_friend_list = SteamFriendListCache(FRIENDS_CACHE_DIR)
        self._steam_cache.set_api_key(
            self._settings.value("steam/web_api_key", "") or ""
        )
        self._steam_friend_list.set_api_key(
            self._settings.value("steam/web_api_key", "") or ""
        )
        self._steam_friend_list.set_steamid64(
            self._settings.value("steam/steamid64", "") or ""
        )
        self._steam_cache.updated.connect(
            lambda: self._refresh_players_roster(force=False)
        )
        self._steam_friend_list.updated.connect(
            lambda: self._refresh_players_roster(force=False)
        )
        self._friends_steam_timer = QtCore.QTimer(self.players_body)
        self._friends_steam_timer.setInterval(60_000)
        self._friends_steam_timer.timeout.connect(self._players_request_steam_refresh)
        self._friends_steam_timer.start()

        self.players_search.textChanged.connect(self._players_controls_changed)
        self.players_sort_combo.currentIndexChanged.connect(
            self._players_controls_changed
        )
        for button in self.players_class_pin_buttons.values():
            button.toggled.connect(self._players_class_pin_toggled)
        self.players_party_only_button.toggled.connect(self._players_controls_changed)

    @staticmethod
    def _players_make_column(
        title: str,
    ) -> tuple[
        QtWidgets.QWidget,
        QtWidgets.QScrollArea,
        QtWidgets.QWidget,
        QtWidgets.QVBoxLayout,
        QtWidgets.QLabel,
        QtWidgets.QLabel,
    ]:
        column = QtWidgets.QWidget()
        column.setObjectName("playersColumn")
        layout = QtWidgets.QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QtWidgets.QLabel(title)
        header.setObjectName("playersColumnTitle")
        header.setFixedHeight(28)
        layout.addWidget(header, 0)

        stack_host = QtWidgets.QWidget()
        stack_layout = QtWidgets.QStackedLayout(stack_host)
        stack_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("playersScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        list_host = QtWidgets.QWidget()
        list_host.setObjectName("playersListHost")
        list_layout = QtWidgets.QVBoxLayout(list_host)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(2)
        list_layout.addStretch(1)
        scroll.setWidget(list_host)

        empty = QtWidgets.QLabel("")
        empty.setObjectName("playersPlaceholder")
        empty.setWordWrap(True)
        empty.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        stack_layout.addWidget(scroll)
        stack_layout.addWidget(empty)
        layout.addWidget(stack_host, 1)
        column._players_stack = stack_layout  # type: ignore[attr-defined]
        return column, scroll, list_host, list_layout, empty, header

    def _players_load_class_pin(self) -> str | None:
        raw = self._settings.value("players/class_pin", "")
        if not raw:
            legacy = self._settings.value("players/class_pins", "")
            if isinstance(legacy, (list, tuple)):
                tokens = [str(item) for item in legacy]
            else:
                tokens = str(legacy or "").split(",")
            for token in tokens:
                normalized = token.strip().lower()
                if normalized in _PLAYER_CLASS_PIN_ORDER:
                    return normalized
            return None
        normalized = str(raw).strip().lower()
        return normalized if normalized in _PLAYER_CLASS_PIN_ORDER else None

    def _players_selected_class_pin(self) -> str | None:
        for class_id, button in self.players_class_pin_buttons.items():
            if button.isChecked():
                return class_id
        return None

    def _players_class_pin_toggled(self, checked: bool) -> None:
        if self._players_class_pin_updating:
            return
        sender = self.sender()
        if not isinstance(sender, QtWidgets.QToolButton):
            return
        self._players_class_pin_updating = True
        try:
            if checked:
                for button in self.players_class_pin_buttons.values():
                    if button is not sender and button.isChecked():
                        button.setChecked(False)
        finally:
            self._players_class_pin_updating = False
        self._players_controls_changed()

    def _players_controls_changed(self, *_args: object) -> None:
        sort_mode = str(self.players_sort_combo.currentData() or "distance")
        self._settings.setValue("players/sort_mode", sort_mode)
        self._settings.setValue(
            "players/party_only", self.players_party_only_button.isChecked()
        )
        pin = self._players_selected_class_pin()
        self._settings.setValue("players/class_pin", pin or "")
        self._refresh_players_roster(force=True)

    def _update_players_page(
        self,
        state: dict[str, Any] | None,
        *,
        online: bool,
        connected: bool,
    ) -> None:
        self._players_online = bool(online)
        self._players_connected = bool(connected)
        self._players_last_state = state if isinstance(state, dict) else {}
        key = str(self._settings.value("steam/web_api_key", "") or "").strip()
        self._steam_cache.set_api_key(key)
        self._steam_friend_list.set_api_key(key)
        self._steam_friend_list.set_steamid64(
            self._settings.value("steam/steamid64", "") or ""
        )
        self._refresh_players_roster(force=False)

    def _players_sync_steam_credentials(self) -> None:
        key = str(self._settings.value("steam/web_api_key", "") or "").strip()
        self._steam_cache.set_api_key(key)
        self._steam_friend_list.set_api_key(key)
        self._steam_friend_list.set_steamid64(
            self._settings.value("steam/steamid64", "") or ""
        )

    def _players_request_steam_refresh(self) -> None:
        self._players_sync_steam_credentials()
        if self._steam_cache.has_api_key():
            steamids: list[str] = []
            for friend in self._friend_store.all():
                sid = str(friend.get("steamid64") or "").strip()
                if not sid:
                    decoded = farever_uid_to_steamid64(friend.get("uid"))
                    sid = str(decoded) if decoded is not None else ""
                if sid:
                    steamids.append(sid)
            self._steam_cache.request_refresh(steamids)
        self._steam_friend_list.request_refresh(max_age_s=600)

    def _players_resolve_steamid64(self, entry: dict[str, Any]) -> str:
        sid = normalize_steamid64(entry.get("steamid64"))
        if sid is not None:
            return sid
        decoded = farever_uid_to_steamid64(entry.get("uid"))
        return str(decoded) if decoded is not None else ""

    def _players_is_steam_friend(self, steamid64: object) -> bool:
        return self._steam_friend_list.is_friend(steamid64)

    def _refresh_players_roster(self, *, force: bool) -> None:
        state = self._players_last_state if isinstance(self._players_last_state, dict) else {}
        all_rows = self._build_players_roster_rows(state)
        follow_key = (
            self.radar.follow_target_key()
            if hasattr(self, "radar")
            else None
        )
        last_focus = self._players_last_focus_key
        for row in all_rows:
            uid = str(row.get("uid") or "").strip()
            friend_key = str(row.get("friend_key") or uid).strip()
            row["is_friend"] = self._friend_store.contains_player(row)
            steamid64 = self._players_resolve_steamid64(row)
            if steamid64:
                row["steamid64"] = steamid64
            row["is_steam_friend"] = self._players_is_steam_friend(steamid64)
            row_key = uid or friend_key
            row["is_followed"] = bool(follow_key and row_key == follow_key)
            row["focus_armed"] = bool(
                last_focus
                and row_key == last_focus
                and not row["is_followed"]
            )
            if row["is_friend"] and not row.get("is_self"):
                self._friend_store.update_seen(row)
        # Recompute after possible name→uid friend upgrades in update_seen.
        for row in all_rows:
            row["is_friend"] = self._friend_store.contains_player(row)
            steamid64 = self._players_resolve_steamid64(row)
            if steamid64:
                row["steamid64"] = steamid64
            row["is_steam_friend"] = self._players_is_steam_friend(steamid64)
        rows = self._filter_sort_players_rows(all_rows)
        self._players_layer_by_uid = {
            str(row.get("uid") or ""): row
            for row in all_rows
            if str(row.get("uid") or "").strip()
        }
        self._players_layer_by_name = {
            str(row.get("name") or "").strip().lower(): row
            for row in all_rows
            if str(row.get("name") or "").strip()
        }

        instance = state.get("instance", {}) if isinstance(state, dict) else {}
        if not isinstance(instance, dict):
            instance = {}
        instance_label = self._players_instance_label(instance)
        total_count = len(all_rows)
        class_pin = self._players_selected_class_pin()
        if not self._players_online:
            summary = "Offline"
            empty_text = "Offline — enable online mode to list players"
        elif not self._players_connected:
            summary = f"{instance_label} · waiting"
            empty_text = "Waiting for live player data"
        else:
            summary = f"{instance_label} · {total_count} player" + (
                "s" if total_count != 1 else ""
            )
            if self.players_party_only_button.isChecked():
                empty_text = "No party members"
            elif self.players_search.text().strip():
                empty_text = "No matching players"
            else:
                empty_text = "No players on this layer"
        self.players_summary_label.setText(summary)
        self.players_summary_label.setToolTip(summary)
        self.players_column_title.setText(f"World · {len(rows)}")

        friend_rows = self._build_friends_rows()
        here_count = sum(1 for row in friend_rows if row.get("presence") == "here")
        self.friends_column_title.setText(
            f"Friends · {len(friend_rows)}"
            + (f" · {here_count} here" if friend_rows else "")
        )
        if self._steam_cache.has_api_key():
            friends_empty = "No friends yet — ★ a player on the left"
        else:
            friends_empty = (
                "No friends yet — ★ a player on the left.\n"
                "Settings → Steam Web API key caches avatars/status.\n"
                "Private Steam profiles are labeled Private (not Offline)."
            )

        world_sig = (
            self._players_online,
            self._players_connected,
            summary,
            empty_text,
            self.players_search.text().strip().lower(),
            str(self.players_sort_combo.currentData() or "distance"),
            self.players_party_only_button.isChecked(),
            class_pin or "",
            tuple(
                (
                    str(row.get("key") or ""),
                    str(row.get("name") or ""),
                    str(row.get("class") or ""),
                    safe_int(row.get("level"), 0),
                    safe_int(row.get("party_slot"), -1),
                    (
                        round(safe_float(row.get("distance"), math.nan))
                        if math.isfinite(safe_float(row.get("distance"), math.nan))
                        else None
                    ),
                    bool(row.get("is_self")),
                    bool(row.get("in_party")),
                    bool(row.get("is_friend")),
                    bool(row.get("is_steam_friend")),
                    bool(row.get("is_followed")),
                    bool(row.get("focus_armed")),
                    str(row.get("uid") or ""),
                )
                for row in rows
            ),
        )
        friends_sig = tuple(
            (
                str(row.get("key") or ""),
                str(row.get("name") or ""),
                str(row.get("class") or ""),
                safe_int(row.get("level"), 0),
                str(row.get("presence") or ""),
                str(row.get("steam_label") or ""),
                str(row.get("steamid64") or ""),
                bool(row.get("is_steam_friend")),
                bool(row.get("steam_avatar")),
                safe_int(
                    (row.get("steam_summary") or {}).get("fetched_at")
                    if isinstance(row.get("steam_summary"), dict)
                    else 0,
                    0,
                ),
                bool(row.get("is_followed")),
                bool(row.get("focus_armed")),
                (
                    round(safe_float(row.get("distance"), math.nan))
                    if math.isfinite(safe_float(row.get("distance"), math.nan))
                    else None
                ),
                str(row.get("uid") or ""),
            )
            for row in friend_rows
        )
        if (
            not force
            and world_sig == self._players_roster_signature
            and friends_sig == self._friends_roster_signature
        ):
            return
        # Don't reorder rows while the user is mid-click on a row action;
        # retry shortly after the mouse is released.
        if self._players_interaction_active() and not force:
            self._players_interaction_guard = True
            if not hasattr(self, "_players_interaction_timer"):
                self._players_interaction_timer = QtCore.QTimer(self.players_body)
                self._players_interaction_timer.setSingleShot(True)
                self._players_interaction_timer.timeout.connect(
                    self._players_flush_interaction_guard
                )
            self._players_interaction_timer.start(50)
            return
        self._players_interaction_guard = False
        self._players_roster_signature = world_sig
        self._friends_roster_signature = friends_sig

        self._players_render_column(
            rows=rows,
            widgets_attr="_players_row_widgets",
            list_layout=self.players_list_layout,
            list_host=self.players_list_host,
            scroll=self.players_scroll,
            empty=self.players_empty_label,
            empty_text=empty_text,
            show_list=bool(rows) and self._players_online,
            column_widget=self.players_world_column,
        )
        self._players_render_column(
            rows=friend_rows,
            widgets_attr="_friends_row_widgets",
            list_layout=self.friends_list_layout,
            list_host=self.friends_list_host,
            scroll=self.friends_scroll,
            empty=self.friends_empty_label,
            empty_text=friends_empty if not friend_rows else "",
            show_list=bool(friend_rows),
            column_widget=self.players_friends_column,
        )
        self._players_request_steam_refresh()

    def _players_flush_interaction_guard(self) -> None:
        if self._players_interaction_active():
            if hasattr(self, "_players_interaction_timer"):
                self._players_interaction_timer.start(50)
            return
        if self._players_interaction_guard:
            self._players_interaction_guard = False
            self._refresh_players_roster(force=False)

    def _players_interaction_active(self) -> bool:
        """True while a row action button is pressed / under the mouse grab."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return False
        mouse = QtWidgets.QApplication.mouseButtons()
        if mouse == QtCore.Qt.MouseButton.NoButton:
            return False
        widget = app.widgetAt(QtGui.QCursor.pos())
        if widget is None:
            return False
        for row in self._players_row_widgets + self._friends_row_widgets:
            if row.isAncestorOf(widget) or widget is row:
                return True
        return False

    def _players_render_column(
        self,
        *,
        rows: list[dict[str, Any]],
        widgets_attr: str,
        list_layout: QtWidgets.QVBoxLayout,
        list_host: QtWidgets.QWidget,
        scroll: QtWidgets.QScrollArea,
        empty: QtWidgets.QLabel,
        empty_text: str,
        show_list: bool,
        column_widget: QtWidgets.QWidget,
    ) -> None:
        """Sync column rows in place — reuse widgets by key so clicks survive updates."""
        widgets: list[PlayerListRow] = getattr(self, widgets_attr)
        stack = getattr(column_widget, "_players_stack", None)
        if isinstance(stack, QtWidgets.QStackedLayout):
            stack.setCurrentWidget(scroll if show_list else empty)
        empty.setText(empty_text)

        desired_keys = [str(entry.get("key") or "") for entry in rows]
        current_keys = [str(widget.entry().get("key") or "") for widget in widgets]

        # Fast path: same membership and order — update labels only, keep widgets.
        if desired_keys == current_keys and len(rows) == len(widgets):
            selected_key = self._players_selected_key
            restored_entry: dict[str, Any] | None = None
            for entry, row in zip(rows, widgets, strict=True):
                row.set_entry(entry)
                key = str(entry.get("key") or "")
                is_selected = bool(selected_key and key == selected_key)
                row.set_selected(is_selected)
                if is_selected:
                    restored_entry = entry
            if restored_entry is not None:
                self._players_selected_entry = restored_entry
            elif selected_key and selected_key not in desired_keys:
                self._players_selected_key = None
                self._players_selected_entry = None
            return

        by_key: dict[str, PlayerListRow] = {}
        for widget in widgets:
            key = str(widget.entry().get("key") or "")
            if key and key not in by_key:
                by_key[key] = widget

        # Detach existing rows without destroying them so we can reorder safely.
        for widget in widgets:
            list_layout.removeWidget(widget)
            widget.setParent(list_host)

        selected_key = self._players_selected_key
        restored_entry = None
        new_widgets: list[PlayerListRow] = []
        used_keys: set[str] = set()

        for entry in rows:
            key = str(entry.get("key") or "")
            row = by_key.get(key) if key else None
            if row is None:
                row = PlayerListRow(list_host)
                row.selected.connect(self._players_row_selected)
                row.activated.connect(self._players_row_activated)
                row.profileRequested.connect(self._players_open_steam_profile)
                row.focusRequested.connect(self._players_focus_entry)
                row.friendToggleRequested.connect(self._players_toggle_friend)
            row.set_entry(entry)
            is_selected = bool(selected_key and key == selected_key)
            row.set_selected(is_selected)
            if is_selected:
                restored_entry = entry
            insert_at = max(0, list_layout.count() - 1)
            list_layout.insertWidget(insert_at, row)
            row.show()
            new_widgets.append(row)
            if key:
                used_keys.add(key)

        for key, widget in by_key.items():
            if key in used_keys:
                continue
            widget.hide()
            widget.deleteLater()

        setattr(self, widgets_attr, new_widgets)

        if restored_entry is not None:
            self._players_selected_entry = restored_entry
        elif selected_key and not any(
            str(row.entry().get("key") or "") == selected_key
            for row in self._players_row_widgets + self._friends_row_widgets
        ):
            self._players_selected_key = None
            self._players_selected_entry = None

    def _build_friends_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for friend in self._friend_store.all():
            uid = str(friend.get("uid") or "").strip()
            if not uid:
                continue
            name = str(friend.get("name") or "Unknown")
            # Friends column ignores the World search box so adds always appear.
            live = self._players_layer_by_uid.get(uid)
            if live is None:
                want = ""
                if uid.startswith("name:"):
                    want = uid[5:].lower()
                elif name:
                    want = name.lower()
                if want:
                    live = self._players_layer_by_name.get(want)
            presence = "here" if live is not None else "away"
            steamid64 = str(friend.get("steamid64") or "").strip()
            if not steamid64:
                decoded = farever_uid_to_steamid64(uid)
                steamid64 = str(decoded) if decoded is not None else ""
            summary = self._steam_cache.summary(steamid64) if steamid64 else None
            steam_label, _tip = steam_persona_label(summary)
            avatar = (
                self._steam_cache.avatar_pixmap(steamid64, 24)
                if steamid64
                else QtGui.QPixmap()
            )
            entry: dict[str, Any] = {
                "key": f"friend:{uid}",
                "uid": uid,
                "steamid64": steamid64,
                "name": str(live.get("name") or name) if live else name,
                "class": (
                    str(live.get("class") or friend.get("class") or "")
                    if live
                    else str(friend.get("class") or "")
                ),
                "level": (
                    safe_int(live.get("level"), safe_int(friend.get("level"), 0))
                    if live
                    else safe_int(friend.get("level"), 0)
                ),
                "x": live.get("x") if live else None,
                "y": live.get("y") if live else None,
                "z": live.get("z") if live else None,
                "distance": live.get("distance") if live else math.nan,
                "is_self": False,
                "in_party": bool(live.get("in_party")) if live else False,
                "is_friend": True,
                "is_steam_friend": self._players_is_steam_friend(steamid64),
                "list_kind": "friend",
                "presence": presence,
                "steam_summary": summary,
                "steam_label": steam_label,
                "steam_avatar": avatar if not avatar.isNull() else None,
            }
            follow_key = (
                self.radar.follow_target_key()
                if hasattr(self, "radar")
                else None
            )
            row_key = uid
            entry["is_followed"] = bool(follow_key and row_key == follow_key)
            entry["focus_armed"] = bool(
                self._players_last_focus_key
                and row_key == self._players_last_focus_key
                and not entry["is_followed"]
            )
            rows.append(entry)

        rows.sort(
            key=lambda row: (
                0 if row.get("presence") == "here" else 1,
                str(row.get("name") or "").lower(),
            )
        )
        return rows

    def _build_players_roster_rows(
        self,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not self._players_online:
            return []

        player = state.get("player", {}) if isinstance(state, dict) else {}
        if not isinstance(player, dict):
            player = {}
        party = state.get("party", []) if isinstance(state, dict) else []
        if not isinstance(party, list):
            party = []
        others = state.get("players", []) if isinstance(state, dict) else []
        if not isinstance(others, list):
            others = []

        local_x = safe_float(player.get("x"), math.nan)
        local_y = safe_float(player.get("y"), math.nan)
        local_uid = str(player.get("uid") or "").strip()
        local_name = str(player.get("name") or "").strip()
        seen_uids: set[str] = set()
        seen_names: set[str] = set()
        rows: list[dict[str, Any]] = []

        def _distance_for(entry: dict[str, Any], fallback: object = None) -> float:
            direct = safe_float(
                entry.get("distance", fallback), math.nan
            )
            if math.isfinite(direct):
                return direct
            x = safe_float(entry.get("x"), math.nan)
            y = safe_float(entry.get("y"), math.nan)
            if (
                math.isfinite(local_x)
                and math.isfinite(local_y)
                and math.isfinite(x)
                and math.isfinite(y)
            ):
                return math.hypot(x - local_x, y - local_y)
            return math.nan

        def _append(
            source: dict[str, Any],
            *,
            is_self: bool = False,
            in_party: bool = False,
            party_slot: int | None = None,
            key_prefix: str = "",
        ) -> None:
            uid = str(source.get("uid") or "").strip()
            name = str(source.get("name") or "").strip() or "Unknown"
            if uid and uid in seen_uids:
                return
            if not uid and name.lower() in seen_names:
                return
            if uid:
                seen_uids.add(uid)
            seen_names.add(name.lower())
            key = uid or f"{key_prefix}:{name.lower()}"
            rows.append(
                {
                    "key": key,
                    "uid": uid,
                    "friend_key": uid or f"name:{name.lower()}",
                    "name": name,
                    "class": str(source.get("class") or "").strip(),
                    "level": safe_int(source.get("level"), 0),
                    "x": source.get("x"),
                    "y": source.get("y"),
                    "z": source.get("z"),
                    "distance": _distance_for(source),
                    "is_self": is_self,
                    "in_party": in_party or is_self,
                    "party_slot": -1 if is_self else (
                        party_slot if party_slot is not None else -1
                    ),
                    "list_kind": "world",
                }
            )

        if not self._players_connected:
            return rows

        if local_name or local_uid:
            _append(player, is_self=True, in_party=True, key_prefix="self")

        party_slot = 0
        for member in party:
            if not isinstance(member, dict):
                continue
            if not bool(member.get("hero_valid", True)):
                continue
            member_uid = str(member.get("uid") or "").strip()
            if local_uid and member_uid == local_uid:
                continue
            _append(
                member,
                in_party=True,
                party_slot=party_slot,
                key_prefix="party",
            )
            party_slot += 1

        for other in others:
            if not isinstance(other, dict):
                continue
            other_uid = str(other.get("uid") or "").strip()
            if local_uid and other_uid == local_uid:
                continue
            _append(other, key_prefix="layer")

        return rows

    @staticmethod
    def _players_sort_key(sort_mode: str):
        if sort_mode == "name":
            return lambda row: str(row.get("name") or "").lower()
        if sort_mode == "level":
            return lambda row: (
                -safe_int(row.get("level"), 0),
                str(row.get("name") or "").lower(),
            )

        def _distance_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
            distance = safe_float(row.get("distance"), math.nan)
            finite = math.isfinite(distance)
            # Bucket distance so tiny movement doesn't constantly reshuffle rows.
            bucket = math.floor(distance / 5.0) * 5.0 if finite else math.inf
            return (
                0 if finite else 1,
                bucket,
                str(row.get("name") or "").lower(),
            )

        return _distance_sort_key

    def _filter_sort_players_rows(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        self_rows: list[dict[str, Any]] = []
        party_rows: list[dict[str, Any]] = []
        other_rows: list[dict[str, Any]] = []
        for row in rows:
            if row.get("is_self"):
                self_rows.append(row)
            elif row.get("in_party"):
                party_rows.append(row)
            else:
                other_rows.append(row)

        party_rows.sort(
            key=lambda row: (
                safe_int(row.get("party_slot"), 10_000),
                str(row.get("name") or "").lower(),
            )
        )

        party_only = self.players_party_only_button.isChecked()
        search = self.players_search.text().strip().lower()
        if party_only:
            other_rows = []
        elif search:
            other_rows = [
                row
                for row in other_rows
                if search in str(row.get("name") or "").lower()
            ]

        sort_mode = str(self.players_sort_combo.currentData() or "distance")
        sort_key = self._players_sort_key(sort_mode)
        class_pin = self._players_selected_class_pin()
        if class_pin:
            pinned = [
                row
                for row in other_rows
                if str(row.get("class") or "").strip().lower() == class_pin
            ]
            rest = [
                row
                for row in other_rows
                if str(row.get("class") or "").strip().lower() != class_pin
            ]
            pinned.sort(key=sort_key)
            rest.sort(key=sort_key)
            other_rows = pinned + rest
        else:
            other_rows.sort(key=sort_key)

        return self_rows + party_rows + other_rows

    @staticmethod
    def _players_instance_label(instance: dict[str, Any]) -> str:
        kind = str(instance.get("type") or "").strip().lower()
        if instance.get("is_rift") or kind == "rift":
            return "Rift"
        if instance.get("is_dungeon") or kind == "dungeon":
            return "Dungeon"
        if kind == "instance":
            return "Instance"
        if instance.get("is_world_map") or kind == "world_map":
            return "World"
        activity = str(instance.get("activity_kind") or "").strip()
        if activity:
            return activity.replace("_", " ").title()
        if kind and kind != "unknown":
            return kind.replace("_", " ").title()
        return "Layer"

    def _show_map_player_context_menu(self, player: object) -> None:
        if not isinstance(player, dict):
            return
        if player.get("is_self"):
            return
        name = str(player.get("name") or "").strip() or "Unknown"
        uid = str(player.get("uid") or "").strip()
        entry = dict(player)
        entry.setdefault("friend_key", uid or f"name:{name.lower()}")
        entry.setdefault("key", uid or entry["friend_key"])

        menu = QtWidgets.QMenu(self if isinstance(self, QtWidgets.QWidget) else None)
        title = menu.addAction(name)
        title.setEnabled(False)
        if entry.get("in_party"):
            party_label = menu.addAction("Party member")
            party_label.setEnabled(False)
        menu.addSeparator()

        focus_action = menu.addAction("Focus")
        x = safe_float(entry.get("x"), math.nan)
        y = safe_float(entry.get("y"), math.nan)
        focus_action.setEnabled(math.isfinite(x) and math.isfinite(y))
        follow_key = ""
        if hasattr(self, "radar"):
            follow_key = self.radar.follow_key_for(entry)
            if self.radar.follow_target_key() == follow_key:
                focus_action.setText("Stop Following")
            elif self._players_last_focus_key == follow_key:
                focus_action.setText("Follow")
        focus_action.triggered.connect(
            lambda _checked=False, payload=dict(entry): self._players_focus_entry(
                payload
            )
        )

        profile_action = menu.addAction("Open Steam Profile")
        profile_action.setEnabled(
            farever_uid_to_steamid64(uid) is not None
            or normalize_steamid64(entry.get("steamid64")) is not None
        )
        profile_action.triggered.connect(
            lambda _checked=False, payload=dict(entry): (
                self._players_open_steam_profile(payload)
            )
        )

        friend_key = str(entry.get("friend_key") or uid).strip()
        is_friend = bool(
            hasattr(self, "_friend_store")
            and (
                (uid and self._friend_store.contains(uid))
                or (friend_key and self._friend_store.contains(friend_key))
            )
        )
        friend_action = menu.addAction(
            "Remove Friend" if is_friend else "Add Friend"
        )
        friend_action.setEnabled(bool(uid or name))
        friend_action.triggered.connect(
            lambda _checked=False, payload=dict(entry): self._players_toggle_friend(
                payload
            )
        )

        menu.addSeparator()
        copy_name = menu.addAction("Copy Name")
        copy_name.triggered.connect(
            lambda _checked=False, text=name: QtWidgets.QApplication.clipboard().setText(
                text
            )
        )
        copy_uid = menu.addAction("Copy UID")
        copy_uid.setEnabled(bool(uid))
        copy_uid.triggered.connect(
            lambda _checked=False, text=uid: QtWidgets.QApplication.clipboard().setText(
                text
            )
        )
        menu.exec(QtGui.QCursor.pos())

    def _players_row_selected(self, entry: object) -> None:
        if not isinstance(entry, dict):
            return
        key = str(entry.get("key") or "")
        self._players_selected_key = key or None
        self._players_selected_entry = dict(entry)
        for row in self._players_row_widgets + self._friends_row_widgets:
            row.set_selected(str(row.entry().get("key") or "") == key)

    def _players_row_activated(self, entry: object) -> None:
        if isinstance(entry, dict):
            self._players_row_selected(entry)
            self._players_focus_entry(entry)
        else:
            self._players_focus_entry(self._players_selected_entry)

    def _players_toggle_friend(self, entry: object) -> None:
        if not isinstance(entry, dict):
            return
        if entry.get("is_self"):
            toast = getattr(self, "_toast_host", None)
            if toast is not None:
                toast.show_message("Cannot add yourself to friends", kind="error")
            return
        uid = str(entry.get("uid") or "").strip()
        # Fallback identity when Player.uid is missing on the layer sample.
        friend_key = uid or str(entry.get("friend_key") or "").strip()
        if not friend_key:
            name = str(entry.get("name") or "").strip()
            if name:
                friend_key = f"name:{name.lower()}"
                entry = dict(entry)
                entry["friend_key"] = friend_key
        if not friend_key:
            toast = getattr(self, "_toast_host", None)
            if toast is not None:
                toast.show_message(
                    "Cannot add friend — no player id/uid",
                    kind="error",
                )
            return
        toast = getattr(self, "_toast_host", None)
        if self._friend_store.contains_player(entry):
            # Prefer removing the concrete store key (uid, else name:).
            remove_key = uid or friend_key
            if not self._friend_store.contains(remove_key):
                name = str(entry.get("name") or "").strip().lower()
                if name and self._friend_store.contains(f"name:{name}"):
                    remove_key = f"name:{name}"
            ok = self._friend_store.remove(remove_key)
            if not ok and uid and remove_key != uid:
                ok = self._friend_store.remove(uid)
            if not ok and friend_key and remove_key != friend_key:
                ok = self._friend_store.remove(friend_key)
            if toast is not None:
                detail = self._friend_store.last_error
                toast.show_message(
                    "Removed from friends"
                    if ok
                    else f"Could not update friends{': ' + detail if detail else ''}",
                    kind="info" if ok else "error",
                )
        else:
            payload = dict(entry)
            if not uid:
                payload["uid"] = friend_key
            ok = self._friend_store.add_from_player(payload)
            if toast is not None:
                detail = self._friend_store.last_error
                toast.show_message(
                    "Added to friends"
                    if ok
                    else f"Could not update friends{': ' + detail if detail else ''}",
                    kind="info" if ok else "error",
                )
            if ok:
                self._players_request_steam_refresh()
        self._refresh_players_roster(force=True)

    def _players_open_steam_profile(self, entry: object) -> None:
        if isinstance(entry, dict):
            self._players_row_selected(entry)
        else:
            entry = self._players_selected_entry
        if not isinstance(entry, dict):
            return
        uid = entry.get("uid")
        steamid64 = entry.get("steamid64")
        if not open_steam_profile(uid, steamid64=steamid64):
            toast = getattr(self, "_toast_host", None)
            if toast is not None:
                toast.show_message("Could not open Steam profile", kind="error")

    def _players_focus_entry(self, entry: object) -> None:
        if isinstance(entry, dict):
            self._players_row_selected(entry)
        else:
            entry = self._players_selected_entry
        if not isinstance(entry, dict):
            return
        x = safe_float(entry.get("x"), math.nan)
        y = safe_float(entry.get("y"), math.nan)
        if not (math.isfinite(x) and math.isfinite(y)):
            return
        if not hasattr(self, "radar"):
            return
        key = self.radar.follow_key_for(entry)
        name = str(entry.get("name") or "").strip() or "player"
        toast = getattr(self, "_toast_host", None)
        if key and self.radar.follow_target_key() == key:
            self.radar.clear_follow()
            self._players_last_focus_key = None
            if toast is not None:
                toast.show_message(f"Stopped following {name}", kind="info")
        elif key and self._players_last_focus_key == key:
            if self.radar.set_follow_target(entry):
                if toast is not None:
                    toast.show_message(f"Following {name}", kind="info")
            else:
                self.radar.center_on(x, y)
                self._players_last_focus_key = key
        else:
            self.radar.clear_follow()
            self.radar.center_on(x, y)
            self._players_last_focus_key = key or None
        # Remove heavy status refresh call that may not exist.
        self._refresh_players_roster(force=True)
        if hasattr(self, "_set_active_page"):
            self._set_active_page("map")
        self.radar.update()
        # Keep footer / recenter affordance in sync with follow state.
        if hasattr(self, "_pan_state_changed"):
            self._pan_state_changed(self.radar.is_panned())


class PlayersPage:
    """Registered players page: shared context bar + body hosted by the shell."""

    PAGE_ID = "players"

    def __init__(self, context_bar, body) -> None:
        self.context_bar = context_bar
        self.body = body

    def on_activated(self) -> None:
        return None

    def on_deactivated(self) -> None:
        return None
