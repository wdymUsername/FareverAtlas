"""Top-bar status widgets for character vitals and the Nightling Rift."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .config import (
    CLASS_ICON_FILES,
    discover_project_asset,
    fmt_hp,
    fmt_number,
    safe_float,
    safe_int,
)
from .controls import ShieldOverlayBar
from .map_data import Snapshot


class CharacterStatusWidget(QtWidgets.QWidget):
    """Compact player identity and survivability display."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("characterStatus")
        self.setFixedHeight(30)
        self._displayed_class: str | None = None
        self._identity_signature: tuple[object, ...] | None = None
        self._vitals_signature: tuple[object, ...] | None = None
        self._tooltip_signature: tuple[object, ...] | None = None
        self._observed_max_hp = 0.0

        root_layout = QtWidgets.QHBoxLayout(self)
        root_layout.setContentsMargins(3, 0, 3, 0)
        root_layout.setSpacing(7)

        self.class_icon = QtWidgets.QLabel("?")
        self.class_icon.setObjectName("characterClassIcon")
        self.class_icon.setFixedSize(30, 30)
        self.class_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        text_container = QtWidgets.QWidget()
        text_layout = QtWidgets.QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(-1)

        title_layout = QtWidgets.QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(5)

        self.title = QtWidgets.QLabel("UNKNOWN · UNKNOWN 0")
        self.title.setObjectName("characterTitle")
        self.title.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.combat_icon = QtWidgets.QLabel("⚔")
        self.combat_icon.setObjectName("characterCombatIcon")
        self.combat_icon.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.combat_icon.setVisible(False)
        self.combat_icon.setToolTip("In combat")

        title_layout.addWidget(self.title)
        title_layout.addWidget(self.combat_icon)
        title_layout.addStretch(1)

        vitals_layout = QtWidgets.QHBoxLayout()
        vitals_layout.setContentsMargins(0, 0, 0, 0)
        vitals_layout.setSpacing(6)

        self.hp_label = QtWidgets.QLabel("HP")
        self.hp_label.setObjectName("characterStatLabel")
        self.hp_bar = ShieldOverlayBar()
        self.offline_label = QtWidgets.QLabel("offline")
        self.offline_label.setObjectName("characterOfflineLabel")
        self.offline_label.setVisible(False)

        vitals_layout.addWidget(self.hp_label)
        vitals_layout.addWidget(self.hp_bar, 1)
        vitals_layout.addWidget(self.offline_label, 1)

        text_layout.addLayout(title_layout)
        text_layout.addLayout(vitals_layout)
        root_layout.addWidget(self.class_icon)
        root_layout.addWidget(text_container)

    def update_snapshot(self, snapshot: Snapshot) -> None:
        self.hp_label.setVisible(True)
        self.hp_bar.setVisible(True)
        self.offline_label.setVisible(False)
        state = snapshot.state if isinstance(snapshot.state, dict) else {}
        player = state.get("player", {}) if isinstance(state, dict) else {}
        dps = state.get("dps", {}) if isinstance(state, dict) else {}
        if not isinstance(player, dict):
            player = {}
        if not isinstance(dps, dict):
            dps = {}

        name = str(player.get("name") or "Unknown").upper()
        character_class = str(player.get("class") or "Unknown")
        level = safe_int(player.get("level"), 0)
        identity_signature = (name, character_class, level)
        if identity_signature != self._identity_signature:
            self._identity_signature = identity_signature
            self.title.setText(f"{name} · {character_class.upper()} {level}")
            self._update_class_icon(character_class)

        hp = max(0.0, safe_float(player.get("hp"), 0.0))
        max_hp = max(0.0, safe_float(player.get("max_hp"), 0.0))
        shield = max(0.0, safe_float(player.get("shield"), 0.0))
        maximum_available = max_hp > 0.0
        if maximum_available:
            self._observed_max_hp = max_hp
        else:
            self._observed_max_hp = max(self._observed_max_hp, hp)
        display_max = max_hp if maximum_available else self._observed_max_hp

        in_combat = bool(player.get("in_combat") or dps.get("in_combat"))
        vitals_signature = (
            fmt_hp(hp),
            fmt_hp(display_max),
            fmt_hp(shield),
            in_combat,
            maximum_available,
        )
        if vitals_signature != self._vitals_signature:
            self._vitals_signature = vitals_signature
            self.hp_bar.set_values(
                float(fmt_hp(hp)),
                float(fmt_hp(shield)),
                float(fmt_hp(display_max)),
                show_maximum=maximum_available,
            )
            self.combat_icon.setVisible(in_combat)
            self._align_vitals_width(in_combat)

        tooltip_signature = (
            identity_signature,
            vitals_signature,
            fmt_number(player.get("energy")),
            fmt_number(player.get("hp_regen")),
            fmt_number(player.get("energy_regen")),
        )
        if tooltip_signature != self._tooltip_signature:
            self._tooltip_signature = tooltip_signature
            self._update_tooltip(
                player=player,
                name=name,
                character_class=character_class,
                level=level,
                hp=hp,
                max_hp=max_hp,
                shield=shield,
                in_combat=in_combat,
            )

    def update_offline(self, player_profile: dict[str, object]) -> None:
        """Show persisted identity without presenting cached live vitals."""
        name = str(player_profile.get("name") or "Unknown").upper()
        character_class = str(player_profile.get("class") or "Unknown")
        level = safe_int(player_profile.get("level"), 0)
        self._identity_signature = (name, character_class, level, "offline")
        self.title.setText(f"{name} · {character_class.upper()} {level}")
        self._displayed_class = "__offline__"
        blank_path = discover_project_asset("classBlank.webp")
        pixmap = QtGui.QPixmap(str(blank_path)) if blank_path else QtGui.QPixmap()
        self.class_icon.setText("" if not pixmap.isNull() else "·")
        self.class_icon.setPixmap(
            pixmap.scaled(
                24,
                24,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            if not pixmap.isNull()
            else QtGui.QPixmap()
        )
        self.combat_icon.setVisible(False)
        self.hp_label.setVisible(False)
        self.hp_bar.setVisible(False)
        self.offline_label.setVisible(True)
        tooltip = f"{name.title()}\n{character_class} · Level {level}\n\nOffline"
        for widget in (self, self.class_icon, self.title, self.offline_label):
            widget.setToolTip(tooltip)

    def _update_class_icon(self, character_class: str) -> None:
        normalized_class = character_class.strip().lower()
        if normalized_class == self._displayed_class:
            return
        self._displayed_class = normalized_class
        icon_name = CLASS_ICON_FILES.get(normalized_class)
        icon_path = discover_project_asset(icon_name) if icon_name else None
        pixmap = QtGui.QPixmap(str(icon_path)) if icon_path else QtGui.QPixmap()

        if not pixmap.isNull():
            self.class_icon.setText("")
            self.class_icon.setPixmap(
                pixmap.scaled(
                    24,
                    24,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
            return

        self.class_icon.setPixmap(QtGui.QPixmap())
        initial = character_class[:1].upper() if character_class else "?"
        self.class_icon.setText(initial if initial.strip() else "?")

    def _align_vitals_width(self, in_combat: bool) -> None:
        title_width = self.title.fontMetrics().horizontalAdvance(self.title.text())
        combat_width = 0
        if in_combat:
            combat_width = (
                self.combat_icon.fontMetrics().horizontalAdvance(
                    self.combat_icon.text()
                )
                + 5
            )
        label_width = self.hp_label.fontMetrics().horizontalAdvance(
            self.hp_label.text()
        )
        bar_width = max(
            108,
            min(164, title_width + combat_width - label_width - 6),
        )
        self.hp_bar.setFixedWidth(bar_width)

    def _update_tooltip(
        self,
        *,
        player: dict[str, object],
        name: str,
        character_class: str,
        level: int,
        hp: float,
        max_hp: float,
        shield: float,
        in_combat: bool,
    ) -> None:
        tooltip = "\n".join(
            (
                name.title(),
                f"{character_class} · Level {level}",
                "",
                (
                    f"Health: {fmt_hp(hp)} / {fmt_hp(max_hp)}"
                    if max_hp > 0.0
                    else f"Health: {fmt_hp(hp)} (maximum unavailable)"
                ),
                f"Shield: {fmt_hp(shield)}",
                f"Energy: {fmt_number(player.get('energy'))}",
                f"Health regeneration: {fmt_number(player.get('hp_regen'))}",
                f"Energy regeneration: {fmt_number(player.get('energy_regen'))}",
                f"Status: {'In combat' if in_combat else 'Out of combat'}",
            )
        )
        for widget in (
            self,
            self.class_icon,
            self.title,
            self.combat_icon,
            self.hp_label,
            self.hp_bar,
        ):
            widget.setToolTip(tooltip)


class PartyMemberStatusWidget(QtWidgets.QWidget):
    """Compact party-member identity and health display for the top bar."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("partyMemberStatus")
        self.setFixedHeight(30)
        self.setMinimumWidth(108)
        self.setMaximumWidth(134)
        self._observed_max_hp = 0.0
        self._displayed_class: str | None = None
        self._identity_signature: tuple[str, str, str] | None = None
        self._vitals_signature: tuple[str, str, str, bool] | None = None
        self._tooltip_signature: tuple[object, ...] | None = None

        root_layout = QtWidgets.QHBoxLayout(self)
        root_layout.setContentsMargins(3, 0, 3, 0)
        root_layout.setSpacing(3)

        self.class_icon = QtWidgets.QLabel("?")
        self.class_icon.setObjectName("partyClassIcon")
        self.class_icon.setFixedSize(24, 24)
        self.class_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        text_container = QtWidgets.QWidget()
        text_layout = QtWidgets.QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(-1)

        self.title = QtWidgets.QLabel("UNKNOWN")
        self.title.setObjectName("partyMemberTitle")
        self.title.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        vitals_layout = QtWidgets.QHBoxLayout()
        vitals_layout.setContentsMargins(0, 0, 0, 0)
        vitals_layout.setSpacing(4)
        hp_label = QtWidgets.QLabel("HP")
        hp_label.setObjectName("characterStatLabel")
        self.hp_bar = ShieldOverlayBar()
        self.hp_bar.setFixedWidth(74)
        vitals_layout.addWidget(hp_label)
        vitals_layout.addWidget(self.hp_bar)

        text_layout.addWidget(self.title)
        text_layout.addLayout(vitals_layout)
        root_layout.addWidget(self.class_icon)
        root_layout.addWidget(text_container, 1)

    def set_placeholder(self) -> None:
        self.setProperty("empty", True)
        opacity = QtWidgets.QGraphicsOpacityEffect(self)
        opacity.setOpacity(0.45)
        self.setGraphicsEffect(opacity)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.title.setText("EMPTY")
        blank_path = discover_project_asset("classBlank.webp")
        blank_pixmap = (
            QtGui.QPixmap(str(blank_path)) if blank_path else QtGui.QPixmap()
        )
        if blank_pixmap.isNull():
            self.class_icon.setPixmap(QtGui.QPixmap())
            self.class_icon.setText("·")
        else:
            self.class_icon.setText("")
            self.class_icon.setPixmap(
                blank_pixmap.scaled(
                    21,
                    21,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.hp_bar.set_values(0.0, 0.0, 0.0)
        self.setToolTip("Open party slot")
        self.class_icon.setToolTip("Open party slot")
        self.title.setToolTip("Open party slot")
        self.hp_bar.setToolTip("Open party slot")

    def update_member(self, member: dict[str, object]) -> None:
        if self.property("empty"):
            self.setProperty("empty", False)
            self.setGraphicsEffect(None)
            style = self.style()
            style.unpolish(self)
            style.polish(self)
        name = str(member.get("name") or "Unknown")
        character_class = str(member.get("class") or "Unknown")
        distance = safe_float(member.get("_distance_m"), math.nan)
        distance_text = (
            f"{math.floor(distance + 0.5)} M"
            if math.isfinite(distance) and distance >= 0.0
            else "— M"
        )

        normalized_class = character_class.strip().lower()
        identity_signature = (name, normalized_class, distance_text)
        if identity_signature != self._identity_signature:
            self._identity_signature = identity_signature
            self.title.setText(f"{name.upper()} · {distance_text}")
            self._displayed_class = normalized_class
            icon_name = CLASS_ICON_FILES.get(normalized_class)
            icon_path = discover_project_asset(icon_name) if icon_name else None
            pixmap = QtGui.QPixmap(str(icon_path)) if icon_path else QtGui.QPixmap()
            if pixmap.isNull():
                self.class_icon.setPixmap(QtGui.QPixmap())
                self.class_icon.setText(
                    character_class[:1].upper() if character_class else "?"
                )
            else:
                self.class_icon.setText("")
                self.class_icon.setPixmap(
                    pixmap.scaled(
                        21,
                        21,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )

        hp = max(0.0, safe_float(member.get("hp"), 0.0))
        max_hp = max(0.0, safe_float(member.get("max_hp"), 0.0))
        shield = max(0.0, safe_float(member.get("shield"), 0.0))
        maximum_available = max_hp > 0.0
        if maximum_available:
            self._observed_max_hp = max_hp
        else:
            self._observed_max_hp = max(self._observed_max_hp, hp)
        display_max = max_hp if maximum_available else self._observed_max_hp
        vitals_signature = (
            fmt_hp(hp),
            fmt_hp(display_max),
            fmt_hp(shield),
            maximum_available,
        )
        if vitals_signature != self._vitals_signature:
            self._vitals_signature = vitals_signature
            self.hp_bar.set_values(
                float(vitals_signature[0]),
                float(vitals_signature[2]),
                float(vitals_signature[1]),
                show_maximum=False,
            )
        tooltip_signature = (identity_signature, vitals_signature)
        if tooltip_signature == self._tooltip_signature:
            return
        self._tooltip_signature = tooltip_signature
        health_detail = (
            f"Health: {fmt_hp(hp)} / {fmt_hp(max_hp)}"
            if maximum_available
            else f"Health: {fmt_hp(hp)} (maximum unavailable from game)"
        )
        tooltip = "\n".join(
            (
                name,
                character_class,
                f"Distance: {distance_text}",
                "",
                health_detail,
                f"Shield: {fmt_hp(shield)}",
            )
        )
        for widget in (self, self.class_icon, self.title, self.hp_bar):
            widget.setToolTip(tooltip)


class RiftStatusWidget(QtWidgets.QWidget):
    """Right-aligned hourly Nightling Rift countdown."""

    def __init__(
        self,
        icon_path: Path | None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("riftStatus")
        self.setFixedHeight(30)

        root_layout = QtWidgets.QHBoxLayout(self)
        root_layout.setContentsMargins(3, 0, 3, 0)
        root_layout.setSpacing(6)

        self.icon = QtWidgets.QLabel()
        self.icon.setObjectName("riftIcon")
        self.icon.setFixedSize(30, 30)
        self.icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._load_icon(icon_path)

        text_container = QtWidgets.QWidget()
        text_layout = QtWidgets.QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self.title = QtWidgets.QLabel("Nightling Rift")
        self.title.setObjectName("riftTitle")
        self.title.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.countdown = QtWidgets.QLabel("Opens in --:--")
        self.countdown.setObjectName("riftCountdown")
        self.countdown.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        text_layout.addWidget(self.title)
        text_layout.addWidget(self.countdown)
        root_layout.addWidget(self.icon)
        root_layout.addWidget(text_container)

        tooltip = "Location is not currently available."
        for widget in (self, self.icon, text_container, self.title, self.countdown):
            widget.setToolTip(tooltip)

        self.timer = QtCore.QTimer(self)
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_countdown)
        self.timer.start()
        self._update_countdown()

    def _load_icon(self, icon_path: Path | None) -> None:
        pixmap = QtGui.QPixmap(str(icon_path)) if icon_path else QtGui.QPixmap()
        if pixmap.isNull():
            self.icon.setVisible(False)
            return
        self.icon.setPixmap(
            pixmap.scaled(
                28,
                28,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _update_countdown(self) -> None:
        current_time = QtCore.QDateTime.currentDateTime().time()
        elapsed_seconds = current_time.minute() * 60 + current_time.second()
        remaining_seconds = (3600 - elapsed_seconds) % 3600
        if remaining_seconds == 0:
            self.countdown.setText("Opens now")
            return
        minutes, seconds = divmod(remaining_seconds, 60)
        self.countdown.setText(f"Opens in {minutes:02d}:{seconds:02d}")
