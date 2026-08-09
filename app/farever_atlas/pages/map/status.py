"""Top-bar status widgets for character vitals, currencies, game time, and Nightling Rift."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import (
    CLASS_ICON_FILES,
    discover_project_asset,
    fmt_hp,
    fmt_number,
    safe_float,
    safe_int,
)
from ...controls import ShieldOverlayBar
from ...currency_caps import enrich_currencies
from ...telemetry import _sanitize_player_display_name
from .data import Snapshot


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

        self.class_icon = QtWidgets.QLabel("")
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

        self.title = QtWidgets.QLabel("WAITING · —")
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
        self._apply_class_blank_icon()

    def update_snapshot(self, snapshot: Snapshot) -> None:
        self.hp_label.setVisible(True)
        self.hp_bar.setVisible(True)
        self.offline_label.setVisible(False)
        state = snapshot.state if isinstance(snapshot.state, dict) else {}
        player = state.get("player", {}) if isinstance(state, dict) else {}
        if not isinstance(player, dict):
            player = {}

        # Main-style identity: always paint NAME · CLASS LEVEL.
        # Telemetry already drops prefab/world IDs from player.name.
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

        # Character combat icon follows the hero's in-combat bit. Do not OR with
        # dps.in_combat here: observed-nearby DPS stays active while others fight
        # nearby, which falsely kept the ⚔ icon on after leaving combat.
        in_combat = bool(player.get("in_combat"))
        if self.combat_icon.isVisible() != in_combat:
            self.combat_icon.setVisible(in_combat)
            self._align_vitals_width(in_combat)
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

    def update_waiting(self) -> None:
        """Online mode without a live attach — blank class, no fake vitals."""
        self._identity_signature = ("waiting",)
        self._vitals_signature = None
        self._tooltip_signature = None
        self._displayed_class = "__waiting__"
        self.title.setText("WAITING · —")
        self._apply_class_blank_icon()
        self.combat_icon.setVisible(False)
        self.hp_label.setVisible(True)
        self.hp_bar.setVisible(True)
        self.hp_bar.set_values(0.0, 0.0, 0.0, show_maximum=False)
        self.offline_label.setVisible(False)
        self._align_vitals_width(False)
        tooltip = "Waiting for live player data"
        for widget in (
            self,
            self.class_icon,
            self.title,
            self.hp_label,
            self.hp_bar,
        ):
            widget.setToolTip(tooltip)

    def update_offline(self) -> None:
        """Offline mode — blank class and the bottom offline label only."""
        self._identity_signature = ("offline",)
        self._vitals_signature = None
        self._tooltip_signature = None
        self._displayed_class = "__offline__"
        self.title.clear()
        self._apply_class_blank_icon()
        self.combat_icon.setVisible(False)
        self.hp_label.setVisible(False)
        self.hp_bar.setVisible(False)
        self.offline_label.setVisible(True)
        tooltip = "Offline"
        for widget in (self, self.class_icon, self.title, self.offline_label):
            widget.setToolTip(tooltip)

    def _apply_class_blank_icon(self) -> None:
        blank_path = discover_project_asset("classBlank.webp")
        pixmap = QtGui.QPixmap(str(blank_path)) if blank_path else QtGui.QPixmap()
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

    def _update_class_icon(self, character_class: str) -> None:
        normalized_class = character_class.strip().lower()
        if normalized_class in {"", "unknown", "none", "null"}:
            normalized_class = "__blank__"
        if normalized_class == self._displayed_class:
            return
        self._displayed_class = normalized_class
        if normalized_class == "__blank__":
            self._apply_class_blank_icon()
            return
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

        self._apply_class_blank_icon()

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

    def set_placeholder(self, *, opacity: float = 0.45) -> None:
        self.setProperty("empty", True)
        effect = QtWidgets.QGraphicsOpacityEffect(self)
        effect.setOpacity(max(0.15, min(1.0, opacity)))
        self.setGraphicsEffect(effect)
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

    def update_member(
        self,
        member: dict[str, object],
        *,
        show_distance: bool = True,
        distance_round_m: int = 1,
    ) -> None:
        if self.property("empty"):
            self.setProperty("empty", False)
            self.setGraphicsEffect(None)
            style = self.style()
            style.unpolish(self)
            style.polish(self)
        name = _sanitize_player_display_name(member.get("name")) or "Unknown"
        character_class = str(member.get("class") or "Unknown")
        distance = safe_float(member.get("_distance_m"), math.nan)
        round_step = max(1, int(distance_round_m))
        if math.isfinite(distance) and distance >= 0.0:
            rounded = int(round(distance / round_step) * round_step)
            distance_text = f"{rounded} M"
        else:
            distance_text = "— M"

        normalized_class = character_class.strip().lower()
        identity_signature = (name, normalized_class, distance_text, show_distance)
        if identity_signature != self._identity_signature:
            self._identity_signature = identity_signature
            if show_distance:
                self.title.setText(f"{name.upper()} · {distance_text}")
            else:
                self.title.setText(name.upper())
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
        tooltip_lines = [name, character_class]
        if show_distance:
            tooltip_lines.append(f"Distance: {distance_text}")
        tooltip_lines.extend(("", health_detail, f"Shield: {fmt_hp(shield)}"))
        tooltip = "\n".join(tooltip_lines)
        for widget in (self, self.class_icon, self.title, self.hp_bar):
            widget.setToolTip(tooltip)


class GameTimeStatusWidget(QtWidgets.QWidget):
    """Single-line in-game day cycle: icon · HH:MM · Period."""

    _PERIODS: tuple[tuple[float, str, str], ...] = (
        (0.20, "Night", "☾"),
        (0.30, "Dawn", "◔"),
        (0.70, "Day", "☀"),
        (0.80, "Dusk", "◑"),
        (1.01, "Night", "☾"),
    )

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gameTimeStatus")
        self.setFixedHeight(22)
        self._signature: tuple[object, ...] | None = None

        root_layout = QtWidgets.QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(4)

        self.icon = QtWidgets.QLabel("·")
        self.icon.setObjectName("gameTimeIcon")
        self.icon.setFixedSize(18, 18)
        self.icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.label = QtWidgets.QLabel("--:-- · —")
        self.label.setObjectName("gameTimeLabel")
        self.label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        root_layout.addWidget(self.icon)
        root_layout.addWidget(self.label)
        tooltip = "In-game time of day"
        for widget in (self, self.icon, self.label):
            widget.setToolTip(tooltip)

    @classmethod
    def _period_for_factor(cls, factor: float) -> tuple[str, str]:
        wrapped = factor % 1.0
        for upper, name, icon in cls._PERIODS:
            if wrapped < upper:
                return name, icon
        return "Night", "☾"

    def update_from_state(self, state: dict | None) -> None:
        tod = state.get("time_of_day") if isinstance(state, dict) else None
        if not isinstance(tod, dict):
            signature = ("missing",)
            if signature != self._signature:
                self._signature = signature
                self.icon.setText("·")
                self.label.setText("--:-- · —")
            return
        factor = safe_float(tod.get("factor"), math.nan)
        if not math.isfinite(factor):
            signature = ("invalid",)
            if signature != self._signature:
                self._signature = signature
                self.icon.setText("·")
                self.label.setText("--:-- · —")
            return
        factor = factor % 1.0
        total_minutes = int(factor * 24 * 60) % (24 * 60)
        hours, minutes = divmod(total_minutes, 60)
        period, icon = self._period_for_factor(factor)
        paused = bool(tod.get("paused"))
        signature = (hours, minutes, period, icon, paused)
        if signature == self._signature:
            return
        self._signature = signature
        self.icon.setText(icon)
        text = f"{hours:02d}:{minutes:02d} · {period}"
        if paused:
            text = f"{text} · paused"
        self.label.setText(text)

    def clear(self) -> None:
        self.update_from_state(None)


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


class CurrencyStatusWidget(QtWidgets.QWidget):
    """Compact 2x2 purse strip: Gold | Craft / Demonic Souls | Nightblood."""

    _CELLS: tuple[tuple[str, str], ...] = (
        ("Gold", "currency_gold.png"),
        ("CraftPoint", "currency_craft.png"),
        ("DemonicSoul", "currency_demonic_soul.png"),
        ("Nightblood", "currency_nightblood.png"),
    )
    _LABELS: dict[str, str] = {
        "Gold": "Gold",
        "CraftPoint": "Craft",
        "DemonicSoul": "Demonic souls",
        "Nightblood": "Nightblood",
    }

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("currencyStatus")
        self.setFixedHeight(36)
        self._signature: tuple[object, ...] | None = None
        self._amount_labels: dict[str, QtWidgets.QLabel] = {}

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(4, 0, 4, 0)
        root.setSpacing(4)

        grid = QtWidgets.QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(1)

        for index, (kind, asset_name) in enumerate(self._CELLS):
            row, col = divmod(index, 2)
            cell = QtWidgets.QWidget()
            cell.setObjectName("currencyCell")
            cell_layout = QtWidgets.QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(3)

            icon = QtWidgets.QLabel()
            icon.setObjectName("currencyIcon")
            icon.setFixedSize(14, 14)
            icon.setScaledContents(True)
            icon_path = discover_project_asset(asset_name)
            pixmap = QtGui.QPixmap(str(icon_path)) if icon_path else QtGui.QPixmap()
            if not pixmap.isNull():
                icon.setPixmap(pixmap)
            else:
                icon.setText("·")

            amount = QtWidgets.QLabel("—")
            amount.setObjectName("currencyAmount")
            amount.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
            self._amount_labels[kind] = amount

            cell_layout.addWidget(icon)
            cell_layout.addWidget(amount)
            grid.addWidget(cell, row, col * 2)

            if col == 0:
                sep = QtWidgets.QLabel("|")
                sep.setObjectName("currencySeparator")
                sep.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(sep, row, 1)

        root.addLayout(grid)
        self.setToolTip("Currencies")

    def update_from_state(self, state: dict | None) -> None:
        player = state.get("player") if isinstance(state, dict) else None
        amounts: dict[str, int | None] = {kind: None for kind, _ in self._CELLS}
        maxima: dict[str, int | None] = {kind: None for kind, _ in self._CELLS}
        raw_currencies: list[object] = []
        counters = None
        if isinstance(player, dict):
            raw = player.get("currencies") or []
            if isinstance(raw, list):
                raw_currencies = raw
            counters = player.get("currency_counters")
            if not isinstance(counters, dict):
                # Prefer enriched player counters; fall back to native bridge payload.
                native = state.get("native_bridge") if isinstance(state, dict) else None
                native_player = (
                    native.get("player") if isinstance(native, dict) else None
                )
                if isinstance(native_player, dict) and isinstance(
                    native_player.get("currency_counters"), dict
                ):
                    counters = native_player.get("currency_counters")
        for entry in enrich_currencies(raw_currencies, counters):
            kind = entry.get("kind")
            if kind not in amounts:
                continue
            try:
                amounts[str(kind)] = int(entry.get("amount") or 0)
            except (TypeError, ValueError):
                amounts[str(kind)] = None
            raw_max = entry.get("max")
            if raw_max is None:
                maxima[str(kind)] = None
            else:
                try:
                    maxima[str(kind)] = int(raw_max)
                except (TypeError, ValueError):
                    maxima[str(kind)] = None

        signature = tuple(
            (kind, amounts[kind], maxima[kind]) for kind, _ in self._CELLS
        )
        if signature == self._signature:
            return
        self._signature = signature

        tip_lines: list[str] = []
        for kind, _asset in self._CELLS:
            label = self._amount_labels[kind]
            value = amounts[kind]
            maximum = maxima[kind]
            if value is None:
                label.setText("—")
                capped = False
            else:
                label.setText(f"{value:,}")
                capped = maximum is not None and value >= maximum
            label.setProperty("capped", "true" if capped else "false")
            style = label.style()
            style.unpolish(label)
            style.polish(label)

            name = self._LABELS.get(kind, kind)
            if value is None and maximum is None:
                tip_lines.append(f"{name}: —")
            elif maximum is None:
                amount_text = "—" if value is None else f"{value:,}"
                tip_lines.append(f"{name}: {amount_text} (no cap)")
            else:
                amount_text = "—" if value is None else f"{value:,}"
                tip_lines.append(f"{name}: {amount_text} / {maximum:,}")
        self.setToolTip("\n".join(tip_lines))

    def clear(self) -> None:
        self.update_from_state(None)
