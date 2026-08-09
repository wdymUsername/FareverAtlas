"""Atlas shell window: title bar, context bar, pages, and footer."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ..config import (
    LOOSE_KIND_ICON_FILES,
    ASSET_ROOT,
    discover_project_asset,
    fmt_hp,
    fmt_number,
    safe_float,
    safe_int,
)
from ..controls import FilterChipButton
from ..pages.map.data import MapTexture, Snapshot
from ..pages.map.fog import FOW_TIER_ORDER
from ..pages.map.fow_layers import (
    FOW_LAYER_LABELS,
    FOW_LAYER_ORDER,
    FOW_LAYER_SHORT_LABELS,
)
from ..pages.codex.page import CodexPage, CodexPageMixin
from ..pages.map.page import MapPage, MapPageMixin
from ..pages.map.radar import RadarWidget
from ..pages.map.status import (
    CharacterStatusWidget,
    CurrencyStatusWidget,
    GameTimeStatusWidget,
    PartyMemberStatusWidget,
    RiftStatusWidget,
)
from ..pages.planner.page import PlannerPage, PlannerPageMixin
from ..pages.players.page import PlayersPage, PlayersPageMixin
from ..theme import MAP_WINDOW_STYLESHEET
from ..toast import ToastHost
from ..waypoints import (
    WaypointConfirmOverlay,
    WaypointEditOverlay,
    WaypointManagerOverlay,
    WaypointStore,
)
from ..window_base import PersistentWindow
from .footer import build_footer
from .navigation import MainNavigationOverlay
from .title_bar import TitleBarMixin


class AtlasWindow(
    PersistentWindow,
    TitleBarMixin,
    MapPageMixin,
    PlannerPageMixin,
    CodexPageMixin,
    PlayersPageMixin,
):
    combatMeterRequested = QtCore.Signal()
    onlineModeChanged = QtCore.Signal(bool)
    uiReloadRequested = QtCore.Signal()
    PARTY_SLOT_COUNT = 3

    # (visible radius in metres, displayed zoom multiplier).
    # 200 m is the baseline 1x view; smaller radii zoom in.
    ZOOM_LEVELS = (
        (25, "8x"),
        (50, "4x"),
        (100, "2x"),
        (200, "1x"),
        (300, "0.7x"),
        (450, "0.5x"),
        (650, "0.35x"),
        (900, "0.25x"),
        (1250, "0.2x"),
        (1600, "0.15x"),
        (2000, "0.1x"),
    )

    POI_FILTERS = (
        ("obelisk", "Obelisks"),
        ("respawn", "Respawns"),
        ("dungeon", "Dungeons"),
        ("merchant", "Merchants"),
        ("activity", "Activities"),
    )

    LOOT_FILTERS = (
        ("chest", "Chests"),
        ("red_orb", "Red Orbs"),
        ("plant", "Plants"),
        ("ore", "Ore"),
    )

    def __init__(
        self,
        settings: QtCore.QSettings,
        map_texture: MapTexture | None,
        map_message: str,
        rift_icon_path: Path | None,
        waypoint_store: WaypointStore,
        *,
        dev_mode: bool = False,
    ):
        super().__init__(settings, "map")
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle("Farever Atlas")
        self.resize(620, 680)
        self.setMinimumSize(420, 360)
        self.map_message = map_message
        self.waypoint_store = waypoint_store
        self.dev_mode = bool(dev_mode)
        self.online_mode = self._setting_bool("app/online_mode", True)
        self._init_frameless_chrome()
        saved_active_id = safe_int(
            self._settings.value("map/active_custom_waypoint_id", -1), -1
        )
        self.active_custom_waypoint_id: int | None = (
            saved_active_id
            if saved_active_id > 0 and waypoint_store.get(saved_active_id) is not None
            else None
        )
        self._init_gather_nav_state()
        saved_gather_kind = str(
            self._settings.value("map/gather_nav_kind", "plant") or "plant"
        ).strip().lower()
        if saved_gather_kind in {"plant", "ore", "chest", "red_orb", "pet"}:
            self.gather_nav_kind = saved_gather_kind
        saved_gather_type = str(
            self._settings.value("map/gather_nav_type", "") or ""
        ).strip().lower()
        # Activity chests / stub ore types are excluded from NODE GUIDE.
        if saved_gather_type in {"orbchest", "campchest", "vaultchest", "ironore"}:
            saved_gather_type = ""
        self.gather_nav_type = saved_gather_type
        saved_gather_size = str(
            self._settings.value("map/gather_nav_size", "large") or ""
        ).strip().lower()
        if saved_gather_size in {"", "small", "medium", "large"}:
            self.gather_nav_size = saved_gather_size
        self.waypoint_manager_overlay: WaypointManagerOverlay | None = None
        self.latest_snapshot = Snapshot({}, [], False, "Waiting for bridge output", None)
        self._connection_signature: tuple[object, ...] | None = None
        self._view_mode_signature: tuple[object, ...] | None = None
        self._diagnostic_text: str | None = None
        self._party_status_signature: tuple[object, ...] | None = None
        cached_x = safe_float(self._settings.value("cache/player_x"), math.nan)
        cached_y = safe_float(self._settings.value("cache/player_y"), math.nan)
        self._cached_map_center: tuple[float, float] | None = (
            (cached_x, cached_y)
            if math.isfinite(cached_x) and math.isfinite(cached_y)
            else None
        )


        central = QtWidgets.QWidget()
        central.setObjectName("minimapRoot")
        root_layout = QtWidgets.QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 7)
        root_layout.setSpacing(7)

        self.context_stack = QtWidgets.QStackedWidget()
        self.context_stack.setObjectName("mainContextStack")
        self.context_stack.setFixedHeight(46)

        self.page_stack = QtWidgets.QStackedWidget()
        self.page_stack.setObjectName("mainPageStack")

        self.map_toolbar = QtWidgets.QWidget()
        self.map_toolbar.setObjectName("minimapToolbar")
        self.map_toolbar.setFixedHeight(46)
        toolbar = self.map_toolbar
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(7, 5, 7, 5)
        toolbar_layout.setSpacing(6)

        self.map_body = QtWidgets.QWidget()
        self.map_body.setObjectName("mapPage")
        layout = QtWidgets.QVBoxLayout(self.map_body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        legacy_show_pois = self._setting_bool("map/show_pois", True)
        # Leading chip dots only where the map uses a matching color marker.
        loot_chip_colors = {
            "chest": "#e4b84a",
            "red_orb": "#e35b62",
            "plant": "#63c174",
            "ore": "#aeb6c2",
        }

        self.enemies_filter = FilterChipButton(
            "Enemies", color="#FF5348", marker="diamond"
        )
        self.enemies_filter.setChecked(self._setting_bool("map/show_enemies", True))
        self.show_patrol_paths = self._setting_bool("map/show_patrol_paths", True)
        self.enemies_filter.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.enemies_filter.customContextMenuRequested.connect(
            self._toggle_patrol_paths_mode
        )

        self.critters_filter = FilterChipButton(
            "Critters", color="#6BE06B", marker="diamond"
        )
        self.critters_filter.setChecked(self._setting_bool("map/show_critters", True))
        self.critters_filter.setToolTip(
            "Show or hide companion critters on the map\n"
            "Sparkling critters get a gold halo"
        )

        self.players_filter = FilterChipButton(
            "Players", color="#5AAFE0", marker="dot"
        )
        self.players_filter.setChecked(self._setting_bool("map/show_players", True))
        self.players_filter.setToolTip(
            "Show or hide other players on the map\n"
            "Party members use the same circle in bright blue"
        )
        self.poi_filters: dict[str, FilterChipButton] = {}
        poi_chip_colors = {
            "obelisk": "#9b6fd4",
            "respawn": "#8ec8f5",
            "dungeon": "#5a3480",
            "merchant": "#a67c52",
            "activity": "#5ba6e6",
        }
        for _index, (kind, label) in enumerate(self.POI_FILTERS):
            button = FilterChipButton(label, color=poi_chip_colors.get(kind))
            button.setChecked(
                self._setting_bool(f"map/show_poi_{kind}", legacy_show_pois)
            )
            button.setToolTip(f"Show or hide {label.lower()}")
            self.poi_filters[kind] = button

        legacy_show_collectibles = self._setting_bool("map/show_collectibles", False)
        default_loot_icon_mode = {
            "chest": True,
            "red_orb": True,
            "plant": True,
            "ore": True,
        }
        self.loot_filters: dict[str, FilterChipButton] = {}
        self.loot_icon_modes: dict[str, bool] = {}
        for _index, (kind, label) in enumerate(self.LOOT_FILTERS):
            button = FilterChipButton(label, color=loot_chip_colors.get(kind))
            button.setChecked(
                self._setting_bool(f"map/show_loot_{kind}", legacy_show_collectibles)
            )
            button.setToolTip(f"Show or hide {label.lower()}")
            button.setContextMenuPolicy(
                QtCore.Qt.ContextMenuPolicy.CustomContextMenu
            )
            button.customContextMenuRequested.connect(
                lambda pos, loot_kind=kind: self._toggle_loot_icon_mode(
                    loot_kind, pos
                )
            )
            self.loot_filters[kind] = button
            self.loot_icon_modes[kind] = self._setting_bool(
                f"map/loot_use_icon_{kind}",
                default_loot_icon_mode[kind],
            )

        # CUSTOM contains one live row per custom waypoint. Each row is a
        # visibility toggle; right-clicking it exposes waypoint actions.
        self.custom_waypoint_buttons: dict[int, QtWidgets.QPushButton] = {}

        self.custom_add_current = QtWidgets.QPushButton()
        self.custom_add_current.setText("Add")
        self.custom_add_current.setToolTip(
            "Create a custom waypoint at the player's current position"
        )

        self.custom_manage = QtWidgets.QPushButton()
        self.custom_manage.setText("Manage")
        self.custom_manage.setToolTip(
            f"Open the waypoint manager\n{self.waypoint_store.file_path}"
        )

        self.recenter = QtWidgets.QToolButton()
        self.recenter.setText("")
        self.recenter.setObjectName("centerButton")
        self.recenter.setEnabled(False)
        self.recenter.setVisible(True)
        self.recenter.setToolTip("Return to player-follow mode")
        self.recenter.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.recenter.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.recenter.setFixedSize(28, 28)
        self.recenter.setIconSize(QtCore.QSize(16, 16))
        recenter_icon = QtGui.QIcon(str(ASSET_ROOT / "map_recenter.svg"))
        if not recenter_icon.isNull():
            self.recenter.setIcon(recenter_icon)

        self.character_status = CharacterStatusWidget()
        toolbar_layout.addWidget(
            self.character_status,
            0,
            QtCore.Qt.AlignmentFlag.AlignVCenter,
        )
        self.party_status_container = QtWidgets.QWidget()
        self.party_status_layout = QtWidgets.QHBoxLayout(
            self.party_status_container
        )
        self.party_status_layout.setContentsMargins(0, 0, 0, 0)
        self.party_status_layout.setSpacing(2)
        self.party_status_widgets: dict[str, PartyMemberStatusWidget] = {}
        self.party_status_container.setVisible(False)
        toolbar_layout.addWidget(
            self.party_status_container,
            0,
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )
        toolbar_layout.addStretch(1)

        self.currency_status = CurrencyStatusWidget()
        toolbar_layout.addWidget(
            self.currency_status,
            0,
            QtCore.Qt.AlignmentFlag.AlignVCenter,
        )

        self.rift_status = RiftStatusWidget(rift_icon_path)
        toolbar_layout.addWidget(
            self.rift_status,
            0,
            QtCore.Qt.AlignmentFlag.AlignVCenter,
        )

        saved_radius = safe_int(self._settings.value("map/zoom_radius", 200), 200)
        self.zoom_index = min(
            range(len(self.ZOOM_LEVELS)),
            key=lambda index: abs(self.ZOOM_LEVELS[index][0] - saved_radius),
        )

        self.zoom_in = QtWidgets.QToolButton()
        self.zoom_in.setText("")
        self.zoom_in.setToolTip("Zoom in")
        self.zoom_in.setObjectName("zoomButton")
        self.zoom_in.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoom_in.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.zoom_in.setFixedSize(28, 28)
        self.zoom_in.setIconSize(QtCore.QSize(14, 14))
        zoom_in_icon = QtGui.QIcon(str(ASSET_ROOT / "level_plus.svg"))
        if not zoom_in_icon.isNull():
            self.zoom_in.setIcon(zoom_in_icon)

        self.zoom_out = QtWidgets.QToolButton()
        self.zoom_out.setText("")
        self.zoom_out.setToolTip("Zoom out")
        self.zoom_out.setObjectName("zoomButton")
        self.zoom_out.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoom_out.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.zoom_out.setFixedSize(28, 28)
        self.zoom_out.setIconSize(QtCore.QSize(14, 14))
        zoom_out_icon = QtGui.QIcon(str(ASSET_ROOT / "level_minus.svg"))
        if not zoom_out_icon.isNull():
            self.zoom_out.setIcon(zoom_out_icon)

        self.radar = RadarWidget(map_texture)
        self.radar.setObjectName("minimapCanvas")
        layout.addWidget(self.radar, 1)

        self._init_filter_sidebar()

        # Loot-mode tooltips depend on the radar's loaded icon assets. Refresh
        # them only after the radar has been constructed.
        for kind in self.loot_icon_modes:
            self._update_loot_mode_button(kind)


        self.map_controls_overlay = QtWidgets.QWidget(self.radar)
        self.map_controls_overlay.setObjectName("mapControlsOverlay")
        self.map_controls_overlay.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        map_controls_layout = QtWidgets.QVBoxLayout(self.map_controls_overlay)
        map_controls_layout.setContentsMargins(0, 0, 0, 0)
        map_controls_layout.setSpacing(8)
        map_controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        map_controls_layout.addWidget(
            self.recenter, 0, QtCore.Qt.AlignmentFlag.AlignRight
        )

        self.zoom_panel = QtWidgets.QWidget()
        self.zoom_panel.setObjectName("zoomPanel")
        zoom_panel_layout = QtWidgets.QVBoxLayout(self.zoom_panel)
        zoom_panel_layout.setContentsMargins(0, 0, 0, 0)
        zoom_panel_layout.setSpacing(0)
        zoom_panel_layout.addWidget(self.zoom_in)
        self.zoom_divider = QtWidgets.QFrame()
        self.zoom_divider.setObjectName("zoomDivider")
        self.zoom_divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.zoom_divider.setFixedHeight(1)
        zoom_panel_layout.addWidget(self.zoom_divider)
        zoom_panel_layout.addWidget(self.zoom_out)
        map_controls_layout.addWidget(
            self.zoom_panel, 0, QtCore.Qt.AlignmentFlag.AlignRight
        )

        self.map_controls_overlay.adjustSize()
        self.map_controls_overlay.raise_()

        if self.dev_mode:
            self._init_map_fow_edit_overlay()

        self._build_window_controls()

        self._init_dps_overlay()


        self.radar.installEventFilter(self)

        self._init_planner_page()
        self._init_codex_page()
        self._init_players_page()

        self.pages = {
            MapPage.PAGE_ID: MapPage(self.map_toolbar, self.map_body),
            PlannerPage.PAGE_ID: PlannerPage(self.planner_toolbar, self.planner_body),
            CodexPage.PAGE_ID: CodexPage(self.codex_toolbar, self.codex_body),
            PlayersPage.PAGE_ID: PlayersPage(
                self.players_toolbar, self.players_body
            ),
        }
        self.page_order = (
            MapPage.PAGE_ID,
            PlannerPage.PAGE_ID,
            CodexPage.PAGE_ID,
            PlayersPage.PAGE_ID,
        )

        for page_id in self.page_order:
            page = self.pages[page_id]
            self.context_stack.addWidget(page.context_bar)
            self.page_stack.addWidget(page.body)

        footer = build_footer()
        self.footer = footer
        self.game_time_status = footer.findChild(
            GameTimeStatusWidget, "gameTimeStatus"
        )
        self.connection = footer.findChild(QtWidgets.QLabel, "connectionStatus")
        self.view_mode = footer.findChild(QtWidgets.QLabel, "viewModeStatus")
        self.position = footer.findChild(QtWidgets.QLabel, "positionStatus")
        self.zoom_label = footer.findChild(QtWidgets.QLabel, "zoomValue")
        self.map_help_button = footer.findChild(
            QtWidgets.QToolButton, "mapHelpButton"
        )
        self.help_icon_normal = QtGui.QIcon(str(ASSET_ROOT / "help.svg"))
        self.help_icon_hover = QtGui.QIcon(str(ASSET_ROOT / "help_hover.svg"))
        self.map_help_button.setIcon(self.help_icon_normal)
        self.map_help_button.setIconSize(QtCore.QSize(18, 18))
        self.map_help_button.installEventFilter(self)

        # Compact map-help popup. The button lives in the footer beside coords;
        # the panel floats above it when opened.
        self.map_help_panel = QtWidgets.QFrame(self)
        self.map_help_panel.setObjectName("mapHelpPanel")
        self.map_help_panel.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        self.map_help_panel.setFixedWidth(284)
        help_layout = QtWidgets.QGridLayout(self.map_help_panel)
        help_layout.setContentsMargins(10, 8, 10, 9)
        help_layout.setHorizontalSpacing(11)
        help_layout.setVerticalSpacing(5)

        help_title = QtWidgets.QLabel("MAP CONTROLS")
        help_title.setObjectName("mapHelpTitle")
        help_layout.addWidget(help_title, 0, 0, 1, 2)

        controls: tuple[tuple[str, str], ...] = (
            ("Middle-drag", "Pan map"),
            ("Right-click", "Add or manage custom waypoints"),
            ("Double-click", "Recenter on player"),
            ("Mouse wheel", "Zoom"),
        )
        if self.dev_mode:
            controls = controls + (
                ("Points", "Edit Align-layer vertices"),
                ("Points", "Shift/Ctrl-click multi-select"),
                ("Points", "Drag empty map: marquee select"),
                ("Points", "Drag selection: group move"),
                ("Points", "Delete selection · Esc clears"),
                ("Layer drag", "Move edit layer by dragging the map"),
                ("Layer arrows", "Nudge layer; X±/Y± stretch by step"),
            )
        for row, (gesture, action) in enumerate(controls, start=1):
            gesture_label = QtWidgets.QLabel(gesture)
            gesture_label.setObjectName("mapHelpKey")
            gesture_label.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
            action_label = QtWidgets.QLabel(action)
            action_label.setObjectName("mapHelpAction")
            help_layout.addWidget(gesture_label, row, 0)
            help_layout.addWidget(action_label, row, 1)

        help_layout.setColumnStretch(1, 1)
        self.map_help_panel.adjustSize()
        self.map_help_panel.hide()

        root_layout.addWidget(self.context_stack)
        root_layout.addWidget(self.page_stack, 1)
        root_layout.addWidget(footer)
        self.setCentralWidget(central)

        self.setStyleSheet(MAP_WINDOW_STYLESHEET)
        self._toast_host = ToastHost(self)

        self._init_planner_build_overlay()


        self.waypoint_edit_overlay = WaypointEditOverlay(self)
        self.waypoint_edit_overlay.closeRequested.connect(
            lambda: self._set_waypoint_edit_visible(False)
        )
        self.waypoint_edit_overlay.saved.connect(self._on_waypoint_edit_saved)
        self.waypoint_edit_overlay.hide()

        self.waypoint_confirm_overlay = WaypointConfirmOverlay(self)
        self.waypoint_confirm_overlay.closeRequested.connect(
            self._cancel_waypoint_confirm
        )
        self.waypoint_confirm_overlay.confirmed.connect(self._on_waypoint_confirm)
        self.waypoint_confirm_overlay.hide()

        self.waypoint_manager_overlay = WaypointManagerOverlay(
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
        self.waypoint_manager_overlay.closeRequested.connect(
            lambda: self._set_waypoint_manager_visible(False)
        )
        self.waypoint_manager_overlay.hide()
        self._wire_gather_nav_panel()
        self._position_waypoint_overlays()

        self.main_navigation_overlay = MainNavigationOverlay(
            self, self._settings, dev_mode=self.dev_mode
        )
        self.main_navigation_overlay.closeRequested.connect(
            lambda: self._set_main_navigation_visible(False)
        )
        self.main_navigation_overlay.settingsChanged.connect(
            self._apply_user_settings
        )
        self.main_navigation_overlay.resetWindowsRequested.connect(
            self._reset_window_layouts
        )
        self.main_navigation_overlay.resetOverlaysRequested.connect(
            self._reset_overlay_positions
        )
        self.main_menu_button.clicked.connect(
            lambda: self._set_planner_build_overlay_visible(False)
        )
        self.main_navigation_overlay.hide()
        self.main_navigation_overlay.update_bridge_status(
            self.latest_snapshot, self.map_message
        )
        self._position_main_navigation()

        self.enemies_filter.toggled.connect(self._controls_changed)
        self.critters_filter.toggled.connect(self._controls_changed)
        self.players_filter.toggled.connect(self._controls_changed)
        for button in self.poi_filters.values():
            button.toggled.connect(self._poi_filter_changed)
        for button in self.loot_filters.values():
            button.toggled.connect(self._controls_changed)
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        self.custom_add_current.clicked.connect(self._add_current_custom_waypoint)
        self.custom_manage.clicked.connect(self._open_waypoint_manager)
        self.dps_overlay_open.clicked.connect(self.combatMeterRequested)
        self.dps_overlay_collapse.clicked.connect(
            lambda: self._set_dps_overlay_collapsed(True)
        )
        self.dps_collapsed_button.clicked.connect(
            lambda: self._set_dps_overlay_collapsed(False)
        )
        self.dps_overlay.moved.connect(self._dps_overlay_moved)
        self.zoom_out.clicked.connect(lambda: self._step_zoom(1))
        self.zoom_in.clicked.connect(lambda: self._step_zoom(-1))
        self.recenter.clicked.connect(self._recenter_map)
        if self.dev_mode and hasattr(self, "fog_toggle_button"):
            self.fog_toggle_button.toggled.connect(self._toggle_fog_enabled)
            for tier, btn in self.fog_layer_buttons.items():
                btn.toggled.connect(
                    lambda checked, t=tier: self._toggle_fog_layer(t, checked)
                )
            self.fow_edit_layer_combo.currentIndexChanged.connect(
                self._on_fow_edit_layer_changed
            )
            self.z4_drag_button.toggled.connect(self._toggle_z4_drag_mode)
            self.z4_invert_button.toggled.connect(self._toggle_z4_invert)
            self.z4_move_left.clicked.connect(lambda: self._nudge_z4(-1.0, 0.0))
            self.z4_move_right.clicked.connect(lambda: self._nudge_z4(1.0, 0.0))
            self.z4_move_up.clicked.connect(lambda: self._nudge_z4(0.0, -1.0))
            self.z4_move_down.clicked.connect(lambda: self._nudge_z4(0.0, 1.0))
            self.z4_stretch_x_out.clicked.connect(lambda: self._stretch_z4(sx=1.0))
            self.z4_stretch_x_in.clicked.connect(lambda: self._stretch_z4(sx=-1.0))
            self.z4_stretch_y_out.clicked.connect(lambda: self._stretch_z4(sy=1.0))
            self.z4_stretch_y_in.clicked.connect(lambda: self._stretch_z4(sy=-1.0))
            self.z4_reset_button.clicked.connect(self._reset_z4_transform)
            self.fog_feather_button.toggled.connect(self._toggle_fog_feather)
            self.fow_line_button.toggled.connect(self._toggle_fow_line_tool)
            self.fow_bake_button.clicked.connect(self._bake_fow_edit_layer)
            self.fow_reset_geo_button.clicked.connect(self._reset_fow_edit_geometry)
            self.fow_bake_all_button.clicked.connect(self._bake_all_fow_to_z0)
            self.fow_line_undo_button.clicked.connect(self.radar.fow_line_undo)
            self.fow_line_close_button.clicked.connect(self._close_custom_fow_line)
            self.fow_line_clear_button.clicked.connect(self._clear_custom_fow)
            self.radar.fowLineToolChanged.connect(self._on_fow_line_tool_changed)
            self.radar.fowLineDraftChanged.connect(self._update_fow_line_buttons)
            self.radar.fowLayerDirtyChanged.connect(self._update_fow_line_buttons)
        self.map_help_button.toggled.connect(self._set_map_help_visible)
        self.radar.zoomRequested.connect(self._zoom_requested)
        self.radar.panStateChanged.connect(self._pan_state_changed)
        self.radar.customWaypointContextRequested.connect(
            self._show_custom_waypoint_context_menu
        )
        self.radar.playerContextRequested.connect(self._show_map_player_context_menu)
        self.waypoint_store.changed.connect(self._custom_waypoints_changed)
        initial_radius, _initial_label = self.ZOOM_LEVELS[self.zoom_index]
        self.radar.set_zoom_radius(float(initial_radius), immediate=True)
        self._set_sidebar_filter_segment(
            str(self._settings.value("map/sidebar_filter_segment", "loot") or "loot"),
            persist=False,
        )
        self._set_sidebar_collapsed(
            self._setting_bool("map/sidebar_collapsed", False),
            persist=False,
            animate=False,
        )
        self._set_gather_sidebar_collapsed(
            self._setting_bool("map/gather_sidebar_collapsed", True),
            persist=False,
            animate=False,
        )
        if self.dev_mode and hasattr(self, "_set_fow_tools_collapsed"):
            self._set_fow_tools_collapsed(
                self._setting_bool("map/fow_tools_collapsed", True),
                persist=False,
            )
        self._controls_changed()
        self._custom_waypoints_changed()
        self._apply_user_settings()
        self._set_active_page("map", persist=False)
        # First paint happens before the hub's first poll. Park the map and
        # character strip so waiting/online-without-attach never flashes the
        # broken (0,0) viewport or a letter class icon.
        self.radar.set_offline_mode(True, self._cached_map_center)
        if self.online_mode:
            self.character_status.update_waiting()
        else:
            self.character_status.update_offline()
        if self.game_time_status is not None:
            self.game_time_status.clear()
        self._update_players_page(
            {},
            online=self.online_mode,
            connected=False,
        )
        QtCore.QTimer.singleShot(0, self._position_map_overlays)
        QtCore.QTimer.singleShot(0, self._controls_changed)

    def _set_active_page(self, page: str, *, persist: bool = True) -> None:
        if page not in getattr(self, "pages", {}):
            page = MapPage.PAGE_ID
        previous = getattr(self, "_active_page_id", None)
        if previous in getattr(self, "pages", {}) and previous != page:
            self.pages[previous].on_deactivated()

        map_active = page == MapPage.PAGE_ID
        planner_active = page == PlannerPage.PAGE_ID
        if hasattr(self, "page_stack") and hasattr(self, "context_stack"):
            target = self.pages[page]
            self.context_stack.setCurrentWidget(target.context_bar)
            self.page_stack.setCurrentWidget(target.body)
        if hasattr(self, "map_page_button"):
            self.map_page_button.setChecked(map_active)
            self.planner_page_button.setChecked(planner_active)
            self.codex_page_button.setChecked(page == CodexPage.PAGE_ID)
            self.players_page_button.setChecked(page == PlayersPage.PAGE_ID)
        if hasattr(self, "game_time_status") and self.game_time_status is not None:
            show_time = map_active and self._setting_bool(
                "map/show_game_time", True
            )
            self.game_time_status.setVisible(show_time)
        if hasattr(self, "view_mode") and self.view_mode is not None:
            if not map_active:
                self.view_mode.setVisible(False)
            else:
                self.view_mode.setVisible(bool(self.view_mode.text()))
        if hasattr(self, "position"):
            self.position.setVisible(map_active)
        if hasattr(self, "zoom_label"):
            self.zoom_label.setVisible(map_active)
        if hasattr(self, "map_help_button"):
            self.map_help_button.setVisible(map_active)
        if not planner_active and hasattr(
            self, "planner_build_load_overlay"
        ):
            self._set_planner_build_overlay_visible(False)
        if not map_active:
            if hasattr(self, "map_help_panel"):
                self._set_map_help_visible(False)
            if hasattr(self, "main_navigation_overlay"):
                self._set_main_navigation_visible(False)

        self._active_page_id = page
        self.pages[page].on_activated()
        if persist:
            self._settings.setValue("app/active_page", page)

    def _set_map_help_visible(self, visible: bool) -> None:
        visible = bool(visible)
        self.map_help_panel.setVisible(visible)
        self.map_help_button.setChecked(visible)
        self.map_help_button.setToolTip(
            "Hide map controls" if visible else "Show map controls"
        )
        self._position_map_overlays()
        if visible:
            self.map_help_panel.raise_()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        icon_pair: tuple[QtGui.QIcon, QtGui.QIcon] | None = None
        if watched is getattr(self, "map_help_button", None):
            icon_pair = (self.help_icon_normal, self.help_icon_hover)
        elif watched is getattr(self, "reload_ui_button", None):
            icon_pair = (self.reload_ui_icon_normal, self.reload_ui_icon_hover)
        elif watched is getattr(self, "main_menu_button", None):
            icon_pair = (self.main_menu_icon_normal, self.main_menu_icon_hover)
        elif watched in getattr(self, "_window_button_icon_pairs", {}):
            icon_pair = self._window_button_icon_pairs[watched]
        if icon_pair is not None:
            normal_icon, hover_icon = icon_pair
            if event.type() == QtCore.QEvent.Type.Enter:
                watched.setIcon(hover_icon)
            elif event.type() == QtCore.QEvent.Type.Leave:
                watched.setIcon(normal_icon)
        if watched in (self.app_menu_bar, self.app_title_bar):
            if event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
                mouse_event = event
                if (
                    mouse_event.button() == QtCore.Qt.MouseButton.LeftButton
                    and (
                        watched is self.app_title_bar
                        or self.app_menu_bar.actionAt(
                            mouse_event.position().toPoint()
                        )
                        is None
                    )
                ):
                    self._toggle_maximized()
                    return True
            elif event.type() == QtCore.QEvent.Type.MouseButtonPress:
                mouse_event = event
                if (
                    mouse_event.button() == QtCore.Qt.MouseButton.LeftButton
                    and (
                        watched is self.app_title_bar
                        or self.app_menu_bar.actionAt(
                            mouse_event.position().toPoint()
                        )
                        is None
                    )
                ):
                    handle = self.windowHandle()
                    if handle is not None and handle.startSystemMove():
                        return True
        if watched is getattr(self, "radar", None):
            if event.type() == QtCore.QEvent.Type.Resize:
                QtCore.QTimer.singleShot(0, self._position_map_overlays)
            elif (
                event.type() == QtCore.QEvent.Type.MouseButtonPress
                and self.map_help_panel.isVisible()
            ):
                # A click that reaches the canvas is outside the help UI. Close
                # the panel but allow the requested map interaction to continue.
                self._set_map_help_visible(False)
        return super().eventFilter(watched, event)

    def changeEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        if (
            event.type() == QtCore.QEvent.Type.WindowStateChange
            and hasattr(self, "window_maximize_button")
        ):
            self._sync_maximize_button()
        super().changeEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_resize_grips()
        self._position_title_label()
        self._position_main_navigation()
        self._position_planner_build_overlay()
        self._position_waypoint_overlays()

    def show_toast(
        self,
        message: str,
        *,
        kind: str = "success",
        duration_ms: int = 2800,
    ) -> None:
        if not hasattr(self, "_toast_host"):
            return
        self._toast_host.show_message(
            message,
            kind=kind,
            duration_ms=duration_ms,
        )


    def _position_waypoint_overlays(self) -> None:
        side_margin = 24
        top_margin = self.app_title_bar.height() + 14
        bottom_margin = 18
        available_width = max(0, self.width() - (side_margin * 2))
        available_height = max(0, self.height() - top_margin - bottom_margin)

        if hasattr(self, "waypoint_manager_overlay"):
            manager_width = min(760, available_width)
            manager_height = min(460, available_height)
            self.waypoint_manager_overlay.setGeometry(
                max(side_margin, (self.width() - manager_width) // 2),
                top_margin + max(0, (available_height - manager_height) // 2),
                manager_width,
                manager_height,
            )

        if hasattr(self, "waypoint_edit_overlay"):
            edit_width = min(420, available_width)
            edit_height = min(360, available_height)
            self.waypoint_edit_overlay.setGeometry(
                max(side_margin, (self.width() - edit_width) // 2),
                top_margin + max(0, (available_height - edit_height) // 2),
                edit_width,
                edit_height,
            )

        if hasattr(self, "waypoint_confirm_overlay"):
            confirm_width = min(400, available_width)
            confirm_height = min(180, available_height)
            self.waypoint_confirm_overlay.setGeometry(
                max(side_margin, (self.width() - confirm_width) // 2),
                top_margin + max(0, (available_height - confirm_height) // 2),
                confirm_width,
                confirm_height,
            )

    def _set_waypoint_manager_visible(self, visible: bool) -> None:
        if not hasattr(self, "waypoint_manager_overlay"):
            return
        if visible:
            self._set_main_navigation_visible(False)
            self._set_planner_build_overlay_visible(False)
            self._set_waypoint_edit_visible(False)
            self._set_waypoint_confirm_visible(False)
            self._position_waypoint_overlays()
            self.waypoint_manager_overlay.show_overlay()
        else:
            self.waypoint_manager_overlay.hide()

    def _set_waypoint_edit_visible(self, visible: bool) -> None:
        if not hasattr(self, "waypoint_edit_overlay"):
            return
        if visible:
            self._set_main_navigation_visible(False)
            self._set_planner_build_overlay_visible(False)
            self._set_waypoint_confirm_visible(False)
            self._position_waypoint_overlays()
            self.waypoint_edit_overlay.show()
            self.waypoint_edit_overlay.raise_()
        else:
            self.waypoint_edit_overlay.hide()

    def _set_waypoint_confirm_visible(self, visible: bool) -> None:
        if not hasattr(self, "waypoint_confirm_overlay"):
            return
        if visible:
            self._set_main_navigation_visible(False)
            self._set_planner_build_overlay_visible(False)
            self._position_waypoint_overlays()
            self.waypoint_confirm_overlay.show()
            self.waypoint_confirm_overlay.raise_()
        else:
            self.waypoint_confirm_overlay.hide()

    def _cancel_waypoint_confirm(self) -> None:
        if hasattr(self, "waypoint_confirm_overlay"):
            self.waypoint_confirm_overlay.setProperty("pendingDeleteId", -1)
        manager = getattr(self, "waypoint_manager_overlay", None)
        if manager is not None:
            manager._pending_import_path = None
        self._set_waypoint_confirm_visible(False)

    def _init_map_fow_edit_overlay(self) -> None:
        """Dev-only FOW / zone edit controls (separate from zoom overlay)."""
        icon_path = discover_project_asset("fog.svg") or (ASSET_ROOT / "fog.svg")
        fow_icon = (
            QtGui.QIcon(str(icon_path)) if icon_path.is_file() else QtGui.QIcon()
        )

        # Collapsed: bare FAB on the radar (no panel chrome / margins).
        self.fow_tools_fab = QtWidgets.QToolButton(self.radar)
        self.fow_tools_fab.setObjectName("fowToolsFab")
        self.fow_tools_fab.setToolTip("Open FOW TOOLS")
        self.fow_tools_fab.setFixedSize(28, 28)
        self.fow_tools_fab.setIconSize(QtCore.QSize(16, 16))
        self.fow_tools_fab.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.fow_tools_fab.setAutoRaise(False)
        self.fow_tools_fab.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        if not fow_icon.isNull():
            self.fow_tools_fab.setIcon(fow_icon)
        else:
            self.fow_tools_fab.setText("FOW")
        self.fow_tools_fab.clicked.connect(self._on_fow_tools_fab_clicked)

        # Expanded panel only — never used as the collapsed chrome.
        self.map_fow_edit_overlay = QtWidgets.QWidget(self.radar)
        self.map_fow_edit_overlay.setObjectName("mapFowEditOverlay")
        self.map_fow_edit_overlay.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        layout = QtWidgets.QVBoxLayout(self.map_fow_edit_overlay)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.fow_tools_header = QtWidgets.QWidget()
        self.fow_tools_header.setObjectName("fowToolsHeader")
        header_layout = QtWidgets.QHBoxLayout(self.fow_tools_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.fow_tools_header_icon = QtWidgets.QLabel()
        self.fow_tools_header_icon.setObjectName("fowToolsHeaderIcon")
        self.fow_tools_header_icon.setFixedSize(18, 18)
        self.fow_tools_header_icon.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        if not fow_icon.isNull():
            self.fow_tools_header_icon.setPixmap(
                fow_icon.pixmap(QtCore.QSize(16, 16))
            )
        header_layout.addWidget(
            self.fow_tools_header_icon, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.fow_tools_title = QtWidgets.QLabel("FOW TOOLS")
        self.fow_tools_title.setObjectName("fowToolsTitle")
        self.fow_tools_title.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        header_layout.addWidget(
            self.fow_tools_title, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        header_layout.addStretch(1)

        self.fow_tools_close = QtWidgets.QToolButton()
        self.fow_tools_close.setObjectName("fowToolsCloseButton")
        self.fow_tools_close.setToolTip("Close FOW TOOLS")
        self.fow_tools_close.setFixedSize(22, 22)
        self.fow_tools_close.setIconSize(QtCore.QSize(12, 12))
        self.fow_tools_close.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close_icon = discover_project_asset("close.svg") or (ASSET_ROOT / "close.svg")
        if close_icon.is_file():
            self.fow_tools_close.setIcon(QtGui.QIcon(str(close_icon)))
        else:
            self.fow_tools_close.setText("×")
        header_layout.addWidget(
            self.fow_tools_close, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.fow_tools_header)

        self.fow_tools_body = QtWidgets.QWidget()
        self.fow_tools_body.setObjectName("fowToolsBody")
        body = QtWidgets.QVBoxLayout(self.fow_tools_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)

        def section(title: str) -> QtWidgets.QLabel:
            label = QtWidgets.QLabel(title)
            label.setObjectName("fowEditSection")
            return label

        def tool_button(
            text: str,
            *,
            checkable: bool = False,
            tip: str = "",
        ) -> QtWidgets.QToolButton:
            btn = QtWidgets.QToolButton()
            btn.setObjectName("fowEditButton")
            btn.setFixedHeight(26)
            btn.setText(text)
            btn.setCheckable(checkable)
            if tip:
                btn.setToolTip(tip)
            btn.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            return btn

        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)
        self.fog_toggle_button = tool_button(
            "FOW",
            checkable=True,
            tip="Show or hide fog of war on the map.",
        )
        self.fog_feather_button = tool_button(
            "Feather",
            checkable=True,
            tip="Soft fog edge (~20 m feather).",
        )
        top_row.addWidget(self.fog_toggle_button)
        top_row.addWidget(self.fog_feather_button)
        body.addLayout(top_row)

        body.addWidget(section("ZONES"))
        self.fog_layer_buttons: dict[str, QtWidgets.QToolButton] = {}
        zone_groups = (
            ("Ship", [layer for layer in FOW_LAYER_ORDER if layer == "Baked"]),
            ("Z0", [layer for layer in FOW_LAYER_ORDER if layer == "Z0"]),
            (
                "Z1a",
                [
                    layer
                    for layer in FOW_LAYER_ORDER
                    if layer
                    in (
                        "Z1_Primevalley",
                        "Z1_Honeywoods",
                        "Z1_Meridion",
                    )
                ],
            ),
            (
                "Z1b",
                [
                    layer
                    for layer in FOW_LAYER_ORDER
                    if layer
                    in (
                        "Z1_Enripit",
                        "Z1_Bel_Etir",
                        "Z1_Slime",
                    )
                ],
            ),
            ("Z2", [layer for layer in FOW_LAYER_ORDER if layer.startswith("Z2_")]),
            ("Z3+", [layer for layer in FOW_LAYER_ORDER if layer in ("Z3", "Z4")]),
        )
        for group_title, layers in zone_groups:
            group_row = QtWidgets.QHBoxLayout()
            group_row.setContentsMargins(0, 0, 0, 0)
            group_row.setSpacing(4)
            for tier in layers:
                short = FOW_LAYER_SHORT_LABELS.get(tier, tier)
                label = FOW_LAYER_LABELS.get(tier, tier)
                tip = (
                    f"Toggle {label} FOW layer. "
                    "Custom FOW borders stay additive with zones."
                )
                if tier == "Baked":
                    tip = (
                        "Release FOW clear zone shipped in assets. "
                        "Use Bake all → Baked to refresh it from enabled edit layers."
                    )
                btn = tool_button(
                    short,
                    checkable=True,
                    tip=tip,
                )
                self.fog_layer_buttons[tier] = btn
                group_row.addWidget(btn)
            if group_title in {"Ship", "Z0", "Z3+"}:
                group_row.addStretch(1)
            body.addLayout(group_row)

        self.fow_bake_all_button = tool_button(
            "Bake all → Baked",
            tip=(
                "Merge all enabled zones (current transforms / inverts / overrides) "
                "into the shipping Baked asset, then disable the other zone layers."
            ),
        )
        body.addWidget(self.fow_bake_all_button)

        self.z4_align_container = QtWidgets.QWidget()
        z4_align_layout = QtWidgets.QVBoxLayout(self.z4_align_container)
        z4_align_layout.setContentsMargins(0, 0, 0, 0)
        z4_align_layout.setSpacing(6)

        z4_align_layout.addWidget(section("ALIGN"))
        edit_row = QtWidgets.QHBoxLayout()
        edit_row.setContentsMargins(0, 0, 0, 0)
        edit_row.setSpacing(4)
        self.fow_edit_layer_combo = QtWidgets.QComboBox()
        self.fow_edit_layer_combo.setObjectName("fowEditCombo")
        self.fow_edit_layer_combo.setFixedHeight(26)
        for tier in FOW_LAYER_ORDER:
            self.fow_edit_layer_combo.addItem(
                FOW_LAYER_LABELS.get(tier, tier), tier
            )
        self.fow_edit_layer_combo.setToolTip(
            "Layer targeted by Points / drag / nudge / stretch / invert / Bake"
        )
        self.z4_step_combo = QtWidgets.QComboBox()
        self.z4_step_combo.setObjectName("fowEditCombo")
        self.z4_step_combo.setFixedHeight(26)
        for label, metres in (
            ("1 m", 1.0),
            ("5 m", 5.0),
            ("25 m", 25.0),
            ("100 m", 100.0),
        ):
            self.z4_step_combo.addItem(label, metres)
        self.z4_step_combo.setCurrentIndex(1)
        self.z4_step_combo.setToolTip("Nudge / stretch step size")
        edit_row.addWidget(self.fow_edit_layer_combo, 1)
        edit_row.addWidget(self.z4_step_combo, 1)
        z4_align_layout.addLayout(edit_row)

        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(4)
        self.z4_drag_button = tool_button(
            "Drag",
            checkable=True,
            tip="Drag on the map to move the edit layer",
        )
        self.z4_invert_button = tool_button(
            "Invert",
            checkable=True,
            tip="Invert edit layer: fog that shape (combine with other layers).",
        )
        self.z4_reset_button = tool_button(
            "Reset",
            tip="Reset edit layer move/stretch (transform only)",
        )
        mode_row.addWidget(self.z4_drag_button)
        mode_row.addWidget(self.z4_invert_button)
        mode_row.addWidget(self.z4_reset_button)
        z4_align_layout.addLayout(mode_row)

        points_row = QtWidgets.QHBoxLayout()
        points_row.setContentsMargins(0, 0, 0, 0)
        points_row.setSpacing(4)
        self.fow_line_button = tool_button(
            "Points",
            checkable=True,
            tip=(
                "Edit layer vertices; Shift/marquee multi-select; "
                "group-drag moves selection. Click empty map to draw a new ring."
            ),
        )
        self.fow_bake_button = tool_button(
            "Bake",
            tip="Commit edited rings to stored geometry and clear transform",
        )
        self.fow_reset_geo_button = tool_button(
            "Reset geo",
            tip="Drop override and restore baked asset rings",
        )
        points_row.addWidget(self.fow_line_button)
        points_row.addWidget(self.fow_bake_button)
        points_row.addWidget(self.fow_reset_geo_button)
        z4_align_layout.addLayout(points_row)

        move_row = QtWidgets.QHBoxLayout()
        move_row.setContentsMargins(0, 0, 0, 0)
        move_row.setSpacing(4)
        self.z4_move_left = tool_button("←", tip="Move edit layer west")
        self.z4_move_up = tool_button("↑", tip="Move edit layer north (−Y)")
        self.z4_move_down = tool_button("↓", tip="Move edit layer south (+Y)")
        self.z4_move_right = tool_button("→", tip="Move edit layer east")
        for btn in (
            self.z4_move_left,
            self.z4_move_up,
            self.z4_move_down,
            self.z4_move_right,
        ):
            move_row.addWidget(btn)
        z4_align_layout.addLayout(move_row)

        stretch_row = QtWidgets.QHBoxLayout()
        stretch_row.setContentsMargins(0, 0, 0, 0)
        stretch_row.setSpacing(4)
        self.z4_stretch_x_out = tool_button("X+", tip="Stretch edit layer wider")
        self.z4_stretch_x_in = tool_button("X−", tip="Stretch edit layer narrower")
        self.z4_stretch_y_out = tool_button("Y+", tip="Stretch edit layer taller")
        self.z4_stretch_y_in = tool_button("Y−", tip="Stretch edit layer shorter")
        for btn in (
            self.z4_stretch_x_out,
            self.z4_stretch_x_in,
            self.z4_stretch_y_out,
            self.z4_stretch_y_in,
        ):
            stretch_row.addWidget(btn)
        z4_align_layout.addLayout(stretch_row)

        self.z4_status_label = QtWidgets.QLabel("")
        self.z4_status_label.setObjectName("fowEditStatus")
        self.z4_status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.z4_status_label.setWordWrap(True)
        z4_align_layout.addWidget(self.z4_status_label)

        self.z4_align_container.hide()
        body.addWidget(self.z4_align_container)

        body.addWidget(section("CUSTOM"))
        fow_line_row = QtWidgets.QHBoxLayout()
        fow_line_row.setContentsMargins(0, 0, 0, 0)
        fow_line_row.setSpacing(4)
        self.fow_line_undo_button = tool_button(
            "Undo", tip="Remove last draft vertex while drawing"
        )
        self.fow_line_close_button = tool_button(
            "Close", tip="Close draft polyline into the edit layer"
        )
        self.fow_line_clear_button = tool_button(
            "Clear", tip="Clear all rings on the edit layer"
        )
        for btn in (
            self.fow_line_undo_button,
            self.fow_line_close_button,
            self.fow_line_clear_button,
        ):
            fow_line_row.addWidget(btn)
        body.addLayout(fow_line_row)

        layout.addWidget(self.fow_tools_body)

        self.fow_tools_fab_size = 28
        self.fow_tools_expanded_width = 188
        self.map_fow_edit_overlay.setFixedWidth(self.fow_tools_expanded_width)
        self.map_fow_edit_overlay.adjustSize()
        self.fow_tools_collapsed = True
        self.map_fow_edit_overlay.hide()
        self.fow_tools_fab.show()
        self.fow_tools_fab.raise_()
        self.fow_tools_close.clicked.connect(self._close_fow_tools)

    def _on_fow_tools_fab_clicked(self) -> None:
        if getattr(self, "fow_tools_collapsed", True):
            self._set_fow_tools_collapsed(False)

    def _close_fow_tools(self) -> None:
        if not getattr(self, "fow_tools_collapsed", True):
            self._set_fow_tools_collapsed(True)

    def _set_fow_tools_collapsed(
        self,
        collapsed: bool,
        *,
        persist: bool = True,
    ) -> None:
        if not hasattr(self, "map_fow_edit_overlay") or not hasattr(
            self, "fow_tools_fab"
        ):
            return
        self.fow_tools_collapsed = bool(collapsed)
        if self.fow_tools_collapsed:
            self.fow_tools_fab.show()
            self.fow_tools_fab.raise_()
            self.map_fow_edit_overlay.hide()
        else:
            self.fow_tools_fab.hide()
            self.map_fow_edit_overlay.setFixedWidth(
                int(getattr(self, "fow_tools_expanded_width", 188))
            )
            self.map_fow_edit_overlay.adjustSize()
            self.map_fow_edit_overlay.show()
            self.map_fow_edit_overlay.raise_()
        self._position_map_overlays()
        if persist:
            self._settings.setValue(
                "map/fow_tools_collapsed", self.fow_tools_collapsed
            )

    def _position_map_overlays(self) -> None:
        if not hasattr(self, "map_controls_overlay") or not hasattr(self, "sidebar"):
            return
        margin = 12
        sidebar_margin = margin

        available_sidebar_height = max(
            0, self.radar.height() - (sidebar_margin * 2)
        )
        target_body_height = self._sidebar_target_body_height(sidebar_margin)
        if self.sidebar_animation.state() != QtCore.QAbstractAnimation.State.Running:
            self._set_sidebar_body_height(target_body_height)
        elif self._sidebar_body_height > self._sidebar_body_limit(sidebar_margin):
            # A window resize can reduce the available map height while an
            # expand animation is running. Clamp every frame so the panel
            # always remains inside the canvas.
            self._set_sidebar_body_height(
                self._sidebar_body_limit(sidebar_margin)
            )

        sidebar_height = min(
            available_sidebar_height,
            self._sidebar_chrome_height(self._sidebar_body_height)
            + self._sidebar_body_height,
        )
        self.sidebar.resize(self.sidebar_width, max(0, sidebar_height))
        self.sidebar.move(sidebar_margin, sidebar_margin)
        self.sidebar.raise_()

        if hasattr(self, "gather_sidebar"):
            max_gather_bottom = self.radar.height() - sidebar_margin
            min_gather_top = sidebar_margin + sidebar_height + sidebar_margin
            if getattr(self, "gather_sidebar_collapsed", True) and hasattr(
                self, "gather_fab"
            ):
                fab = self.gather_fab
                fab_size = int(getattr(self, "gather_sidebar_fab_size", 28))
                fab.resize(fab_size, fab_size)
                fab_y = max(
                    min_gather_top,
                    max_gather_bottom - fab_size,
                )
                fab.move(sidebar_margin, fab_y)
                fab.raise_()
            else:
                gather_target = self._gather_sidebar_target_body_height(sidebar_margin)
                if (
                    self.gather_sidebar_animation.state()
                    != QtCore.QAbstractAnimation.State.Running
                ):
                    self._set_gather_sidebar_body_height(gather_target)
                elif self._gather_sidebar_body_height > self._gather_sidebar_body_limit(
                    sidebar_margin
                ):
                    self._set_gather_sidebar_body_height(
                        self._gather_sidebar_body_limit(sidebar_margin)
                    )
                gather_height = (
                    self._gather_sidebar_chrome_height(self._gather_sidebar_body_height)
                    + self._gather_sidebar_body_height
                )
                # Keep gather below waypoints with a gap when the window is short.
                if min_gather_top + gather_height > max_gather_bottom:
                    # Prefer shrinking gather body; header stays visible.
                    allowed_body = max(
                        0,
                        max_gather_bottom
                        - min_gather_top
                        - self._gather_sidebar_chrome_height(1),
                    )
                    if (
                        self.gather_sidebar_animation.state()
                        != QtCore.QAbstractAnimation.State.Running
                    ):
                        self._set_gather_sidebar_body_height(
                            min(self._gather_sidebar_body_height, allowed_body)
                        )
                    gather_height = (
                        self._gather_sidebar_chrome_height(
                            self._gather_sidebar_body_height
                        )
                        + self._gather_sidebar_body_height
                    )
                gather_y = max(
                    min_gather_top,
                    max_gather_bottom - gather_height,
                )
                self.gather_sidebar.resize(
                    self.gather_sidebar_width, max(0, gather_height)
                )
                self.gather_sidebar.move(sidebar_margin, gather_y)
                self.gather_sidebar.raise_()

        self.map_controls_overlay.adjustSize()
        controls_x = max(
            margin,
            self.radar.width() - self.map_controls_overlay.width() - margin,
        )
        controls_y = max(
            margin,
            self.radar.height() - self.map_controls_overlay.height() - margin,
        )
        self.map_controls_overlay.move(controls_x, controls_y)
        self.map_controls_overlay.raise_()

        if hasattr(self, "map_fow_edit_overlay"):
            fow_x = max(
                margin,
                self.radar.width()
                - (
                    int(getattr(self, "fow_tools_fab_size", 28))
                    if getattr(self, "fow_tools_collapsed", True)
                    else self.map_fow_edit_overlay.width()
                )
                - margin,
            )
            if getattr(self, "fow_tools_collapsed", True) and hasattr(
                self, "fow_tools_fab"
            ):
                fab = self.fow_tools_fab
                fab_size = int(getattr(self, "fow_tools_fab_size", 28))
                fab.resize(fab_size, fab_size)
                fab.move(fow_x, margin)
                fab.raise_()
            else:
                self.map_fow_edit_overlay.adjustSize()
                fow_y = margin
                # Keep clear of the zoom overlay if the canvas is short.
                zoom_top = self.map_controls_overlay.y()
                max_bottom = zoom_top - 8
                if fow_y + self.map_fow_edit_overlay.height() > max_bottom:
                    fow_y = max(
                        margin, max_bottom - self.map_fow_edit_overlay.height()
                    )
                fow_x = max(
                    margin,
                    self.radar.width() - self.map_fow_edit_overlay.width() - margin,
                )
                self.map_fow_edit_overlay.move(fow_x, max(margin, fow_y))
                self.map_fow_edit_overlay.raise_()

        if hasattr(self, "map_help_button") and hasattr(self, "map_help_panel"):
            self.map_help_panel.adjustSize()
            button_top_left = self.map_help_button.mapToGlobal(QtCore.QPoint(0, 0))
            anchor = self.mapFromGlobal(button_top_left)
            panel_x = max(
                margin,
                min(
                    anchor.x()
                    + self.map_help_button.width()
                    - self.map_help_panel.width(),
                    self.width() - self.map_help_panel.width() - margin,
                ),
            )
            # Footer button: prefer opening the panel upward.
            above_y = anchor.y() - self.map_help_panel.height() - 3
            below_y = anchor.y() + self.map_help_button.height() + 3
            if above_y >= margin:
                panel_y = above_y
            elif below_y + self.map_help_panel.height() <= self.height() - margin:
                panel_y = below_y
            else:
                panel_y = max(margin, above_y)
            self.map_help_panel.move(panel_x, panel_y)
            if self.map_help_panel.isVisible():
                self.map_help_panel.raise_()

        if hasattr(self, "dps_overlay"):
            self.dps_overlay.adjustSize()
            if not self.dps_overlay.dragging:
                available_x = max(
                    0,
                    self.radar.width()
                    - self.dps_overlay.width()
                    - (margin * 2),
                )
                available_y = max(
                    0,
                    self.radar.height()
                    - self.dps_overlay.height()
                    - (margin * 2),
                )
                if (
                    math.isfinite(self._dps_overlay_x_ratio)
                    and math.isfinite(self._dps_overlay_y_ratio)
                ):
                    dps_x = margin + round(
                        max(0.0, min(1.0, self._dps_overlay_x_ratio))
                        * available_x
                    )
                    dps_y = margin + round(
                        max(0.0, min(1.0, self._dps_overlay_y_ratio))
                        * available_y
                    )
                else:
                    dps_x = max(
                        margin,
                        self.radar.width() - self.dps_overlay.width() - margin,
                    )
                    dps_y = margin
                self.dps_overlay.move(
                    max(margin, min(dps_x, margin + available_x)),
                    max(margin, min(dps_y, margin + available_y)),
                )
            if self.dps_overlay.isVisible():
                self.dps_overlay.raise_()

        if hasattr(self, "dps_collapsed_button"):
            collapsed_x = max(
                margin,
                self.radar.width() - self.dps_collapsed_button.width() - margin,
            )
            self.dps_collapsed_button.move(collapsed_x, margin)
            if self.dps_collapsed_button.isVisible():
                self.dps_collapsed_button.raise_()

    def _setting_bool(self, key: str, default: bool) -> bool:
        value = self._settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _online_mode_toggled(self, online: bool) -> None:
        self.online_mode = online
        self._settings.setValue("app/online_mode", online)
        self.online_switch.setToolTip(
            "Online · live bridge polling enabled"
            if online
            else "Offline · live bridge polling stopped"
        )
        self._sync_online_switch_color()
        self.onlineModeChanged.emit(online)

    def _sync_online_switch_color(self, connection_state: str | None = None) -> None:
        if not self.online_mode:
            self.online_switch.set_status_color("#77838d")
            return
        if connection_state is None:
            message = self.latest_snapshot.message.lower()
            if self.latest_snapshot.connected:
                connection_state = "connected"
            elif "error" in message or "fail" in message:
                connection_state = "failure"
            else:
                connection_state = "waiting"
        colors = {
            "connected": "#4f9b68",
            "waiting": "#b47d35",
            "failure": "#b94f49",
        }
        self.online_switch.set_status_color(colors[connection_state])

    def _cache_connected_player(self, snapshot: Snapshot) -> None:
        if not snapshot.connected or not isinstance(snapshot.state, dict):
            return
        player = snapshot.state.get("player", {})
        if not isinstance(player, dict):
            return
        player_x = safe_float(player.get("x"), math.nan)
        player_y = safe_float(player.get("y"), math.nan)
        if math.isfinite(player_x) and math.isfinite(player_y):
            center = (player_x, player_y)
            if center != self._cached_map_center:
                self._cached_map_center = center
                self._settings.setValue("cache/player_x", player_x)
                self._settings.setValue("cache/player_y", player_y)


    def _step_zoom(self, delta: int) -> None:
        new_index = max(0, min(len(self.ZOOM_LEVELS) - 1, self.zoom_index + delta))
        if new_index == self.zoom_index:
            return
        self.zoom_index = new_index
        self._controls_changed()

    def _zoom_requested(self, direction: int) -> None:
        # Wheel up zooms in, which means a smaller visible radius.
        self._step_zoom(-direction)

    def _recenter_map(self) -> None:
        self.radar.recenter()
        self._players_last_focus_key = None
        if hasattr(self, "_refresh_players_roster"):
            self._refresh_players_roster(force=True)

    def _update_fog_toggle_button(self) -> None:
        if not hasattr(self, "fog_toggle_button"):
            return
        enabled = bool(self.radar.fog.enabled)
        blocked = self.fog_toggle_button.blockSignals(True)
        self.fog_toggle_button.setChecked(enabled)
        self.fog_toggle_button.blockSignals(blocked)
        self.fog_toggle_button.setText("FOW on" if enabled else "FOW off")

    def _toggle_fog_enabled(self, checked: bool) -> None:
        self.radar.fog.enabled = bool(checked)
        self._settings.setValue("map/fog_enabled", self.radar.fog.enabled)
        self._update_fog_toggle_button()
        self.radar.update()

    def _fow_edit_tier(self) -> str:
        data = self.fow_edit_layer_combo.currentData()
        tier = str(data or "Z4")
        return tier if tier in FOW_LAYER_ORDER else "Z4"

    def _set_fow_edit_tier(self, tier: str) -> None:
        tier = str(tier)
        idx = self.fow_edit_layer_combo.findData(tier)
        if idx < 0:
            # Case-insensitive fallback for mixed-case region ids.
            for i in range(self.fow_edit_layer_combo.count()):
                if str(self.fow_edit_layer_combo.itemData(i)).upper() == tier.upper():
                    idx = i
                    break
        if idx < 0:
            return
        blocked = self.fow_edit_layer_combo.blockSignals(True)
        self.fow_edit_layer_combo.setCurrentIndex(idx)
        self.fow_edit_layer_combo.blockSignals(blocked)
        self.radar.set_fow_edit_layer(str(self.fow_edit_layer_combo.itemData(idx)))

    def _on_fow_edit_layer_changed(self, _index: int = 0) -> None:
        tier = self._fow_edit_tier()
        self.radar.set_fow_edit_layer(tier)
        self._update_z4_align_controls()

    def _update_fog_layer_buttons(self) -> None:
        if not hasattr(self, "fog_layer_buttons"):
            return
        for tier, btn in self.fog_layer_buttons.items():
            enabled = self.radar.fog.layer_enabled(tier)
            inverted = self.radar.fog.layer_inverted(tier)
            blocked = btn.blockSignals(True)
            btn.setChecked(enabled)
            btn.blockSignals(blocked)
            btn.setText(FOW_LAYER_SHORT_LABELS.get(tier, tier))
            btn.setProperty("inverted", inverted)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _toggle_fog_layer(self, tier: str, checked: bool) -> None:
        tier = str(tier)
        self.radar.fog.set_layer_enabled(tier, bool(checked))
        key = next(
            (k for k in FOW_LAYER_ORDER if k.upper() == tier.upper()),
            tier,
        )
        self._settings.setValue(
            f"map/fog_layer_{key}", self.radar.fog.layer_enabled(key)
        )
        if not self.radar.fog.any_layer_enabled():
            self.radar.set_z4_drag_mode(False)
        if checked:
            self._set_fow_edit_tier(key)
        self._update_fog_layer_buttons()
        self._update_z4_align_controls()
        self._update_fow_line_buttons()
        self.radar.update()
        if hasattr(self, "map_fow_edit_overlay"):
            self.map_fow_edit_overlay.adjustSize()
        self._position_map_overlays()

    def _z4_step_metres(self) -> float:
        value = self.z4_step_combo.currentData()
        try:
            return max(0.1, float(value))
        except (TypeError, ValueError):
            return 5.0

    def _nudge_z4(self, dx_sign: float, dy_sign: float) -> None:
        tier = self._fow_edit_tier()
        if not self.radar.fog.layer_enabled(tier):
            return
        step = self._z4_step_metres()
        self.radar.fog.nudge_layer(tier, dx_sign * step, dy_sign * step)
        self._update_z4_status_label()
        self.radar.update()

    def _stretch_z4(self, *, sx: float = 0.0, sy: float = 0.0) -> None:
        tier = self._fow_edit_tier()
        if not self.radar.fog.layer_enabled(tier):
            return
        rings = self.radar.fog.transformed_layer_rings(tier)
        xs = [x for ring in rings for x, _y in ring]
        ys = [y for ring in rings for _x, y in ring]
        if not xs or not ys:
            return
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        step = self._z4_step_metres()
        sx_factor = 1.0
        sy_factor = 1.0
        if sx != 0.0 and span_x > 1e-6:
            sx_factor = max(1e-4, (span_x + sx * step) / span_x)
        if sy != 0.0 and span_y > 1e-6:
            sy_factor = max(1e-4, (span_y + sy * step) / span_y)
        self.radar.fog.stretch_layer(tier, sx_factor=sx_factor, sy_factor=sy_factor)
        self._update_z4_status_label()
        self.radar.update()

    def _reset_z4_transform(self) -> None:
        tier = self._fow_edit_tier()
        self.radar.fog.reset_layer_transform(tier)
        self._update_z4_status_label()
        self.radar.update()

    def _toggle_z4_drag_mode(self, checked: bool) -> None:
        if checked and not self.radar.fog.any_layer_enabled():
            blocked = self.z4_drag_button.blockSignals(True)
            self.z4_drag_button.setChecked(False)
            self.z4_drag_button.blockSignals(blocked)
            return
        self.radar.set_fow_edit_layer(self._fow_edit_tier())
        self.radar.set_z4_drag_mode(bool(checked))
        self._update_z4_align_controls()

    def _toggle_z4_invert(self, checked: bool) -> None:
        tier = self._fow_edit_tier()
        self.radar.fog.set_layer_inverted(tier, bool(checked))
        self._settings.setValue(
            f"map/fog_layer_{tier}_invert", self.radar.fog.layer_inverted(tier)
        )
        self._update_fog_layer_buttons()
        self._update_z4_align_controls()
        self.radar.update()

    def _update_z4_align_controls(self) -> None:
        if not hasattr(self, "z4_align_container"):
            return
        any_on = self.radar.fog.any_layer_enabled()
        self.z4_align_container.setVisible(any_on)
        tier = self._fow_edit_tier()
        tier_on = self.radar.fog.layer_enabled(tier)
        blocked = self.z4_drag_button.blockSignals(True)
        self.z4_drag_button.setChecked(self.radar.z4_drag_mode_active and any_on)
        self.z4_drag_button.blockSignals(blocked)
        self.z4_drag_button.setEnabled(any_on and tier_on)
        inv = self.radar.fog.layer_inverted(tier)
        inv_blocked = self.z4_invert_button.blockSignals(True)
        self.z4_invert_button.setChecked(inv)
        self.z4_invert_button.blockSignals(inv_blocked)
        self.z4_invert_button.setEnabled(any_on and tier_on)
        self.z4_invert_button.setText("Invert" if not inv else "Inverted")
        self.fow_edit_layer_combo.setEnabled(any_on)
        points_on = self.radar.fow_line_tool_active
        if hasattr(self, "fow_line_button"):
            self.fow_line_button.setEnabled(any_on and tier_on)
        if hasattr(self, "fow_bake_button"):
            dirty = self.radar.fog.is_layer_dirty(tier)
            self.fow_bake_button.setEnabled(any_on and tier_on and dirty)
        if hasattr(self, "fow_reset_geo_button"):
            self.fow_reset_geo_button.setEnabled(
                any_on
                and tier_on
                and (
                    self.radar.fog.has_layer_override(tier)
                    or self.radar.fog.is_layer_dirty(tier)
                )
            )
        for widget in (
            self.z4_step_combo,
            self.z4_move_left,
            self.z4_move_right,
            self.z4_move_up,
            self.z4_move_down,
            self.z4_stretch_x_out,
            self.z4_stretch_x_in,
            self.z4_stretch_y_out,
            self.z4_stretch_y_in,
            self.z4_reset_button,
        ):
            # Affine tools stay available unless Points is actively editing.
            widget.setEnabled(any_on and tier_on and not points_on)
        self._update_z4_status_label()
        if hasattr(self, "map_fow_edit_overlay"):
            self.map_fow_edit_overlay.adjustSize()
            self._position_map_overlays()

    def _update_z4_status_label(self) -> None:
        if not hasattr(self, "z4_status_label"):
            return
        tier = self._fow_edit_tier()
        label = FOW_LAYER_SHORT_LABELS.get(tier, tier)
        xform = self.radar.fog.layer_transform(tier)
        flags: list[str] = []
        if self.radar.fog.is_layer_dirty(tier):
            flags.append("edited")
        elif self.radar.fog.has_layer_override(tier):
            flags.append("override")
        sel = self.radar.fow_selection_count
        if sel:
            flags.append(f"{sel} selected")
        flag_txt = f" · {', '.join(flags)}" if flags else ""
        self.z4_status_label.setText(
            f"{label}  Δ{xform.tx:+.0f},{xform.ty:+.0f} m{flag_txt}\n"
            f"× {xform.sx:.3f} · {xform.sy:.3f}"
        )

    def _update_fog_feather_button(self) -> None:
        if not hasattr(self, "fog_feather_button"):
            return
        enabled = bool(self.radar.fog.feather_enabled)
        blocked = self.fog_feather_button.blockSignals(True)
        self.fog_feather_button.setChecked(enabled)
        self.fog_feather_button.blockSignals(blocked)
        self.fog_feather_button.setText("Feather" if enabled else "Feather")

    def _toggle_fog_feather(self, checked: bool) -> None:
        self.radar.fog.feather_enabled = bool(checked)
        self._settings.setValue("map/fog_feather", self.radar.fog.feather_enabled)
        self._update_fog_feather_button()
        self.radar.update()

    def _toggle_fow_line_tool(self, checked: bool) -> None:
        self.radar.set_fow_edit_layer(self._fow_edit_tier())
        self.radar.set_fow_line_tool(bool(checked))

    def _on_fow_line_tool_changed(self, active: bool) -> None:
        if not hasattr(self, "fow_line_button"):
            return
        blocked = self.fow_line_button.blockSignals(True)
        self.fow_line_button.setChecked(bool(active))
        self.fow_line_button.blockSignals(blocked)
        self._update_fow_line_buttons()
        self._update_z4_align_controls()

    def _update_fow_line_buttons(self) -> None:
        if not hasattr(self, "fow_line_undo_button"):
            return
        if not hasattr(self, "fow_line_button"):
            return
        draft = self.radar.fow_line_draft_count
        active = self.radar.fow_line_tool_active
        tier = self._fow_edit_tier()
        has_rings = bool(self.radar.fog.source_rings(tier))
        self.fow_line_button.setEnabled(
            self.radar.fog.any_layer_enabled()
            and self.radar.fog.layer_enabled(tier)
        )
        self.fow_line_undo_button.setEnabled(active and draft > 0)
        self.fow_line_close_button.setEnabled(active and draft >= 3)
        self.fow_line_clear_button.setEnabled(active and (has_rings or draft > 0))
        if hasattr(self, "fow_bake_button"):
            self.fow_bake_button.setEnabled(
                self.radar.fog.layer_enabled(tier)
                and self.radar.fog.is_layer_dirty(tier)
            )
        # Closing a new ring may auto-enable the edit layer; sync toggle.
        layer_btn = getattr(self, "fog_layer_buttons", {}).get(tier)
        if layer_btn is not None:
            enabled = self.radar.fog.layer_enabled(tier)
            if layer_btn.isChecked() != enabled:
                blocked = layer_btn.blockSignals(True)
                layer_btn.setChecked(enabled)
                layer_btn.blockSignals(blocked)
                self._settings.setValue(f"map/fog_layer_{tier}", enabled)
                self._update_z4_align_controls()
        self._update_z4_status_label()

    def _close_custom_fow_line(self) -> None:
        closed = self.radar.fow_line_close()
        if not closed:
            return
        tier = self._fow_edit_tier()
        self._settings.setValue(
            f"map/fog_layer_{tier}", self.radar.fog.layer_enabled(tier)
        )
        self._update_fog_layer_buttons()
        self._update_fow_line_buttons()
        self._update_z4_align_controls()
        self.radar.update()

    def _clear_custom_fow(self) -> None:
        tier = self._fow_edit_tier()
        label = FOW_LAYER_LABELS.get(tier, tier)
        if (
            not self.radar.fog.source_rings(tier)
            and self.radar.fow_line_draft_count == 0
        ):
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear layer rings",
            f"Remove all FOW rings on {label}?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.radar.fow_line_clear_custom()
        self._update_fow_line_buttons()
        self.radar.update()

    def _bake_fow_edit_layer(self) -> None:
        self.radar.set_fow_edit_layer(self._fow_edit_tier())
        self.radar.bake_fow_edit_layer()
        self._update_fow_line_buttons()
        self._update_z4_align_controls()

    def _bake_all_fow_to_z0(self) -> None:
        enabled = [
            FOW_LAYER_LABELS.get(tier, tier)
            for tier in FOW_LAYER_ORDER
            if self.radar.fog.layer_enabled(tier)
        ]
        if not enabled:
            QtWidgets.QMessageBox.information(
                self,
                "Bake all zones",
                "Enable at least one FOW layer first.",
            )
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Bake all zones → Baked",
            "Merge currently enabled zones into the shipping Baked asset?\n\n"
            "Uses each layer’s current transform, invert, and overrides.\n"
            "Writes assets/map/w1_siagarta_fow.json and turns other zones off.\n\n"
            f"Enabled: {', '.join(enabled)}",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        if self.radar.fow_line_tool_active:
            self.radar.set_fow_line_tool(False)
        ok, message = self.radar.fog.bake_all_enabled_to_baked()
        if not ok:
            QtWidgets.QMessageBox.warning(self, "Bake all zones", message)
            return
        for tier in FOW_LAYER_ORDER:
            self._settings.setValue(
                f"map/fog_layer_{tier}", self.radar.fog.layer_enabled(tier)
            )
            self._settings.setValue(
                f"map/fog_layer_{tier}_invert",
                self.radar.fog.layer_inverted(tier),
            )
        self._set_fow_edit_tier("Baked")
        self._update_fog_layer_buttons()
        self._update_fow_line_buttons()
        self._update_z4_align_controls()
        self.radar.update()
        if hasattr(self, "map_fow_edit_overlay"):
            self.map_fow_edit_overlay.adjustSize()
            self._position_map_overlays()
        QtWidgets.QMessageBox.information(self, "Bake all zones", message)

    def _reset_fow_edit_geometry(self) -> None:
        tier = self._fow_edit_tier()
        label = FOW_LAYER_LABELS.get(tier, tier)
        reply = QtWidgets.QMessageBox.question(
            self,
            "Reset layer geometry",
            f"Restore baked asset rings for {label}?\n"
            "Stored overrides and unsaved edits will be discarded.",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.radar.set_fow_edit_layer(tier)
        self.radar.reset_fow_edit_geometry()
        self._update_fow_line_buttons()
        self._update_z4_align_controls()
        self.radar.update()

    def _pan_state_changed(self, panned: bool) -> None:
        self.recenter.setEnabled(panned or self.radar.is_following())

    def _apply_user_settings(self) -> None:
        always_on_top = self._setting_bool("app/always_on_top", False)
        if bool(self.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint) != always_on_top:
            was_visible = self.isVisible()
            self.setWindowFlag(
                QtCore.Qt.WindowType.WindowStaysOnTopHint, always_on_top
            )
            if was_visible:
                self.show()

        saved_radius = safe_int(self._settings.value("map/zoom_radius", 200), 200)
        self.zoom_index = min(
            range(len(self.ZOOM_LEVELS)),
            key=lambda index: abs(self.ZOOM_LEVELS[index][0] - saved_radius),
        )

        self.enemies_filter.blockSignals(True)
        self.enemies_filter.setChecked(
            self._setting_bool("map/show_enemies", True)
        )
        self.enemies_filter.blockSignals(False)
        self.critters_filter.blockSignals(True)
        self.critters_filter.setChecked(
            self._setting_bool("map/show_critters", True)
        )
        self.critters_filter.blockSignals(False)
        self.show_patrol_paths = self._setting_bool("map/show_patrol_paths", True)
        self.players_filter.blockSignals(True)
        self.players_filter.setChecked(
            self._setting_bool("map/show_players", True)
        )
        self.players_filter.blockSignals(False)
        for kind, button in self.poi_filters.items():
            button.blockSignals(True)
            button.setChecked(
                self._setting_bool(
                    f"map/show_poi_{kind}",
                    self._setting_bool("map/show_pois", True),
                )
            )
            button.blockSignals(False)
        for kind, button in self.loot_filters.items():
            button.blockSignals(True)
            button.setChecked(
                self._setting_bool(
                    f"map/show_loot_{kind}",
                    self._setting_bool("map/show_collectibles", False),
                )
            )
            button.blockSignals(False)

        dps_enabled = self._setting_bool("map/show_dps_overlay", True)
        if dps_enabled and self.dps_overlay_collapsed:
            self._set_dps_overlay_collapsed(False)
        elif not dps_enabled and not self.dps_overlay_collapsed:
            self._set_dps_overlay_collapsed(True)
        elif not dps_enabled:
            self.dps_overlay.hide()
            self.dps_collapsed_button.hide()

        self.currency_status.setVisible(
            self._setting_bool("map/show_currencies", True)
        )
        map_active = getattr(self, "_active_page_id", None) == MapPage.PAGE_ID
        if self.game_time_status is not None:
            self.game_time_status.setVisible(
                map_active and self._setting_bool("map/show_game_time", True)
            )
        self.rift_status.setVisible(
            self._setting_bool("map/show_rift_timer", True)
        )

        self._party_status_signature = None
        self._controls_changed()
        if isinstance(self.latest_snapshot.state, dict):
            self.update_snapshot(self.latest_snapshot)

    def _reset_window_layouts(self) -> None:
        for key in list(self._settings.allKeys()):
            if key.startswith("windows/") and key.endswith("/geometry"):
                self._settings.remove(key)
        self.resize(1180, 760)
        self._settings.setValue(
            f"windows/{self._settings_key}/geometry", self.saveGeometry()
        )

    def _reset_overlay_positions(self) -> None:
        self._settings.remove("map/dps_overlay_x_ratio")
        self._settings.remove("map/dps_overlay_y_ratio")
        self._dps_overlay_x_ratio = math.nan
        self._dps_overlay_y_ratio = math.nan
        self._position_map_overlays()

    def _controls_changed(self) -> None:
        radius, zoom_label = self.ZOOM_LEVELS[self.zoom_index]
        self.radar.show_texture = self._setting_bool("map/show_texture", True)
        self.radar.show_route_line = self._setting_bool("map/show_route_line", True)
        self.radar.heading_up = False
        self.radar.rounded = False
        self.radar.fog.enabled = self._setting_bool("map/fog_enabled", True)
        self.radar.fog.show_outlines = False
        # Zone / FOW ring borders are --dev edit chrome only.
        self.radar.fog.show_layer_outlines = bool(self.dev_mode)
        self.radar.fog.hide_markers = self._setting_bool("map/fog_hide_markers", True)
        self.radar.fog.feather_enabled = self._setting_bool("map/fog_feather", True)
        fog_tier = str(self._settings.value("map/fog_max_tier", "Z3") or "Z3").upper()
        if fog_tier not in FOW_TIER_ORDER:
            fog_tier = "Z3"
        self.radar.fog.set_max_tier(fog_tier)
        for tier in FOW_LAYER_ORDER:
            key = f"map/fog_layer_{tier}"
            enabled = self._setting_bool(key, tier == "Baked")
            if not self._settings.contains(key):
                if tier == "Baked":
                    enabled = True
                elif tier == "Z0":
                    enabled = False
                elif tier.startswith("Z1_"):
                    enabled = self._setting_bool("map/fog_layer_Z1", False)
                elif tier.startswith("Z2_"):
                    enabled = self._setting_bool("map/fog_layer_Z2", False)
                elif tier == "Z4":
                    enabled = self._setting_bool("map/fog_z4_layer", False)
                else:
                    enabled = False
            # Release builds only ship the Baked clear zone.
            if not self.dev_mode:
                enabled = tier == "Baked"
            self.radar.fog.set_layer_enabled(tier, enabled, persist=False)
            inv_key = f"map/fog_layer_{tier}_invert"
            inverted = self._setting_bool(inv_key, False)
            if not self._settings.contains(inv_key):
                if tier.startswith("Z1_"):
                    inverted = self._setting_bool("map/fog_layer_Z1_invert", False)
                elif tier.startswith("Z2_"):
                    inverted = self._setting_bool("map/fog_layer_Z2_invert", False)
                elif tier == "Z4":
                    inverted = self._setting_bool("map/fog_z4_invert", False)
            if not self.dev_mode:
                inverted = False
            self.radar.fog.set_layer_inverted(tier, inverted, persist=False)
        # Don't clobber --dev layer toggles when running a release session.
        if self.dev_mode:
            self.radar.fog._persist_layers()
        self._update_fog_toggle_button()
        self._update_fog_layer_buttons()
        self._update_z4_align_controls()
        self._update_fog_feather_button()
        self._update_fow_line_buttons()
        poi_visibility = {
            kind: button.isChecked() for kind, button in self.poi_filters.items()
        }
        loot_visibility = {
            kind: button.isChecked() for kind, button in self.loot_filters.items()
        }
        loot_icon_mode = {
            kind: bool(enabled) for kind, enabled in self.loot_icon_modes.items()
        }
        self.radar.poi_kind_visibility = poi_visibility
        self.radar.loot_kind_visibility = loot_visibility
        self.radar.loot_kind_icon_mode = loot_icon_mode
        self.radar.show_party_members = True
        self.radar.show_party_names = self._setting_bool("party/show_names", True)
        self.radar.show_party_health_rings = self._setting_bool(
            "party/show_health_rings", True
        )
        self.radar.dim_invalid_party_members = self._setting_bool(
            "party/dim_invalid", True
        )
        self.radar.show_enemies = self.enemies_filter.isChecked()
        self.radar.show_critters = self.critters_filter.isChecked()
        self.radar.show_patrol_paths = bool(self.show_patrol_paths)
        self.radar.show_players = self.players_filter.isChecked()
        self._update_enemies_filter_tooltip()
        self.radar.show_player_names = self._setting_bool(
            "map/show_player_names", False
        )
        self.radar.show_pois = any(poi_visibility.values())
        visible_custom_waypoints = self._visible_custom_waypoints()
        self.radar.set_custom_waypoints(
            visible_custom_waypoints,
            visible=True,
            active_id=self.active_custom_waypoint_id,
        )
        self.radar.set_zoom_radius(float(radius))
        zoom_tip = (
            f"Scale reference: ±{radius} m across "
            f"{int(self.radar.ZOOM_REFERENCE_HEIGHT_PX)} px height"
        )
        if hasattr(self, "zoom_label") and self.zoom_label is not None:
            self.zoom_label.setText(zoom_label)
            self.zoom_label.setToolTip(zoom_tip)
        self.zoom_in.setToolTip(f"Zoom in\n{zoom_tip}")
        self.zoom_out.setToolTip(f"Zoom out\n{zoom_tip}")
        self.zoom_out.setEnabled(self.zoom_index < len(self.ZOOM_LEVELS) - 1)
        self.zoom_in.setEnabled(self.zoom_index > 0)
        # Keep the legacy aggregate value for downgrade compatibility while
        # persisting each supported marker category independently.
        self._settings.setValue("map/show_pois", any(poi_visibility.values()))
        for kind, enabled in poi_visibility.items():
            self._settings.setValue(f"map/show_poi_{kind}", enabled)
        for kind, enabled in loot_visibility.items():
            self._settings.setValue(f"map/show_loot_{kind}", enabled)
        for kind, use_icon in loot_icon_mode.items():
            self._settings.setValue(f"map/loot_use_icon_{kind}", use_icon)
        self._settings.setValue("map/show_collectibles", any(loot_visibility.values()))
        self._settings.setValue("map/show_enemies", self.radar.show_enemies)
        self._settings.setValue("map/show_critters", self.radar.show_critters)
        self._settings.setValue(
            "map/show_patrol_paths", self.radar.show_patrol_paths
        )
        self._settings.setValue("map/show_players", self.radar.show_players)
        self._settings.setValue("map/fog_enabled", self.radar.fog.enabled)
        self._settings.setValue("map/fog_show_outlines", False)
        self._settings.setValue("map/fog_hide_markers", self.radar.fog.hide_markers)
        self._settings.setValue("map/fog_feather", self.radar.fog.feather_enabled)
        self._settings.setValue("map/fog_max_tier", self.radar.fog.max_tier)
        for tier in FOW_LAYER_ORDER:
            self._settings.setValue(
                f"map/fog_layer_{tier}", self.radar.fog.layer_enabled(tier)
            )
            self._settings.setValue(
                f"map/fog_layer_{tier}_invert",
                self.radar.fog.layer_inverted(tier),
            )
        # Retain the aggregate key only for downgrade compatibility.
        self._settings.setValue(
            "map/show_custom_waypoints", bool(visible_custom_waypoints)
        )
        self._settings.setValue("map/zoom_radius", radius)
        self.radar.update()

    def _update_party_status(self, members: list[dict[str, Any]]) -> None:
        show_distance = self._setting_bool("party/show_distance", True)
        distance_round_m = max(
            1, safe_int(self._settings.value("party/distance_round_m", 1), 1)
        )
        show_empty_slots = self._setting_bool("party/show_empty_slots", True)
        slot_count = self.PARTY_SLOT_COUNT
        empty_opacity = max(
            0.15,
            min(
                1.0,
                safe_int(self._settings.value("party/empty_slot_opacity", 45), 45)
                / 100.0,
            ),
        )

        for key in [
            key for key in self.party_status_widgets if key.startswith("__empty_")
        ]:
            widget = self.party_status_widgets.pop(key)
            self.party_status_layout.removeWidget(widget)
            widget.deleteLater()

        live_keys: set[str] = set()
        for index, member in enumerate(members[:slot_count]):
            key = str(member.get("uid") or member.get("name") or f"member-{index}")
            live_keys.add(key)
            widget = self.party_status_widgets.get(key)
            if widget is None:
                widget = PartyMemberStatusWidget(self.party_status_container)
                self.party_status_widgets[key] = widget
            self.party_status_layout.removeWidget(widget)
            self.party_status_layout.insertWidget(index, widget)
            widget.update_member(
                member,
                show_distance=show_distance,
                distance_round_m=distance_round_m,
            )
            widget.setVisible(True)

        for key in list(self.party_status_widgets):
            if key in live_keys:
                continue
            widget = self.party_status_widgets.pop(key)
            self.party_status_layout.removeWidget(widget)
            widget.deleteLater()

        if show_empty_slots:
            empty_slots = max(0, slot_count - min(len(members), slot_count))
            for empty_index in range(empty_slots):
                key = f"__empty_{empty_index}"
                widget = PartyMemberStatusWidget(self.party_status_container)
                widget.set_placeholder(opacity=empty_opacity)
                self.party_status_widgets[key] = widget
                self.party_status_layout.addWidget(widget)
                widget.show()

        self.party_status_container.setVisible(
            bool(members) or show_empty_slots
        )

    def update_snapshot(self, snapshot: Snapshot) -> None:
        self.latest_snapshot = snapshot
        self._cache_connected_player(snapshot)
        # Online-but-waiting has no live pose yet. Park the map on the last
        # known / calibration center so the texture and waypoints stay aligned
        # instead of collapsing onto the safe_float default (0, 0).
        park_map = (not self.online_mode) or (not snapshot.connected)
        self.radar.set_offline_mode(park_map, self._cached_map_center)
        if (
            self.main_navigation_overlay.isVisible()
            and self.main_navigation_overlay.current_section_index == 5
        ):
            self.main_navigation_overlay.update_bridge_status(
                snapshot, self.map_message
            )
        # Static file POIs always feed the radar: landmarks (obelisk/etc.) and
        # out-of-range loot. Live interactibles overlay loot when in range.
        self.radar.set_snapshot(snapshot)
        self._gather_nav_tick(snapshot)
        self._update_dps_overlay(
            snapshot.state if isinstance(snapshot.state, dict) else {}
        )

        poi_suffix = f" · {len(snapshot.pois)} POIs" if snapshot.pois else ""
        raw_party = (
            snapshot.state.get("party", [])
            if isinstance(snapshot.state, dict)
            else []
        )
        visible_party: list[dict[str, Any]] = []
        if isinstance(raw_party, list):
            player = snapshot.state.get("player", {})
            player_uid = (
                str(player.get("uid") or "") if isinstance(player, dict) else ""
            )
            player_x = (
                safe_float(player.get("x"), math.nan)
                if isinstance(player, dict)
                else math.nan
            )
            player_y = (
                safe_float(player.get("y"), math.nan)
                if isinstance(player, dict)
                else math.nan
            )
            for member in raw_party:
                if not isinstance(member, dict) or not member.get("hero_valid", True):
                    continue
                member_uid = str(member.get("uid") or "")
                if not (player_uid and member_uid == player_uid):
                    display_member = dict(member)
                    member_x = safe_float(member.get("x"), math.nan)
                    member_y = safe_float(member.get("y"), math.nan)
                    if (
                        math.isfinite(player_x)
                        and math.isfinite(player_y)
                        and math.isfinite(member_x)
                        and math.isfinite(member_y)
                    ):
                        display_member["_distance_m"] = math.hypot(
                            member_x - player_x,
                            member_y - player_y,
                        )
                    visible_party.append(display_member)
        party_status_signature = tuple(
            (
                str(member.get("uid") or member.get("name") or ""),
                str(member.get("name") or ""),
                str(member.get("class") or ""),
                (
                    math.floor(
                        safe_float(member.get("_distance_m"), math.nan) + 0.5
                    )
                    if math.isfinite(
                        safe_float(member.get("_distance_m"), math.nan)
                    )
                    else None
                ),
                fmt_hp(member.get("hp")),
                fmt_hp(member.get("max_hp")),
                fmt_hp(member.get("shield")),
                bool(member.get("hero_valid", True)),
            )
            for member in visible_party
        )
        if not self.online_mode:
            self.party_status_container.setVisible(False)
            self._party_status_signature = None
        elif party_status_signature != self._party_status_signature:
            self._party_status_signature = party_status_signature
            self._update_party_status(visible_party)

        self._update_players_page(
            snapshot.state if isinstance(snapshot.state, dict) else {},
            online=self.online_mode,
            connected=bool(snapshot.connected),
        )

        message_lower = snapshot.message.lower()
        if snapshot.connected:
            connection_state = "connected"
        elif "error" in message_lower or "fail" in message_lower:
            connection_state = "failure"
        else:
            connection_state = "waiting"
        if not self.online_mode:
            connection_state = "offline"
        self._sync_online_switch_color(connection_state)
        waiting_seconds = (
            int(snapshot.age)
            if connection_state == "waiting" and snapshot.age is not None
            else None
        )
        connection_signature = (
            connection_state,
            snapshot.message if connection_state == "failure" else "",
            waiting_seconds,
        )
        if connection_signature != self._connection_signature:
            self._connection_signature = connection_signature
            if connection_state == "offline":
                self.connection.setText("● Offline")
            elif connection_state == "connected":
                self.connection.setText("● Connected")
            elif connection_state == "failure":
                self.connection.setText("● Failure")
            else:
                timer = (
                    f" ({waiting_seconds}s)"
                    if waiting_seconds is not None
                    else ""
                )
                self.connection.setText(f"● Waiting{timer}")
            self.connection.setProperty("status", connection_state)
            style = self.connection.style()
            style.unpolish(self.connection)
            style.polish(self.connection)

        following = self.radar.is_following()
        follow_name = self.radar.follow_target_name() if following else ""
        panned = self.radar.is_panned()
        view_signature = (following, follow_name, panned)
        if view_signature != self._view_mode_signature:
            self._view_mode_signature = view_signature
            if following:
                self.view_mode.setText(
                    f"Following {follow_name or 'player'}"
                )
            elif panned:
                self.view_mode.setText("Free view")
            else:
                self.view_mode.setText("")
            map_active = getattr(self, "_active_page_id", None) == MapPage.PAGE_ID
            self.view_mode.setVisible(map_active and bool(self.view_mode.text()))

        player = snapshot.state.get("player", {}) if isinstance(snapshot.state, dict) else {}
        if not isinstance(player, dict):
            player = {}
        player_x = safe_float(player.get("x"), math.nan)
        player_y = safe_float(player.get("y"), math.nan)
        if (
            snapshot.connected
            and math.isfinite(player_x)
            and math.isfinite(player_y)
        ):
            position_text = f"X {player_x:.1f}   Y {player_y:.1f}"
        else:
            position_text = "X —   Y —"
        if self.position.text() != position_text:
            self.position.setText(position_text)

        diagnostic = (
            f"{snapshot.message}{poi_suffix}\n"
            f"{self.map_message}; {self.radar.map_status()}"
        )
        if diagnostic != self._diagnostic_text:
            self._diagnostic_text = diagnostic
            self.connection.setToolTip(diagnostic)
            self.position.setToolTip(diagnostic)
        if self.online_mode and snapshot.connected:
            self.character_status.update_snapshot(snapshot)
            state = snapshot.state if isinstance(snapshot.state, dict) else {}
            self.currency_status.update_from_state(state)
            if self.game_time_status is not None:
                self.game_time_status.update_from_state(state)
        elif self.online_mode:
            self.character_status.update_waiting()
            self.currency_status.clear()
            if self.game_time_status is not None:
                self.game_time_status.clear()
        else:
            self.character_status.update_offline()
            self.currency_status.clear()
            if self.game_time_status is not None:
                self.game_time_status.clear()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        super().closeEvent(event)
