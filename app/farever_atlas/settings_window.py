"""In-window settings pages for Farever Atlas.

General, Map, Party, and the compact DPS enable toggle are live.
Alerts and advanced Combat options stay visible but disabled for later work.
"""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets


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


def apply_settings_defaults(settings: QtCore.QSettings) -> None:
    """Restore the first-slice settings keys to their defaults."""
    settings.setValue("app/always_on_top", False)
    settings.setValue("app/restore_window_positions", True)
    settings.setValue("map/zoom_radius", 200)
    settings.setValue("map/show_texture", True)
    settings.setValue("map/show_route_line", True)
    settings.setValue("map/fog_enabled", True)
    settings.setValue("map/fog_show_outlines", True)
    settings.setValue("map/fog_hide_markers", True)
    settings.setValue("map/fog_max_tier", "Z2")
    for kind, _label in POI_DEFAULT_KINDS:
        settings.setValue(f"map/show_poi_{kind}", True)
    for kind, _label in LOOT_DEFAULT_KINDS:
        settings.setValue(f"map/show_loot_{kind}", False)
    settings.setValue("map/show_pois", True)
    settings.setValue("map/show_collectibles", False)
    settings.setValue("map/show_enemies", True)
    settings.setValue("map/show_players", True)
    settings.setValue("map/show_player_names", False)
    settings.setValue("map/show_dps_overlay", True)
    settings.setValue("party/show_empty_slots", True)
    settings.setValue("party/slot_count", PARTY_SLOT_COUNT)
    settings.setValue("party/show_distance", True)
    settings.setValue("party/distance_round_m", 1)
    settings.setValue("party/empty_slot_opacity", 45)
    settings.setValue("party/show_names", True)
    settings.setValue("party/show_health_rings", True)
    settings.setValue("party/dim_invalid", True)


