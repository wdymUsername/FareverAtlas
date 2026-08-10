"""Players page list row widgets."""

from __future__ import annotations

import math
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import CLASS_BLANK_RELATIVE_PATH, CLASS_ICON_FILES, discover_project_asset, safe_float, safe_int
from .steam import farever_uid_to_steamid64, steam_persona_label


class PlayerListRow(QtWidgets.QFrame):
    """Compact roster row: identity, uid, distance, Profile / Focus actions."""

    selected = QtCore.Signal(object)
    activated = QtCore.Signal(object)
    profileRequested = QtCore.Signal(object)
    focusRequested = QtCore.Signal(object)
    friendToggleRequested = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("playersListRow")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(48)
        self._entry: dict[str, Any] = {}
        self._selected = False
        self._displayed_class: str | None = None
        self._displayed_avatar_key: str | None = None

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(8)

        self.class_icon = QtWidgets.QLabel("")
        self.class_icon.setObjectName("playersRowClassIcon")
        self.class_icon.setFixedSize(28, 28)
        self.class_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        text_column = QtWidgets.QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(0)

        title_row = QtWidgets.QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)

        self.name_label = QtWidgets.QLabel("")
        self.name_label.setObjectName("playersRowName")
        self.name_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.badge_you = QtWidgets.QLabel("YOU")
        self.badge_you.setObjectName("playersRowBadgeYou")
        self.badge_you.setVisible(False)

        self.badge_party = QtWidgets.QLabel("PARTY")
        self.badge_party.setObjectName("playersRowBadgeParty")
        self.badge_party.setVisible(False)

        self.badge_presence = QtWidgets.QLabel("")
        self.badge_presence.setObjectName("playersRowBadgePresence")
        self.badge_presence.setVisible(False)

        self.badge_steam_friend = QtWidgets.QLabel("STEAM")
        self.badge_steam_friend.setObjectName("playersRowBadgeSteamFriend")
        self.badge_steam_friend.setToolTip("Steam friend")
        self.badge_steam_friend.setVisible(False)

        self.badge_steam = QtWidgets.QLabel("")
        self.badge_steam.setObjectName("playersRowBadgeSteam")
        self.badge_steam.setVisible(False)

        title_row.addWidget(self.name_label, 0)
        title_row.addWidget(self.badge_you, 0)
        title_row.addWidget(self.badge_party, 0)
        title_row.addWidget(self.badge_presence, 0)
        title_row.addWidget(self.badge_steam_friend, 0)
        title_row.addWidget(self.badge_steam, 0)
        title_row.addStretch(1)

        meta_row = QtWidgets.QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)

        self.meta_label = QtWidgets.QLabel("")
        self.meta_label.setObjectName("playersRowMeta")
        self.meta_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.uid_label = QtWidgets.QLabel("")
        self.uid_label.setObjectName("playersRowUid")
        self.uid_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.uid_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        meta_row.addWidget(self.meta_label, 0)
        meta_row.addWidget(self.uid_label, 0)
        meta_row.addStretch(1)

        text_column.addLayout(title_row)
        text_column.addLayout(meta_row)

        self.distance_label = QtWidgets.QLabel("")
        self.distance_label.setObjectName("playersRowDistance")
        self.distance_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.distance_label.setMinimumWidth(56)

        actions = QtWidgets.QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)

        self.friend_button = QtWidgets.QToolButton()
        self.friend_button.setObjectName("playersRowFriendButton")
        self.friend_button.setText("Add")
        self.friend_button.setFixedSize(40, 26)
        self.friend_button.setAutoRaise(False)
        self.friend_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.friend_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.friend_button.setToolTip("Add to friends")
        self.friend_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.friend_button.clicked.connect(self._emit_friend_toggle)

        self.profile_button = QtWidgets.QToolButton()
        self.profile_button.setObjectName("playersRowProfileButton")
        self.profile_button.setText("Profile")
        self.profile_button.setFixedSize(54, 26)
        self.profile_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.profile_button.setToolTip("Open Steam profile")
        self.profile_button.clicked.connect(self._emit_profile)

        self.focus_button = QtWidgets.QToolButton()
        self.focus_button.setObjectName("playersRowFocusButton")
        self.focus_button.setText("Focus")
        self.focus_button.setFixedSize(48, 26)
        self.focus_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.focus_button.setToolTip("Center the map on this player")
        self.focus_button.clicked.connect(self._emit_focus)

        actions.addWidget(self.friend_button, 0)
        actions.addWidget(self.profile_button, 0)
        actions.addWidget(self.focus_button, 0)

        root.addWidget(self.class_icon, 0)
        root.addLayout(text_column, 1)
        root.addWidget(self.distance_label, 0)
        root.addLayout(actions, 0)

    def entry(self) -> dict[str, Any]:
        return self._entry

    def set_selected(self, selected: bool) -> None:
        selected = bool(selected)
        if selected == self._selected:
            return
        self._selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._entry = dict(entry)
        is_friend_list = str(entry.get("list_kind") or "") == "friend"
        name = str(entry.get("name") or "Unknown")
        character_class = str(entry.get("class") or "").strip()
        level = safe_int(entry.get("level"), 0)
        uid = str(entry.get("uid") or "").strip()
        steamid64 = farever_uid_to_steamid64(uid)
        if steamid64 is None:
            raw_sid = str(entry.get("steamid64") or "").strip()
            steamid64 = int(raw_sid) if raw_sid.isdigit() else None

        self.name_label.setText(name)
        self.badge_you.setVisible(bool(entry.get("is_self")) and not is_friend_list)
        self.badge_party.setVisible(
            bool(entry.get("in_party"))
            and not bool(entry.get("is_self"))
            and not is_friend_list
        )
        self.badge_steam_friend.setVisible(bool(entry.get("is_steam_friend")))

        presence = str(entry.get("presence") or "").strip().lower()
        if is_friend_list and presence in {"here", "away"}:
            self.badge_presence.setText(presence.upper())
            self.badge_presence.setProperty("presence", presence)
            self.badge_presence.style().unpolish(self.badge_presence)
            self.badge_presence.style().polish(self.badge_presence)
            self.badge_presence.setVisible(True)
            self.badge_presence.setToolTip(
                "On this layer" if presence == "here" else "Not on this layer"
            )
        else:
            self.badge_presence.clear()
            self.badge_presence.setVisible(False)

        steam_summary = entry.get("steam_summary")
        steam_label, steam_tip = steam_persona_label(
            steam_summary if isinstance(steam_summary, dict) else None
        )
        if steam_label:
            self.badge_steam.setText(steam_label)
            self.badge_steam.setVisible(True)
            self.badge_steam.setToolTip(steam_tip or steam_label)
            private = "private" in steam_label.lower() or (
                "private" in (steam_tip or "").lower()
            )
            self.badge_steam.setProperty("steamState", "private" if private else "ok")
            self.badge_steam.style().unpolish(self.badge_steam)
            self.badge_steam.style().polish(self.badge_steam)
        else:
            self.badge_steam.clear()
            self.badge_steam.setVisible(False)

        class_text = character_class.title() if character_class else "Unknown"
        if level > 0:
            self.meta_label.setText(f"{class_text} · {level}")
        else:
            self.meta_label.setText(class_text)

        if uid:
            self.uid_label.setText(uid)
            self.uid_label.setVisible(True)
        else:
            self.uid_label.clear()
            self.uid_label.setVisible(False)

        avatar = entry.get("steam_avatar")
        if isinstance(avatar, QtGui.QPixmap) and not avatar.isNull():
            avatar_key = f"steam:{steamid64}"
            if avatar_key != self._displayed_avatar_key:
                self._displayed_avatar_key = avatar_key
                self._displayed_class = None
                self.class_icon.setText("")
                self.class_icon.setPixmap(avatar)
        else:
            self._displayed_avatar_key = None
            self._update_class_icon(character_class)

        if is_friend_list and presence != "here":
            self.distance_label.setText("—")
        else:
            self._set_distance(entry.get("distance"))

        x = safe_float(entry.get("x"), math.nan)
        y = safe_float(entry.get("y"), math.nan)
        can_focus = math.isfinite(x) and math.isfinite(y)
        self.focus_button.setEnabled(can_focus)
        self.focus_button.setVisible(not is_friend_list or can_focus)
        if entry.get("is_followed"):
            self.focus_button.setText("Unfollow")
            self.focus_button.setToolTip("Stop following this player")
        elif entry.get("focus_armed"):
            self.focus_button.setText("Follow")
            self.focus_button.setToolTip("Follow this player on the map")
        else:
            self.focus_button.setText("Focus")
            self.focus_button.setToolTip(
                "Center the map on this player (click again to follow)"
            )
        self.profile_button.setEnabled(steamid64 is not None)
        if steamid64 is None:
            self.profile_button.setToolTip("No Steam profile for this player")
        else:
            self.profile_button.setToolTip(
                f"Open Steam profile ({steamid64})"
            )

        is_friend = bool(entry.get("is_friend"))
        # Allow add when we have a Steam uid, or at least a stable name key.
        can_friend = (bool(uid) or bool(name)) and not bool(entry.get("is_self"))
        self.friend_button.setVisible(can_friend)
        self.friend_button.setEnabled(can_friend)
        if is_friend_list or is_friend:
            self.friend_button.setText("✓")
            self.friend_button.setToolTip("Remove from friends")
            self.friend_button.setProperty("friendActive", True)
        else:
            self.friend_button.setText("Add")
            self.friend_button.setToolTip("Add to friends")
            self.friend_button.setProperty("friendActive", False)
        self.friend_button.style().unpolish(self.friend_button)
        self.friend_button.style().polish(self.friend_button)

        tooltip_bits = [name, class_text]
        if level > 0:
            tooltip_bits.append(f"Level {level}")
        if uid:
            tooltip_bits.append(uid)
        if steamid64 is not None:
            tooltip_bits.append(str(steamid64))
        if entry.get("is_self"):
            tooltip_bits.append("You")
        elif entry.get("in_party"):
            tooltip_bits.append("Party")
        if entry.get("is_steam_friend"):
            tooltip_bits.append("Steam friend")
        if presence:
            tooltip_bits.append(presence.title())
        if steam_tip:
            tooltip_bits.append(steam_tip)
        distance = safe_float(entry.get("distance"), float("nan"))
        if math.isfinite(distance):
            tooltip_bits.append(f"{distance:.0f} m")
        tip = " · ".join(tooltip_bits)
        self.setToolTip(tip)

    def _emit_friend_toggle(self) -> None:
        self.selected.emit(self._entry)
        self.friendToggleRequested.emit(dict(self._entry))

    def _emit_profile(self) -> None:
        self.selected.emit(self._entry)
        self.profileRequested.emit(self._entry)

    def _emit_focus(self) -> None:
        self.selected.emit(self._entry)
        self.focusRequested.emit(self._entry)

    def _set_distance(self, distance: object) -> None:
        value = safe_float(distance, float("nan"))
        if not math.isfinite(value):
            self.distance_label.setText("—")
            return
        if value < 10.0:
            self.distance_label.setText(f"{value:.1f} m")
        else:
            self.distance_label.setText(f"{value:.0f} m")

    def _update_class_icon(self, character_class: str) -> None:
        normalized = character_class.strip().lower()
        if normalized in {"", "unknown", "none", "null"}:
            normalized = "__blank__"
        if normalized == self._displayed_class:
            return
        self._displayed_class = normalized
        if normalized == "__blank__":
            blank_path = discover_project_asset(CLASS_BLANK_RELATIVE_PATH)
            pixmap = QtGui.QPixmap(str(blank_path)) if blank_path else QtGui.QPixmap()
        else:
            icon_name = CLASS_ICON_FILES.get(normalized)
            icon_path = discover_project_asset(icon_name) if icon_name else None
            pixmap = QtGui.QPixmap(str(icon_path)) if icon_path else QtGui.QPixmap()
        if pixmap.isNull():
            self.class_icon.setPixmap(QtGui.QPixmap())
            self.class_icon.setText("·")
            return
        self.class_icon.setText("")
        self.class_icon.setPixmap(
            pixmap.scaled(
                24,
                24,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _is_action_child(self, child: QtWidgets.QWidget | None) -> bool:
        if child is None:
            return False
        for button in (
            self.profile_button,
            self.focus_button,
            self.friend_button,
        ):
            if child is button or button.isAncestorOf(child):
                return True
        return False

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if self._is_action_child(child):
                super().mousePressEvent(event)
                return
            self.selected.emit(self._entry)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if self._is_action_child(child):
                super().mouseDoubleClickEvent(event)
                return
            self.activated.emit(self._entry)
        super().mouseDoubleClickEvent(event)
