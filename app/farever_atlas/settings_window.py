"""In-window settings pages for Farever Atlas.

General, Map, Party, Combat, and proximity Alerts are live.
Cast-warning UI stays out until the bridge exposes cast data.
"""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .pages.map.fow_layers import FOW_LAYER_LABELS, FOW_LAYER_ORDER
from .cull_limits import CULL_SETTING_KEYS, clamp_cull_value, cull_setting


_ACCENT = QtGui.QColor("#587083")
_MUTED = QtGui.QColor("#344352")


class SettingsToggle(QtWidgets.QCheckBox):
    """Pill on/off switch used in settings rows."""

    _W = 36
    _H = 20

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsToggle")
        self.setText("")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self._W, self._H)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self._W, self._H)

    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    def hitButton(self, pos: QtCore.QPoint) -> bool:  # noqa: N802
        # Style sheets zero the indicator; treat the whole pill as clickable.
        return self.rect().contains(pos)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: ARG002
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        track = QtCore.QRectF(0.5, 0.5, self._W - 1, self._H - 1)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(_ACCENT if self.isChecked() else _MUTED)
        painter.drawRoundedRect(track, self._H / 2, self._H / 2)
        knob_d = self._H - 6
        knob_x = self._W - knob_d - 3 if self.isChecked() else 3.0
        painter.setBrush(QtGui.QColor("#eef3f7"))
        painter.drawEllipse(QtCore.QRectF(knob_x, 3.0, knob_d, knob_d))
        if self.hasFocus():
            pen = QtGui.QPen(QtGui.QColor("#9ec9e0"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track, self._H / 2, self._H / 2)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


ZOOM_CHOICES = (
    ("8x", 25),
    ("4x", 50),
    ("2x", 100),
    ("1x", 200),
    ("0.7x", 300),
    ("0.5x", 450),
    ("0.35x", 650),
    ("0.25x", 900),
)

DISTANCE_ROUND_CHOICES = (
    ("1 m", 1),
    ("5 m", 5),
    ("10 m", 10),
)

POI_DEFAULT_KINDS = (
    ("obelisk", "Obelisks"),
    ("respawn", "Respawns"),
    ("dungeon", "Dungeons"),
    ("merchant", "Merchants"),
    ("activity", "Activities"),
)

LOOT_DEFAULT_KINDS = (
    ("chest", "Chests"),
    ("red_orb", "Red Orbs"),
    ("plant", "Plants"),
    ("ore", "Ore"),
)

PARTY_SLOT_COUNT = 3

DPS_ROW_CHOICES = (1, 2, 3, 4, 5)
COMBAT_REFRESH_CHOICES = (
    ("4 FPS", 250),
    ("2 FPS", 500),
    ("1 FPS", 1000),
)
PROXIMITY_DURATION_CHOICES = (
    ("5 s", 5),
    ("10 s", 10),
    ("15 s", 15),
)

SETTINGS_PAGE_META = (
    ("General", "Application behavior and Steam friend lookup."),
    ("Map", "Map display, fog, markers, and cull ranges."),
    ("Party", "Party cards, markers, and distance display."),
    ("Combat", "Combat meter and compact DPS overlay."),
    ("Alerts", "Proximity toasts for elites, bosses, and critters."),
)


def apply_settings_defaults(settings: QtCore.QSettings) -> None:
    """Restore the first-slice settings keys to their defaults."""
    settings.setValue("app/always_on_top", False)
    settings.setValue("app/restore_window_positions", True)
    settings.setValue("map/zoom_radius", 200)
    settings.setValue("map/show_texture", True)
    settings.setValue("map/show_route_line", True)
    settings.setValue("map/fog_enabled", True)
    settings.setValue("map/fog_show_outlines", False)
    settings.setValue("map/fog_hide_markers", True)
    settings.setValue("map/fog_feather", True)
    settings.setValue("map/fog_max_tier", "Z3")
    for tier in FOW_LAYER_ORDER:
        settings.setValue(f"map/fog_layer_{tier}", tier == "Baked")
        settings.setValue(f"map/fog_layer_{tier}_invert", False)
    for kind, _label in POI_DEFAULT_KINDS:
        settings.setValue(f"map/show_poi_{kind}", True)
    for kind, _label in LOOT_DEFAULT_KINDS:
        settings.setValue(f"map/show_loot_{kind}", False)
    settings.setValue("map/show_pois", True)
    settings.setValue("map/show_collectibles", False)
    settings.setValue("map/show_enemies", True)
    settings.setValue("map/show_critters", True)
    settings.setValue("map/show_patrol_paths", True)
    settings.setValue("map/show_players", True)
    settings.setValue("map/show_player_names", False)
    settings.setValue("map/show_currencies", True)
    settings.setValue("map/show_game_time", True)
    settings.setValue("map/show_rift_timer", True)
    settings.setValue("map/show_dps_overlay", True)
    for key, (default, _minimum, _maximum) in CULL_SETTING_KEYS.items():
        settings.setValue(key, default)
    settings.setValue("party/show_empty_slots", True)
    settings.setValue("party/slot_count", PARTY_SLOT_COUNT)
    settings.setValue("party/show_distance", True)
    settings.setValue("party/distance_round_m", 1)
    settings.setValue("party/empty_slot_opacity", 45)
    settings.setValue("party/show_names", True)
    settings.setValue("party/show_health_rings", True)
    settings.setValue("party/dim_invalid", True)
    settings.setValue("combat/dps_visible_rows", 3)
    settings.setValue("combat/dps_opacity", 85)
    settings.setValue("combat/refresh_ms", 500)
    settings.setValue("combat/default_view", "damage")
    settings.setValue("combat/always_on_top", False)
    settings.setValue("combat/compact", False)
    settings.setValue("alerts/proximity_enabled", True)
    settings.setValue("alerts/proximity_enemies", True)
    settings.setValue("alerts/proximity_critters", True)
    settings.setValue("alerts/proximity_duration_s", 10)


class SettingsPanel(QtCore.QObject):
    """Builds settings pages and persists values into QSettings."""

    changed = QtCore.Signal()
    resetWindowsRequested = QtCore.Signal()
    resetOverlaysRequested = QtCore.Signal()

    def __init__(
        self,
        settings: QtCore.QSettings,
        parent: QtCore.QObject | None = None,
        *,
        dev_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self.dev_mode = bool(dev_mode)
        self._suppress = False
        self.cull_spins: dict[str, QtWidgets.QSpinBox] = {}
        builders = (
            self._general_tab,
            self._map_tab,
            self._party_tab,
            self._combat_tab,
            self._alerts_tab,
        )
        self.pages: list[tuple[str, str, QtWidgets.QWidget]] = []
        for (title, description), build in zip(SETTINGS_PAGE_META, builders):
            self.pages.append((title, description, build()))
        self.reload_from_settings()

    def reload_from_settings(self) -> None:
        self._suppress = True
        try:
            self.always_on_top.setChecked(
                _as_bool(self._settings.value("app/always_on_top"), False)
            )
            self.restore_windows.setChecked(
                _as_bool(
                    self._settings.value("app/restore_window_positions"), True
                )
            )
            self.steam_web_api_key.setText(
                str(self._settings.value("steam/web_api_key", "") or "")
            )
            self.steam_steamid64.setText(
                str(self._settings.value("steam/steamid64", "") or "")
            )

            radius = _as_int(self._settings.value("map/zoom_radius"), 200)
            zoom_index = min(
                range(len(ZOOM_CHOICES)),
                key=lambda index: abs(ZOOM_CHOICES[index][1] - radius),
            )
            self.default_zoom.setCurrentIndex(zoom_index)
            self.show_texture.setChecked(
                _as_bool(self._settings.value("map/show_texture"), True)
            )
            self.show_route.setChecked(
                _as_bool(self._settings.value("map/show_route_line"), True)
            )
            self.fog_enabled.setChecked(
                _as_bool(self._settings.value("map/fog_enabled"), True)
            )
            for tier, checkbox in self.fog_layer_checks.items():
                default = tier == "Baked"
                if not self._settings.contains(f"map/fog_layer_{tier}"):
                    if tier == "Baked":
                        default = True
                    elif tier == "Z0":
                        default = False
                    elif tier.startswith("Z1_"):
                        default = _as_bool(
                            self._settings.value("map/fog_layer_Z1"), False
                        )
                    elif tier.startswith("Z2_"):
                        default = _as_bool(
                            self._settings.value("map/fog_layer_Z2"), False
                        )
                    elif tier == "Z4":
                        default = _as_bool(
                            self._settings.value("map/fog_z4_layer"), False
                        )
                    else:
                        default = False
                checkbox.setChecked(
                    _as_bool(self._settings.value(f"map/fog_layer_{tier}"), default)
                )
            for tier, checkbox in self.fog_layer_invert_checks.items():
                default = False
                if not self._settings.contains(f"map/fog_layer_{tier}_invert"):
                    if tier.startswith("Z1_"):
                        default = _as_bool(
                            self._settings.value("map/fog_layer_Z1_invert"), False
                        )
                    elif tier.startswith("Z2_"):
                        default = _as_bool(
                            self._settings.value("map/fog_layer_Z2_invert"), False
                        )
                    elif tier == "Z4":
                        default = _as_bool(
                            self._settings.value("map/fog_z4_invert"), False
                        )
                checkbox.setChecked(
                    _as_bool(
                        self._settings.value(f"map/fog_layer_{tier}_invert"), default
                    )
                )
            self.fog_hide_markers.setChecked(
                _as_bool(self._settings.value("map/fog_hide_markers"), True)
            )
            self.fog_feather.setChecked(
                _as_bool(self._settings.value("map/fog_feather"), True)
            )
            self.fog_show_outlines.setChecked(
                _as_bool(self._settings.value("map/fog_show_outlines"), False)
            )
            fog_tier = str(
                self._settings.value("map/fog_max_tier", "Z3") or "Z3"
            ).upper()
            fog_index = max(0, self.fog_max_tier.findData(fog_tier))
            self.fog_max_tier.setCurrentIndex(fog_index)

            self.show_currencies.setChecked(
                _as_bool(self._settings.value("map/show_currencies"), True)
            )
            self.show_game_time.setChecked(
                _as_bool(self._settings.value("map/show_game_time"), True)
            )
            self.show_rift_timer.setChecked(
                _as_bool(self._settings.value("map/show_rift_timer"), True)
            )
            for key, spin in self.cull_spins.items():
                spin.setValue(cull_setting(self._settings, key))

            self.show_empty_slots.setChecked(
                _as_bool(self._settings.value("party/show_empty_slots"), True)
            )
            self.show_distance.setChecked(
                _as_bool(self._settings.value("party/show_distance"), True)
            )
            round_m = _as_int(self._settings.value("party/distance_round_m"), 1)
            round_index = next(
                (
                    index
                    for index, (_label, value) in enumerate(DISTANCE_ROUND_CHOICES)
                    if value == round_m
                ),
                0,
            )
            self.distance_rounding.setCurrentIndex(round_index)
            self.empty_opacity.setValue(
                max(
                    25,
                    min(
                        100,
                        _as_int(
                            self._settings.value("party/empty_slot_opacity"), 45
                        ),
                    ),
                )
            )
            self.show_party_names.setChecked(
                _as_bool(self._settings.value("party/show_names"), True)
            )
            self.show_health_rings.setChecked(
                _as_bool(self._settings.value("party/show_health_rings"), True)
            )
            self.dim_invalid.setChecked(
                _as_bool(self._settings.value("party/dim_invalid"), True)
            )

            self.dps_enabled.setChecked(
                _as_bool(self._settings.value("map/show_dps_overlay"), True)
            )
            rows = _as_int(self._settings.value("combat/dps_visible_rows"), 3)
            row_index = next(
                (
                    index
                    for index, value in enumerate(DPS_ROW_CHOICES)
                    if value == rows
                ),
                2,
            )
            self.dps_visible_rows.setCurrentIndex(row_index)
            self.dps_opacity.setValue(
                max(
                    25,
                    min(100, _as_int(self._settings.value("combat/dps_opacity"), 85)),
                )
            )
            refresh_ms = _as_int(self._settings.value("combat/refresh_ms"), 500)
            refresh_index = next(
                (
                    index
                    for index, (_label, value) in enumerate(COMBAT_REFRESH_CHOICES)
                    if value == refresh_ms
                ),
                1,
            )
            self.combat_refresh.setCurrentIndex(refresh_index)
            view = str(
                self._settings.value("combat/default_view", "damage") or "damage"
            ).lower()
            self.combat_default_view.setCurrentIndex(0 if view != "healing" else 1)
            self.combat_always_on_top.setChecked(
                _as_bool(self._settings.value("combat/always_on_top"), False)
            )
            self.combat_compact.setChecked(
                _as_bool(self._settings.value("combat/compact"), False)
            )

            self.proximity_enabled.setChecked(
                _as_bool(self._settings.value("alerts/proximity_enabled"), True)
            )
            self.proximity_enemies.setChecked(
                _as_bool(self._settings.value("alerts/proximity_enemies"), True)
            )
            self.proximity_critters.setChecked(
                _as_bool(self._settings.value("alerts/proximity_critters"), True)
            )
            duration_s = _as_int(
                self._settings.value("alerts/proximity_duration_s"), 10
            )
            duration_index = next(
                (
                    index
                    for index, (_label, value) in enumerate(
                        PROXIMITY_DURATION_CHOICES
                    )
                    if value == duration_s
                ),
                1,
            )
            self.proximity_duration.setCurrentIndex(duration_index)
        finally:
            self._suppress = False

    def reset_all_to_defaults(self) -> None:
        apply_settings_defaults(self._settings)
        self.reload_from_settings()
        self.resetWindowsRequested.emit()
        self.resetOverlaysRequested.emit()
        self.changed.emit()

    def _emit_changed(self) -> None:
        if not self._suppress:
            self.changed.emit()

    def _bind_bool(
        self,
        checkbox: QtWidgets.QCheckBox,
        key: str,
    ) -> None:
        checkbox.toggled.connect(
            lambda checked, settings_key=key: self._set_bool(settings_key, checked)
        )

    def _set_bool(self, key: str, checked: bool) -> None:
        if self._suppress:
            return
        self._settings.setValue(key, bool(checked))
        self._emit_changed()

    def _set_int(self, key: str, value: int) -> None:
        if self._suppress:
            return
        self._settings.setValue(key, int(value))
        self._emit_changed()

    def _set_cull_int(self, key: str, value: int) -> None:
        if self._suppress:
            return
        self._settings.setValue(key, clamp_cull_value(key, value))
        self._emit_changed()

    def _cull_spin(
        self,
        key: str,
        *,
        tooltip: str,
    ) -> QtWidgets.QSpinBox:
        _default, minimum, maximum = CULL_SETTING_KEYS[key]
        spin = QtWidgets.QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSuffix(" m")
        spin.setToolTip(tooltip)
        spin.valueChanged.connect(
            lambda value, settings_key=key: self._set_cull_int(settings_key, value)
        )
        self.cull_spins[key] = spin
        return spin

    @staticmethod
    def _page() -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(10)
        return page, layout

    @classmethod
    def _group(cls, title: str) -> tuple[QtWidgets.QGroupBox, QtWidgets.QVBoxLayout]:
        group = QtWidgets.QGroupBox(title)
        body = QtWidgets.QVBoxLayout(group)
        body.setContentsMargins(10, 10, 10, 8)
        body.setSpacing(0)
        return group, body

    @staticmethod
    def _prepare_field(field: QtWidgets.QWidget) -> QtWidgets.QWidget:
        if isinstance(field, QtWidgets.QCheckBox):
            field.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        elif isinstance(field, QtWidgets.QAbstractSpinBox):
            field.setFixedHeight(28)
            field.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        elif isinstance(field, QtWidgets.QComboBox):
            field.setFixedHeight(28)
            field.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            field.setSizeAdjustPolicy(
                QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents
            )
            field.setMinimumContentsLength(4)
        elif isinstance(field, QtWidgets.QLineEdit):
            field.setObjectName("settingsField")
            field.setFixedHeight(28)
            field.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            field.setMinimumWidth(160)
            field.setMaximumWidth(280)
            field.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
        elif isinstance(field, QtWidgets.QSlider):
            field.setMinimumWidth(140)
            field.setMaximumWidth(220)
            field.setFixedHeight(22)
            field.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        elif isinstance(field, QtWidgets.QPushButton):
            field.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        else:
            field.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
        return field

    @classmethod
    def _add_separator(cls, body: QtWidgets.QVBoxLayout) -> None:
        if body.count() <= 0:
            return
        sep = QtWidgets.QFrame()
        sep.setObjectName("settingsRowSeparator")
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        body.addWidget(sep)

    @classmethod
    def _add_setting(
        cls,
        body: QtWidgets.QVBoxLayout,
        title: str,
        field: QtWidgets.QWidget,
        hint: str = "",
    ) -> None:
        cls._add_separator(body)

        row = QtWidgets.QWidget()
        row.setObjectName("settingsRow")
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(2, 8, 2, 8)
        row_layout.setSpacing(16)

        left = QtWidgets.QWidget()
        left.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(3)
        title_lab = QtWidgets.QLabel(title)
        title_lab.setObjectName("settingsRowTitle")
        title_lab.setWordWrap(True)
        left_layout.addWidget(title_lab)
        if hint:
            hint_lab = QtWidgets.QLabel(hint)
            hint_lab.setObjectName("settingsRowHint")
            hint_lab.setWordWrap(True)
            hint_lab.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            left_layout.addWidget(hint_lab)

        field = cls._prepare_field(field)
        row_layout.addWidget(left, 1)
        row_layout.addWidget(
            field,
            0,
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )
        body.addWidget(row)

    @classmethod
    def _add_note(cls, body: QtWidgets.QVBoxLayout, text: str) -> None:
        cls._add_separator(body)
        note = QtWidgets.QLabel(text)
        note.setWordWrap(True)
        note.setObjectName("settingsDeferredNote")
        note.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        wrap = QtWidgets.QWidget()
        wrap_layout = QtWidgets.QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(2, 8, 2, 4)
        wrap_layout.setSpacing(0)
        wrap_layout.addWidget(note)
        body.addWidget(wrap)

    @classmethod
    def _add_action(cls, body: QtWidgets.QVBoxLayout, widget: QtWidgets.QWidget) -> None:
        wrap = QtWidgets.QWidget()
        wrap_layout = QtWidgets.QHBoxLayout(wrap)
        wrap_layout.setContentsMargins(2, 6, 2, 4)
        wrap_layout.setSpacing(0)
        wrap_layout.addWidget(widget, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        wrap_layout.addStretch(1)
        body.addWidget(wrap)

    @staticmethod
    def _finish(
        page: QtWidgets.QWidget,
        layout: QtWidgets.QVBoxLayout,
    ) -> QtWidgets.QWidget:
        layout.addStretch(1)
        return page

    @staticmethod
    def _pair_row(
        left: QtWidgets.QWidget,
        right: QtWidgets.QWidget,
    ) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        left_wrap = QtWidgets.QWidget()
        left_layout = QtWidgets.QHBoxLayout(left_wrap)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_label = QtWidgets.QLabel("XY")
        left_layout.addWidget(left_label)
        left_layout.addWidget(left, 1)
        right_wrap = QtWidgets.QWidget()
        right_layout = QtWidgets.QHBoxLayout(right_wrap)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_label = QtWidgets.QLabel("Z")
        right_layout.addWidget(right_label)
        right_layout.addWidget(right, 1)
        layout.addWidget(left_wrap, 1)
        layout.addWidget(right_wrap, 1)
        return row

    def _general_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        behavior, form = self._group("Application behavior")

        self.always_on_top = SettingsToggle()
        self._bind_bool(self.always_on_top, "app/always_on_top")
        self._add_setting(
            form,
            "Always on top",
            self.always_on_top,
            "Keep Atlas above other windows (Linux uses X11/XWayland).",
        )
        self.restore_windows = SettingsToggle()
        self._bind_bool(self.restore_windows, "app/restore_window_positions")
        self._add_setting(
            form,
            "Restore window positions",
            self.restore_windows,
            "Remember window layout between launches.",
        )
        layout.addWidget(behavior)

        steam, steam_form = self._group("Steam")
        self.steam_web_api_key = QtWidgets.QLineEdit()
        self.steam_web_api_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.steam_web_api_key.setPlaceholderText("Web API key (optional)")
        self.steam_web_api_key.setClearButtonEnabled(True)
        self.steam_web_api_key.setToolTip(
            "Used to cache friend Steam avatars and online status,\n"
            "and to detect Steam friends for the STEAM badge.\n"
            "Get a key at https://steamcommunity.com/dev/apikey\n"
            "Private profiles may still show Offline — Atlas labels those Private."
        )
        self.steam_web_api_key.editingFinished.connect(self._on_steam_api_key_changed)
        self._add_setting(
            steam_form,
            "Web API key",
            self.steam_web_api_key,
            "Caches friend avatars and the Steam-friend badge.",
        )
        self.steam_steamid64 = QtWidgets.QLineEdit()
        self.steam_steamid64.setPlaceholderText("Your SteamID64 (digits only)")
        self.steam_steamid64.setClearButtonEnabled(True)
        self.steam_steamid64.setToolTip(
            "Your 64-bit Steam ID (profile URL ends with /profiles/<this>).\n"
            "Needed with the Web API key for the Steam-friend badge.\n"
            "Friend list must be public (or GetFriendList returns 401)."
        )
        self.steam_steamid64.editingFinished.connect(self._on_steam_steamid64_changed)
        self._add_setting(
            steam_form,
            "Your SteamID64",
            self.steam_steamid64,
            "Your 64-bit Steam ID for friend lookup.",
        )
        steam_note = QtWidgets.QLabel(
            "Optional. Friends still work with Here/Away from the game layer. "
            "Steam-friend badge needs API key + SteamID64 and a readable friend list."
        )
        steam_note.setWordWrap(True)
        steam_note.setObjectName("settingsDeferredNote")
        layout.addWidget(steam)
        layout.addWidget(steam_note)

        actions, actions_form = self._group("Reset")
        self.reset_all_settings = QtWidgets.QPushButton(
            "Reset all settings to default"
        )
        self.reset_all_settings.setObjectName("resetAllSettingsButton")
        self.reset_all_settings.setToolTip(
            "Restore General, Map, Party, Combat, and Alerts settings to defaults"
        )
        self.reset_all_settings.setProperty("confirmReset", False)
        self._add_action(actions_form, self.reset_all_settings)
        layout.addWidget(actions)
        return self._finish(page, layout)

    def _map_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        display, form = self._group("Map display")

        self.default_zoom = QtWidgets.QComboBox()
        for label, _radius in ZOOM_CHOICES:
            self.default_zoom.addItem(label)
        self.default_zoom.currentIndexChanged.connect(self._on_zoom_changed)
        self._add_setting(
            form,
            "Default zoom",
            self.default_zoom,
            "Initial zoom when opening the map.",
        )
        self.show_texture = SettingsToggle()
        self._bind_bool(self.show_texture, "map/show_texture")
        self._add_setting(
            form,
            "Show map texture",
            self.show_texture,
            "Terrain and map artwork.",
        )
        self.show_route = SettingsToggle()
        self._bind_bool(self.show_route, "map/show_route_line")
        self._add_setting(
            form,
            "Waypoint route line",
            self.show_route,
            "Lines between waypoints.",
        )
        layout.addWidget(display)

        status_bar, status_form = self._group("Status bar")
        self.show_currencies = SettingsToggle()
        self._bind_bool(self.show_currencies, "map/show_currencies")
        self._add_setting(
            status_form,
            "Currencies",
            self.show_currencies,
            "Currency totals on the status bar.",
        )
        self.show_game_time = SettingsToggle()
        self._bind_bool(self.show_game_time, "map/show_game_time")
        self._add_setting(
            status_form,
            "Time of day",
            self.show_game_time,
            "In-game time of day.",
        )
        self.show_rift_timer = SettingsToggle()
        self._bind_bool(self.show_rift_timer, "map/show_rift_timer")
        self._add_setting(
            status_form,
            "Rift timer",
            self.show_rift_timer,
            "Rift timer when a rift is active.",
        )
        layout.addWidget(status_bar)

        fog, fog_form = self._group("Fog of war")
        self.fog_enabled = SettingsToggle()
        self._bind_bool(self.fog_enabled, "map/fog_enabled")
        self._add_setting(
            fog_form,
            "Enable fog",
            self.fog_enabled,
            "Reveal only explored areas.",
        )
        self.fog_feather = SettingsToggle()
        self._bind_bool(self.fog_feather, "map/fog_feather")
        self._add_setting(
            fog_form,
            "Soft fog edge (feather)",
            self.fog_feather,
            "Soften fog edges.",
        )
        self.fog_hide_markers = SettingsToggle()
        self._bind_bool(self.fog_hide_markers, "map/fog_hide_markers")
        self._add_setting(
            fog_form,
            "Hide markers under fog",
            self.fog_hide_markers,
            "Hide markers in unexplored areas.",
        )
        self.fog_show_outlines = SettingsToggle()
        self._bind_bool(self.fog_show_outlines, "map/fog_show_outlines")
        self._add_setting(
            fog_form,
            "Show region outlines",
            self.fog_show_outlines,
            "Region boundaries on the map.",
        )
        self._add_note(
            fog_form,
            "Outlines are inaccurate: the extracted zone polygons never lined "
            "up with the Atlas map. Math couldn't fix the transform; hand-editing "
            "the rings was not worth the time.",
        )

        self.fog_layer_checks: dict[str, QtWidgets.QCheckBox] = {}
        self.fog_layer_invert_checks: dict[str, QtWidgets.QCheckBox] = {}
        for tier in FOW_LAYER_ORDER:
            enabled = SettingsToggle()
            inverted = SettingsToggle()
            self.fog_layer_checks[tier] = enabled
            self.fog_layer_invert_checks[tier] = inverted
            self._bind_bool(enabled, f"map/fog_layer_{tier}")
            self._bind_bool(inverted, f"map/fog_layer_{tier}_invert")
            if self.dev_mode:
                label = FOW_LAYER_LABELS.get(tier, tier)
                self._add_setting(
                    fog_form,
                    f"{label} layer",
                    enabled,
                    "Dev: include this fog layer.",
                )
                self._add_setting(
                    fog_form,
                    f"{label} invert",
                    inverted,
                    "Dev: invert this fog layer mask.",
                )

        self.fog_max_tier = QtWidgets.QComboBox()
        self.fog_max_tier.addItem(
            "Z1 Primevalley/Honeywoods/Meridion/Enripit/Bel Etir/Slime", "Z1"
        )
        self.fog_max_tier.addItem("Z2 Azuram/Krisomal/Nescent/Eksod", "Z2")
        self.fog_max_tier.addItem("Z3 Crimson Island", "Z3")
        saved_tier = str(self._settings.value("map/fog_max_tier", "Z3") or "Z3").upper()
        tier_index = max(0, self.fog_max_tier.findData(saved_tier))
        self.fog_max_tier.setCurrentIndex(tier_index)
        self.fog_max_tier.currentIndexChanged.connect(self._on_fog_tier_changed)
        if self.dev_mode:
            self._add_setting(
                fog_form,
                "Legacy accessible through",
                self.fog_max_tier,
                "Dev: legacy fog tier ceiling.",
            )
        layout.addWidget(fog)

        ranges, range_form = self._group("Live detection limits")
        self._add_setting(
            range_form,
            "Enemies",
            self._pair_row(
                self._cull_spin(
                    "map/cull/enemy_xy_m",
                    tooltip="Atlas XY filter for enemy markers (max 500 m). 0 = Off.",
                ),
                self._cull_spin(
                    "map/cull/enemy_z_m",
                    tooltip="Hide enemies on other floors (max 120 m). 0 = Off.",
                ),
            ),
            "XY and elevation cull. 0 = Off.",
        )
        self._add_setting(
            range_form,
            "Critters",
            self._pair_row(
                self._cull_spin(
                    "map/cull/critter_xy_m",
                    tooltip="Atlas XY filter for critter markers (max 500 m). 0 = Off.",
                ),
                self._cull_spin(
                    "map/cull/critter_z_m",
                    tooltip="Hide critters on other floors (max 120 m). 0 = Off.",
                ),
            ),
            "XY and elevation cull. 0 = Off.",
        )
        self._add_setting(
            range_form,
            "Patrol",
            self._pair_row(
                self._cull_spin(
                    "map/cull/patrol_xy_m",
                    tooltip=(
                        "Only claim patrol paths for live units within this XY "
                        "range (max 500 m)."
                    ),
                ),
                self._cull_spin(
                    "map/cull/patrol_z_m",
                    tooltip="Patrol path elevation gate (max 120 m). 0 = Off.",
                ),
            ),
            "Claim patrol paths near live units. 0 = Off.",
        )
        self._add_setting(
            range_form,
            "Patrol leash",
            self._cull_spin(
                "map/cull/patrol_leash_m",
                tooltip="Max distance from a live unit to its path samples (max 200 m).",
            ),
            "Max distance from a unit to its path samples.",
        )
        self._add_setting(
            range_form,
            "Loot / NODE GUIDE",
            self._pair_row(
                self._cull_spin(
                    "map/cull/loot_xy_m",
                    tooltip="Live loot bubble radius (max 500 m).",
                ),
                self._cull_spin(
                    "map/cull/loot_z_m",
                    tooltip="Live loot elevation cull (max 160 m).",
                ),
            ),
            "Live loot bubble. 0 = Off.",
        )
        self._add_note(
            range_form,
            "Hide markers beyond XY / elevation from you. "
            "0 = Off. Maxima match the live game stream limit + sanity check.",
        )
        layout.addWidget(ranges)
        return self._finish(page, layout)

    def _party_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        cards, form = self._group("Party cards")

        self.show_empty_slots = SettingsToggle()
        self._bind_bool(self.show_empty_slots, "party/show_empty_slots")
        self._add_setting(
            form,
            "Show empty slots",
            self.show_empty_slots,
            "Keep vacant party slots visible.",
        )
        self.show_distance = SettingsToggle()
        self._bind_bool(self.show_distance, "party/show_distance")
        self._add_setting(
            form,
            "Show distance",
            self.show_distance,
            "Distance on party cards.",
        )
        self.distance_rounding = QtWidgets.QComboBox()
        for label, _value in DISTANCE_ROUND_CHOICES:
            self.distance_rounding.addItem(label)
        self.distance_rounding.currentIndexChanged.connect(
            self._on_distance_round_changed
        )
        self._add_setting(
            form,
            "Distance rounding",
            self.distance_rounding,
            "Round displayed distance.",
        )
        self.empty_opacity = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.empty_opacity.setRange(25, 100)
        self.empty_opacity.valueChanged.connect(
            lambda value: self._set_int("party/empty_slot_opacity", value)
        )
        self._add_setting(
            form,
            "Empty-slot opacity",
            self.empty_opacity,
            "Fade unused slots.",
        )
        layout.addWidget(cards)

        markers, marker_form = self._group("Map markers")
        self.show_party_names = SettingsToggle()
        self._bind_bool(self.show_party_names, "party/show_names")
        self._add_setting(
            marker_form,
            "Show names",
            self.show_party_names,
            "Names on map party markers.",
        )
        self.show_health_rings = SettingsToggle()
        self._bind_bool(self.show_health_rings, "party/show_health_rings")
        self._add_setting(
            marker_form,
            "Health rings",
            self.show_health_rings,
            "Health rings around party markers.",
        )
        self.dim_invalid = SettingsToggle()
        self._bind_bool(self.dim_invalid, "party/dim_invalid")
        self._add_setting(
            marker_form,
            "Dim invalid members",
            self.dim_invalid,
            "Dim members with stale or invalid data.",
        )
        layout.addWidget(markers)
        return self._finish(page, layout)

    def _combat_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        preview = QtWidgets.QLabel("PREVIEW  ·  Work in progress")
        preview.setObjectName("mainNavigationPreview")
        layout.addWidget(preview)

        hud, form = self._group("Compact DPS HUD")

        self.dps_enabled = SettingsToggle()
        self._bind_bool(self.dps_enabled, "map/show_dps_overlay")
        self._add_setting(
            form,
            "Enabled",
            self.dps_enabled,
            "Show the compact DPS overlay.",
        )
        self.dps_visible_rows = QtWidgets.QComboBox()
        for count in DPS_ROW_CHOICES:
            self.dps_visible_rows.addItem(str(count), count)
        self.dps_visible_rows.currentIndexChanged.connect(self._on_dps_rows_changed)
        self._add_setting(
            form,
            "Visible rows",
            self.dps_visible_rows,
            "How many DPS rows to show.",
        )
        self.dps_opacity = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.dps_opacity.setRange(25, 100)
        self.dps_opacity.valueChanged.connect(
            lambda value: self._set_int("combat/dps_opacity", value)
        )
        self._add_setting(
            form,
            "Opacity",
            self.dps_opacity,
            "Overlay transparency.",
        )
        layout.addWidget(hud)

        meter, meter_form = self._group("Full Combat Meter")
        self.combat_refresh = QtWidgets.QComboBox()
        for label, value in COMBAT_REFRESH_CHOICES:
            self.combat_refresh.addItem(label, value)
        self.combat_refresh.currentIndexChanged.connect(self._on_combat_refresh_changed)
        self._add_setting(
            meter_form,
            "Refresh rate",
            self.combat_refresh,
            "How often the meter updates.",
        )
        self.combat_default_view = QtWidgets.QComboBox()
        self.combat_default_view.addItem("Damage", "damage")
        self.combat_default_view.addItem("Healing", "healing")
        self.combat_default_view.currentIndexChanged.connect(
            self._on_combat_default_view_changed
        )
        self._add_setting(
            meter_form,
            "Default view",
            self.combat_default_view,
            "Damage or healing on open.",
        )
        self.combat_compact = SettingsToggle()
        self._bind_bool(self.combat_compact, "combat/compact")
        self._add_setting(
            meter_form,
            "Compact columns",
            self.combat_compact,
            "Tighter meter columns.",
        )
        self.combat_always_on_top = SettingsToggle()
        self._bind_bool(self.combat_always_on_top, "combat/always_on_top")
        self._add_setting(
            meter_form,
            "Always on top",
            self.combat_always_on_top,
            "Keep the meter above other windows.",
        )
        layout.addWidget(meter)

        note = QtWidgets.QLabel(
            "Observed nearby DPS only for now. Skill-level history needs a "
            "richer bridge pipeline."
        )
        note.setWordWrap(True)
        note.setObjectName("settingsDeferredNote")
        layout.addWidget(note)
        return self._finish(page, layout)

    def _alerts_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        proximity, form = self._group("Proximity toasts")

        self.proximity_enabled = SettingsToggle()
        self._bind_bool(self.proximity_enabled, "alerts/proximity_enabled")
        self._add_setting(
            form,
            "Enabled",
            self.proximity_enabled,
            "Show proximity toasts.",
        )
        self.proximity_enemies = SettingsToggle()
        self._bind_bool(self.proximity_enemies, "alerts/proximity_enemies")
        self._add_setting(
            form,
            "Special enemies",
            self.proximity_enemies,
            "Elites and bosses nearby.",
        )
        self.proximity_critters = SettingsToggle()
        self._bind_bool(self.proximity_critters, "alerts/proximity_critters")
        self._add_setting(
            form,
            "Wild critters",
            self.proximity_critters,
            "Critters entering range.",
        )
        self.proximity_duration = QtWidgets.QComboBox()
        for label, value in PROXIMITY_DURATION_CHOICES:
            self.proximity_duration.addItem(label, value)
        self.proximity_duration.currentIndexChanged.connect(
            self._on_proximity_duration_changed
        )
        self._add_setting(
            form,
            "Toast duration",
            self.proximity_duration,
            "How long toasts stay visible.",
        )
        layout.addWidget(proximity)

        note = QtWidgets.QLabel(
            "Uses the same XY/Z cull ranges as Map → Live detection limits. "
            "Target cast warnings need live cast data from the native bridge "
            "and are not available yet."
        )
        note.setWordWrap(True)
        note.setObjectName("settingsDeferredNote")
        layout.addWidget(note)
        return self._finish(page, layout)

    def _on_steam_api_key_changed(self) -> None:
        if self._suppress:
            return
        self._settings.setValue(
            "steam/web_api_key",
            self.steam_web_api_key.text().strip(),
        )
        self._emit_changed()

    def _on_steam_steamid64_changed(self) -> None:
        if self._suppress:
            return
        from .pages.players.steam import normalize_steamid64

        raw = self.steam_steamid64.text().strip()
        normalized = normalize_steamid64(raw) or ""
        if raw and not normalized:
            # Keep typed text visible but don't persist invalid ids.
            return
        if normalized and normalized != raw:
            self.steam_steamid64.setText(normalized)
        self._settings.setValue("steam/steamid64", normalized)
        self._emit_changed()

    def _on_zoom_changed(self, index: int) -> None:
        if self._suppress or not (0 <= index < len(ZOOM_CHOICES)):
            return
        self._set_int("map/zoom_radius", ZOOM_CHOICES[index][1])

    def _on_fog_tier_changed(self, index: int) -> None:
        if self._suppress or not (0 <= index < self.fog_max_tier.count()):
            return
        tier = self.fog_max_tier.itemData(index)
        if tier is None:
            return
        self._settings.setValue("map/fog_max_tier", str(tier))
        self._emit_changed()

    def _on_distance_round_changed(self, index: int) -> None:
        if self._suppress or not (0 <= index < len(DISTANCE_ROUND_CHOICES)):
            return
        self._set_int("party/distance_round_m", DISTANCE_ROUND_CHOICES[index][1])

    def _on_dps_rows_changed(self, index: int) -> None:
        if self._suppress or not (0 <= index < len(DPS_ROW_CHOICES)):
            return
        self._set_int("combat/dps_visible_rows", DPS_ROW_CHOICES[index])

    def _on_combat_refresh_changed(self, index: int) -> None:
        if self._suppress or not (0 <= index < len(COMBAT_REFRESH_CHOICES)):
            return
        self._set_int("combat/refresh_ms", COMBAT_REFRESH_CHOICES[index][1])

    def _on_combat_default_view_changed(self, index: int) -> None:
        if self._suppress or not (0 <= index < self.combat_default_view.count()):
            return
        view = self.combat_default_view.itemData(index)
        if view is None:
            return
        self._settings.setValue("combat/default_view", str(view))
        self._emit_changed()

    def _on_proximity_duration_changed(self, index: int) -> None:
        if self._suppress or not (0 <= index < len(PROXIMITY_DURATION_CHOICES)):
            return
        self._set_int(
            "alerts/proximity_duration_s", PROXIMITY_DURATION_CHOICES[index][1]
        )