class SettingsPanel(QtCore.QObject):
    """Builds settings tabs and persists values into QSettings."""

    changed = QtCore.Signal()
    resetWindowsRequested = QtCore.Signal()
    resetOverlaysRequested = QtCore.Signal()

    def __init__(
        self,
        settings: QtCore.QSettings,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._suppress = False
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self._general_tab(), "General")
        self.tabs.addTab(self._map_tab(), "Map")
        self.tabs.addTab(self._party_tab(), "Party")
        self.tabs.addTab(self._combat_tab(), "Combat")
        self.tabs.addTab(self._alerts_tab(), "Alerts")
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
            self.fog_show_outlines.setChecked(
                _as_bool(self._settings.value("map/fog_show_outlines"), True)
            )
            self.fog_hide_markers.setChecked(
                _as_bool(self._settings.value("map/fog_hide_markers"), True)
            )
            fog_tier = str(
                self._settings.value("map/fog_max_tier", "Z2") or "Z2"
            ).upper()
            fog_index = max(0, self.fog_max_tier.findData(fog_tier))
            self.fog_max_tier.setCurrentIndex(fog_index)

            legacy_pois = _as_bool(self._settings.value("map/show_pois"), True)
            for kind, checkbox in self.poi_defaults.items():
                checkbox.setChecked(
                    _as_bool(
                        self._settings.value(f"map/show_poi_{kind}"),
                        legacy_pois,
                    )
                )
            legacy_loot = _as_bool(
                self._settings.value("map/show_collectibles"), False
            )
            for kind, checkbox in self.loot_defaults.items():
                checkbox.setChecked(
                    _as_bool(
                        self._settings.value(f"map/show_loot_{kind}"),
                        legacy_loot,
                    )
                )
            self.show_enemies.setChecked(
                _as_bool(self._settings.value("map/show_enemies"), True)
            )
            self.show_players.setChecked(
                _as_bool(self._settings.value("map/show_players"), True)
            )
            self.show_player_names.setChecked(
                _as_bool(self._settings.value("map/show_player_names"), False)
            )

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

    @staticmethod
    def _page() -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        return page, layout

    @staticmethod
    def _group(title: str) -> tuple[QtWidgets.QGroupBox, QtWidgets.QFormLayout]:
        group = QtWidgets.QGroupBox(title)
        form = QtWidgets.QFormLayout(group)
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        return group, form

    @staticmethod
    def _finish(
        page: QtWidgets.QWidget,
        layout: QtWidgets.QVBoxLayout,
    ) -> QtWidgets.QWidget:
        layout.addStretch(1)
        return page

    def _general_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        behavior, form = self._group("Application behavior")

        self.always_on_top = QtWidgets.QCheckBox()
        self._bind_bool(self.always_on_top, "app/always_on_top")
        form.addRow("Always on top", self.always_on_top)

        single = QtWidgets.QCheckBox()
        single.setChecked(True)
        single.setEnabled(False)
        single.setToolTip("Farever Atlas always uses a single-instance lock")
        form.addRow("Single instance", single)

        self.restore_windows = QtWidgets.QCheckBox()
        self._bind_bool(self.restore_windows, "app/restore_window_positions")
        form.addRow("Restore window positions", self.restore_windows)
        layout.addWidget(behavior)

        steam, steam_form = self._group("Steam")
        self.steam_web_api_key = QtWidgets.QLineEdit()
        self.steam_web_api_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.steam_web_api_key.setPlaceholderText("Web API key (optional)")
        self.steam_web_api_key.setClearButtonEnabled(True)
        self.steam_web_api_key.setToolTip(
            "Used to cache friend Steam avatars and online status.\n"
            "Get a key at https://steamcommunity.com/dev/apikey\n"
            "Private profiles may still show Offline — Atlas labels those Private."
        )
        self.steam_web_api_key.editingFinished.connect(self._on_steam_api_key_changed)
        steam_form.addRow("Web API key", self.steam_web_api_key)
        steam_note = QtWidgets.QLabel(
            "Optional. Friends still work with Here/Away from the game layer. "
            "Private Steam profiles often look Offline — Atlas shows Private instead."
        )
        steam_note.setWordWrap(True)
        steam_note.setObjectName("settingsDeferredNote")
        steam_form.addRow(steam_note)
        layout.addWidget(steam)
        return self._finish(page, layout)

    def _map_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        display, form = self._group("Map display")

        self.default_zoom = QtWidgets.QComboBox()
        for label, _radius in ZOOM_CHOICES:
            self.default_zoom.addItem(label)
        self.default_zoom.currentIndexChanged.connect(self._on_zoom_changed)
        form.addRow("Default zoom", self.default_zoom)

        self.show_texture = QtWidgets.QCheckBox()
        self._bind_bool(self.show_texture, "map/show_texture")
        form.addRow("Show map texture", self.show_texture)

        self.show_route = QtWidgets.QCheckBox()
        self._bind_bool(self.show_route, "map/show_route_line")
        form.addRow("Waypoint route line", self.show_route)
        layout.addWidget(display)

        fog, fog_form = self._group("Fog of war (prototype)")
        self.fog_enabled = QtWidgets.QCheckBox()
        self._bind_bool(self.fog_enabled, "map/fog_enabled")
        fog_form.addRow("Enable fog", self.fog_enabled)

        self.fog_max_tier = QtWidgets.QComboBox()
        self.fog_max_tier.addItem("Z1 Skover only", "Z1")
        self.fog_max_tier.addItem("Z1–Z2 (EA default)", "Z2")
        self.fog_max_tier.addItem("Z1–Z3 + Crimson", "Z3")
        self.fog_max_tier.addItem("All regions", "Z4")
        saved_tier = str(self._settings.value("map/fog_max_tier", "Z2") or "Z2").upper()
        tier_index = max(0, self.fog_max_tier.findData(saved_tier))
        self.fog_max_tier.setCurrentIndex(tier_index)
        self.fog_max_tier.currentIndexChanged.connect(self._on_fog_tier_changed)
        fog_form.addRow("Accessible through", self.fog_max_tier)

        self.fog_show_outlines = QtWidgets.QCheckBox()
        self._bind_bool(self.fog_show_outlines, "map/fog_show_outlines")
        fog_form.addRow("Region outlines", self.fog_show_outlines)

        self.fog_hide_markers = QtWidgets.QCheckBox()
        self._bind_bool(self.fog_hide_markers, "map/fog_hide_markers")
        fog_form.addRow("Hide markers under fog", self.fog_hide_markers)
        layout.addWidget(fog)

        defaults, default_form = self._group("Default visibility")
        self.poi_defaults: dict[str, QtWidgets.QCheckBox] = {}
        for kind, label in POI_DEFAULT_KINDS:
            checkbox = QtWidgets.QCheckBox()
            self.poi_defaults[kind] = checkbox
            self._bind_bool(checkbox, f"map/show_poi_{kind}")
            default_form.addRow(label, checkbox)

        self.loot_defaults: dict[str, QtWidgets.QCheckBox] = {}
        for kind, label in LOOT_DEFAULT_KINDS:
            checkbox = QtWidgets.QCheckBox()
            self.loot_defaults[kind] = checkbox
            self._bind_bool(checkbox, f"map/show_loot_{kind}")
            default_form.addRow(label, checkbox)

        self.show_enemies = QtWidgets.QCheckBox()
        self._bind_bool(self.show_enemies, "map/show_enemies")
        default_form.addRow("Nearby enemies", self.show_enemies)
        self.show_players = QtWidgets.QCheckBox()
        self._bind_bool(self.show_players, "map/show_players")
        default_form.addRow("Nearby players", self.show_players)
        self.show_player_names = QtWidgets.QCheckBox()
        self._bind_bool(self.show_player_names, "map/show_player_names")
        default_form.addRow("Player names", self.show_player_names)
        layout.addWidget(defaults)
        return self._finish(page, layout)

    def _party_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        cards, form = self._group("Party cards")

        self.show_empty_slots = QtWidgets.QCheckBox()
        self._bind_bool(self.show_empty_slots, "party/show_empty_slots")
        form.addRow("Show empty slots", self.show_empty_slots)

        self.show_distance = QtWidgets.QCheckBox()
        self._bind_bool(self.show_distance, "party/show_distance")
        form.addRow("Show distance", self.show_distance)

        self.distance_rounding = QtWidgets.QComboBox()
        for label, _value in DISTANCE_ROUND_CHOICES:
            self.distance_rounding.addItem(label)
        self.distance_rounding.currentIndexChanged.connect(
            self._on_distance_round_changed
        )
        form.addRow("Distance rounding", self.distance_rounding)

        self.empty_opacity = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.empty_opacity.setRange(25, 100)
        self.empty_opacity.valueChanged.connect(
            lambda value: self._set_int("party/empty_slot_opacity", value)
        )
        form.addRow("Empty-slot opacity", self.empty_opacity)
        layout.addWidget(cards)

        markers, marker_form = self._group("Map markers")
        self.show_party_names = QtWidgets.QCheckBox()
        self._bind_bool(self.show_party_names, "party/show_names")
        marker_form.addRow("Show names", self.show_party_names)

        self.show_health_rings = QtWidgets.QCheckBox()
        self._bind_bool(self.show_health_rings, "party/show_health_rings")
        marker_form.addRow("Health rings", self.show_health_rings)

        self.dim_invalid = QtWidgets.QCheckBox()
        self._bind_bool(self.dim_invalid, "party/dim_invalid")
        marker_form.addRow("Dim invalid members", self.dim_invalid)
        layout.addWidget(markers)
        return self._finish(page, layout)

    def _combat_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        hud, form = self._group("Compact DPS HUD")

        self.dps_enabled = QtWidgets.QCheckBox()
        self._bind_bool(self.dps_enabled, "map/show_dps_overlay")
        form.addRow("Enabled", self.dps_enabled)

        for label, widget in (
            (
                "Auto behavior",
                self._disabled_combo(
                    "Always visible", "Combat only", "Auto-collapse"
                ),
            ),
            ("Scale", self._disabled_slider(100)),
            ("Opacity", self._disabled_slider(85)),
            (
                "Visible rows",
                self._disabled_combo("3", "1", "2", "4", "5"),
            ),
            ("Default view", self._disabled_combo("Damage", "Healing")),
        ):
            form.addRow(label, widget)
        layout.addWidget(hud)

        meter, meter_form = self._group("Full Combat Meter")
        for label, widget in (
            ("Refresh rate", self._disabled_combo("2 FPS", "4 FPS", "1 FPS")),
            (
                "Encounter history",
                self._disabled_combo("5", "10", "20", "Off"),
            ),
            (
                "Auto reset",
                self._disabled_combo("New fight ID", "Manual", "After combat"),
            ),
        ):
            meter_form.addRow(label, widget)
        layout.addWidget(meter)

        note = QtWidgets.QLabel(
            "Advanced combat options will return after the DPS pipeline rework."
        )
        note.setWordWrap(True)
        note.setObjectName("settingsDeferredNote")
        layout.addWidget(note)
        return self._finish(page, layout)

    def _alerts_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        casting, form = self._group("Target cast warnings")
        for label, widget in (
            ("Enabled", self._disabled_checkbox(True)),
            ("Warning sound", self._disabled_checkbox(True)),
            ("Toast notification", self._disabled_checkbox(True)),
            (
                "Minimum cast duration",
                self._disabled_combo("0.5 s", "1.0 s", "2.0 s"),
            ),
        ):
            form.addRow(label, widget)
        configure = QtWidgets.QPushButton("Configure…")
        configure.setEnabled(False)
        configure.setToolTip("Requires the upcoming alerts pipeline")
        form.addRow("Per-skill overrides", configure)
        layout.addWidget(casting)

        note = QtWidgets.QLabel(
            "Alerts need live cast data from the native bridge and are not "
            "available yet."
        )
        note.setWordWrap(True)
        note.setObjectName("settingsDeferredNote")
        layout.addWidget(note)
        return self._finish(page, layout)

    @staticmethod
    def _disabled_checkbox(checked: bool = False) -> QtWidgets.QCheckBox:
        checkbox = QtWidgets.QCheckBox()
        checkbox.setChecked(checked)
        checkbox.setEnabled(False)
        checkbox.setToolTip("Not available yet")
        return checkbox

    @staticmethod
    def _disabled_combo(*items: str) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        combo.addItems(items)
        combo.setEnabled(False)
        combo.setToolTip("Not available yet")
        return combo

    @staticmethod
    def _disabled_slider(value: int) -> QtWidgets.QSlider:
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(25, 150)
        slider.setValue(value)
        slider.setEnabled(False)
        slider.setToolTip("Not available yet")
        return slider

    def _on_steam_api_key_changed(self) -> None:
        if self._suppress:
            return
        self._settings.setValue(
            "steam/web_api_key",
            self.steam_web_api_key.text().strip(),
        )
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
