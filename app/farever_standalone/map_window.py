"""Primary standalone minimap window and its UI orchestration."""

from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .config import (
    LOOSE_KIND_ICON_FILES,
    PROJECT_ROOT,
    fmt_hp,
    fmt_number,
    safe_float,
    safe_int,
)
from .controls import (
    LootFilterButton,
    SidebarHeaderButton,
    SlideSwitch,
)
from .map_custom_waypoints import CustomWaypointMixin
from .map_data import MapTexture, Snapshot
from .map_dps_overlay import DpsOverlayMixin
from .map_filter_sidebar import FilterSidebarMixin
from .map_window_chrome import MapWindowChromeMixin
from .navigation_overlay import MainNavigationOverlay
from .radar import RadarWidget
from .theme import MAP_WINDOW_STYLESHEET
from .toolbar import CharacterStatusWidget, PartyMemberStatusWidget, RiftStatusWidget
from .waypoints import WaypointStore
from .window_base import PersistentWindow


class MapWindow(
    PersistentWindow,
    MapWindowChromeMixin,
    FilterSidebarMixin,
    CustomWaypointMixin,
    DpsOverlayMixin,
):
    combatMeterRequested = QtCore.Signal()
    onlineModeChanged = QtCore.Signal(bool)
    PARTY_SLOT_COUNT = 3

    # (visible radius in metres, displayed zoom multiplier).
    # 200 m is the baseline 1x view; smaller radii zoom in.
    ZOOM_LEVELS = (
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
    ):
        super().__init__(settings, "map")
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle("Farever Minimap")
        self.resize(620, 680)
        self.setMinimumSize(420, 360)
        self.map_message = map_message
        self.waypoint_store = waypoint_store
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
        self.waypoint_manager: WaypointManagerDialog | None = None
        self.latest_snapshot = Snapshot({}, [], False, "Waiting for bridge output", None)
        self._connection_signature: tuple[object, ...] | None = None
        self._diagnostic_text: str | None = None
        self._party_status_signature: tuple[object, ...] | None = None
        self._cached_player_profile: dict[str, object] = {
            "name": str(self._settings.value("cache/player_name", "Unknown")),
            "class": str(self._settings.value("cache/player_class", "Unknown")),
            "level": safe_int(self._settings.value("cache/player_level", 0), 0),
        }
        cached_x = safe_float(self._settings.value("cache/player_x"), math.nan)
        cached_y = safe_float(self._settings.value("cache/player_y"), math.nan)
        self._cached_map_center: tuple[float, float] | None = (
            (cached_x, cached_y)
            if math.isfinite(cached_x) and math.isfinite(cached_y)
            else None
        )


        central = QtWidgets.QWidget()
        central.setObjectName("minimapRoot")
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 7)
        layout.setSpacing(7)

        toolbar = QtWidgets.QWidget()
        toolbar.setObjectName("minimapToolbar")
        toolbar.setFixedHeight(46)
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(7, 5, 7, 5)
        toolbar_layout.setSpacing(6)

        legacy_show_pois = self._setting_bool("map/show_pois", True)

        self.poi_section_toggle = SidebarHeaderButton("POI", "sidebarSectionButton")
        self.poi_section_toggle.setToolTip("Hide POI filters")
        self.poi_section_toggle.setFixedHeight(27)
        self.poi_section_toggle.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.loot_section_toggle = SidebarHeaderButton("LOOT", "sidebarSectionButton")
        self.loot_section_toggle.setToolTip("Hide loot filters")
        self.loot_section_toggle.setFixedHeight(27)
        self.loot_section_toggle.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.custom_section_toggle = SidebarHeaderButton("CUSTOM", "sidebarSectionButton")
        self.custom_section_toggle.setToolTip("Hide custom waypoint filters")
        self.custom_section_toggle.setFixedHeight(27)
        self.custom_section_toggle.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.poi_filters: dict[str, QtWidgets.QPushButton] = {}
        for _index, (kind, label) in enumerate(self.POI_FILTERS):
            button = QtWidgets.QPushButton()
            button.setText(label)
            button.setCheckable(True)
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
        self.loot_filters: dict[str, LootFilterButton] = {}
        self.loot_icon_modes: dict[str, SlideSwitch] = {}
        for _index, (kind, label) in enumerate(self.LOOT_FILTERS):
            button = LootFilterButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(
                self._setting_bool(f"map/show_loot_{kind}", legacy_show_collectibles)
            )
            button.setToolTip(f"Show or hide {label.lower()}")
            self.loot_filters[kind] = button

            mode_button = button.mode_switch
            mode_button.setChecked(
                self._setting_bool(
                    f"map/loot_use_icon_{kind}",
                    default_loot_icon_mode[kind],
                )
            )
            mode_button.sync_position()
            mode_button.setAccessibleDescription(
                f"Switch {label.lower()} between colored-dot and atlas-icon rendering"
            )
            self.loot_icon_modes[kind] = mode_button

        # CUSTOM contains one live row per standalone waypoint. Each row is a
        # visibility toggle; right-clicking it exposes waypoint actions.
        self.custom_waypoint_buttons: dict[int, QtWidgets.QPushButton] = {}

        self.custom_add_current = QtWidgets.QPushButton()
        self.custom_add_current.setText("Add Current Position")
        self.custom_add_current.setToolTip(
            "Create a custom waypoint at the player's current position"
        )

        self.custom_manage = QtWidgets.QPushButton()
        self.custom_manage.setText("Manage Waypoints")
        self.custom_manage.setToolTip(
            f"Open the standalone waypoint manager\n{self.waypoint_store.file_path}"
        )

        self.recenter = QtWidgets.QToolButton()
        self.recenter.setText("Recenter")
        self.recenter.setEnabled(False)
        self.recenter.setVisible(True)
        self.recenter.setToolTip("Return to player-follow mode")

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

        self.rift_status = RiftStatusWidget(rift_icon_path)
        toolbar_layout.addWidget(
            self.rift_status,
            0,
            QtCore.Qt.AlignmentFlag.AlignVCenter,
        )

        self.zoom_out = QtWidgets.QToolButton()
        self.zoom_out.setText("−")
        self.zoom_out.setToolTip("Zoom out")
        self.zoom_out.setObjectName("zoomButton")

        saved_radius = safe_int(self._settings.value("map/zoom_radius", 200), 200)
        self.zoom_index = min(
            range(len(self.ZOOM_LEVELS)),
            key=lambda index: abs(self.ZOOM_LEVELS[index][0] - saved_radius),
        )

        self.zoom_in = QtWidgets.QToolButton()
        self.zoom_in.setText("+")
        self.zoom_in.setToolTip("Zoom in")
        self.zoom_in.setObjectName("zoomButton")

        self.zoom_label = QtWidgets.QLabel()
        self.zoom_label.setObjectName("zoomValue")
        self.zoom_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setFixedWidth(54)

        # Match the recenter row to the exact width of the zoom row:
        # 28 + 54 + 28 pixels, plus two 2-pixel gaps. This prevents the
        # floating panel from widening when Recenter becomes visible.
        self.map_control_inner_width = 114
        self.recenter.setFixedHeight(26)
        self.recenter.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        layout.addWidget(toolbar)

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
        map_controls_layout.setContentsMargins(5, 4, 5, 4)
        map_controls_layout.setSpacing(3)

        self.recenter_container = QtWidgets.QWidget()
        self.recenter_container.setObjectName("recenterContainer")
        self.recenter_container.setMinimumHeight(0)
        self.recenter_container.setMaximumHeight(0)
        recenter_layout = QtWidgets.QVBoxLayout(self.recenter_container)
        recenter_layout.setContentsMargins(0, 0, 0, 0)
        recenter_layout.setSpacing(0)
        self.recenter.setObjectName("centerButton")
        recenter_layout.addWidget(self.recenter)
        map_controls_layout.addWidget(self.recenter_container)

        self.recenter_animation = QtCore.QPropertyAnimation(
            self.recenter_container, b"maximumHeight", self
        )
        self.recenter_animation.setDuration(160)
        self.recenter_animation.valueChanged.connect(self._overlay_animation_step)

        zoom_row = QtWidgets.QHBoxLayout()
        zoom_row.setContentsMargins(0, 0, 0, 0)
        zoom_row.setSpacing(2)
        zoom_row.addWidget(self.zoom_out)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addWidget(self.zoom_in)
        map_controls_layout.addLayout(zoom_row)
        self.map_controls_overlay.setFixedWidth(self.map_control_inner_width + 10)
        self.map_controls_overlay.adjustSize()
        self.map_controls_overlay.raise_()

        # Compact map-help control. The old canvas-wide tooltip was intrusive and
        # obscured the map, so controls are now shown explicitly on demand.
        self.map_help_button = QtWidgets.QToolButton(self.radar)
        self.map_help_button.setObjectName("mapHelpButton")
        self.map_help_button.setText("")
        self.help_icon_normal = QtGui.QIcon(
            str(PROJECT_ROOT / "assets" / "help.svg")
        )
        self.help_icon_hover = QtGui.QIcon(
            str(PROJECT_ROOT / "assets" / "help_hover.svg")
        )
        self.map_help_button.setIcon(self.help_icon_normal)
        self.map_help_button.setIconSize(QtCore.QSize(18, 18))
        self.map_help_button.setCheckable(True)
        self.map_help_button.setFixedSize(19, 21)
        self.map_help_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.map_help_button.setToolTip("Show map controls")
        self.map_help_button.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        self.map_help_button.installEventFilter(self)
        self._build_window_controls()

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

        controls = (
            ("Drag", "Pan map"),
            ("Right-click", "Add or manage custom waypoints"),
            ("Double-click", "Recenter on player"),
            ("Mouse wheel", "Zoom"),
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
        self.map_help_button.raise_()

        self._init_dps_overlay()


        self.radar.installEventFilter(self)

        footer = QtWidgets.QWidget()
        footer.setObjectName("minimapFooter")
        footer_layout = QtWidgets.QHBoxLayout(footer)
        footer_layout.setContentsMargins(5, 0, 5, 0)
        footer_layout.setSpacing(8)

        self.connection = QtWidgets.QLabel("● Waiting for bridge")
        self.connection.setObjectName("connectionStatus")
        self.connection.setProperty("status", "waiting")
        self.connection.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.connection.setToolTip("Waiting for nyx_external_live_state.json")

        self.position = QtWidgets.QLabel("X —   Y —")
        self.position.setObjectName("positionStatus")
        self.position.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        footer_layout.addWidget(self.connection)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.position)
        layout.addWidget(footer)
        self.setCentralWidget(central)

        self.setStyleSheet(MAP_WINDOW_STYLESHEET)
        self.main_navigation_overlay = MainNavigationOverlay(self)
        self.main_navigation_overlay.closeRequested.connect(
            lambda: self._set_main_navigation_visible(False)
        )
        self.main_navigation_overlay.hide()
        self.main_navigation_overlay.update_bridge_status(
            self.latest_snapshot, self.map_message
        )
        self._position_main_navigation()

        for button in self.poi_filters.values():
            button.toggled.connect(self._poi_filter_changed)
        for button in self.loot_filters.values():
            button.toggled.connect(self._controls_changed)
        for kind, button in self.loot_icon_modes.items():
            button.toggled.connect(
                lambda checked, loot_kind=kind: self._loot_icon_mode_changed(
                    loot_kind, checked
                )
            )
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        self.poi_section_toggle.clicked.connect(self._toggle_poi_section)
        self.loot_section_toggle.clicked.connect(self._toggle_loot_section)
        self.custom_section_toggle.clicked.connect(self._toggle_custom_section)
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
        self.recenter.clicked.connect(self.radar.recenter)
        self.map_help_button.toggled.connect(self._set_map_help_visible)
        self.radar.zoomRequested.connect(self._zoom_requested)
        self.radar.panStateChanged.connect(self._pan_state_changed)
        self.radar.customWaypointContextRequested.connect(
            self._show_custom_waypoint_context_menu
        )
        self.waypoint_store.changed.connect(self._custom_waypoints_changed)
        initial_radius, _initial_label = self.ZOOM_LEVELS[self.zoom_index]
        self.radar.set_zoom_radius(float(initial_radius), immediate=True)
        self._set_poi_collapsed(
            self._setting_bool("map/poi_collapsed", False),
            persist=False,
            animate=False,
        )
        self._set_loot_collapsed(
            self._setting_bool("map/loot_collapsed", False),
            persist=False,
            animate=False,
        )
        self._set_custom_collapsed(
            self._setting_bool("map/custom_collapsed", False),
            persist=False,
            animate=False,
        )
        self._set_sidebar_collapsed(
            self._setting_bool("map/sidebar_collapsed", False),
            persist=False,
            animate=False,
        )
        self._controls_changed()
        self._custom_waypoints_changed()
        QtCore.QTimer.singleShot(0, self._position_map_overlays)

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

        self.map_controls_overlay.adjustSize()
        x = max(margin, self.radar.width() - self.map_controls_overlay.width() - margin)
        y = max(margin, self.radar.height() - self.map_controls_overlay.height() - margin)
        self.map_controls_overlay.move(x, y)
        self.map_controls_overlay.raise_()

        if hasattr(self, "map_help_button") and hasattr(self, "map_help_panel"):
            help_x = (
                self.map_controls_overlay.x()
                + self.map_controls_overlay.width()
                - self.map_help_button.width()
            )
            help_y = max(
                margin,
                self.map_controls_overlay.y() - self.map_help_button.height() - 4,
            )
            self.map_help_button.move(help_x, help_y)
            self.map_help_button.raise_()
            self.map_help_panel.adjustSize()
            button_bottom_left = self.map_help_button.mapToGlobal(
                QtCore.QPoint(0, self.map_help_button.height())
            )
            anchor = self.mapFromGlobal(button_bottom_left)
            panel_x = max(
                margin,
                min(
                    anchor.x() + self.map_help_button.width()
                    - self.map_help_panel.width(),
                    self.width() - self.map_help_panel.width() - margin,
                ),
            )
            below_y = anchor.y() + 3
            if below_y + self.map_help_panel.height() <= self.height() - margin:
                panel_y = below_y
            else:
                button_top = self.mapFromGlobal(
                    self.map_help_button.mapToGlobal(QtCore.QPoint(0, 0))
                ).y()
                panel_y = max(
                    margin,
                    button_top - self.map_help_panel.height() - 3,
                )
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
            self.online_switch.set_track_colors("#3b444c", "#3b444c")
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
        self.online_switch.set_track_colors("#3b444c", colors[connection_state])

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
        name = str(player.get("name") or "").strip()
        character_class = str(player.get("class") or "").strip()
        level = safe_int(player.get("level"), 0)
        if not name or not character_class or level <= 0:
            return
        profile = {"name": name, "class": character_class, "level": level}
        if profile == self._cached_player_profile:
            return
        self._cached_player_profile = profile
        self._settings.setValue("cache/player_name", name)
        self._settings.setValue("cache/player_class", character_class)
        self._settings.setValue("cache/player_level", level)


    def _step_zoom(self, delta: int) -> None:
        new_index = max(0, min(len(self.ZOOM_LEVELS) - 1, self.zoom_index + delta))
        if new_index == self.zoom_index:
            return
        self.zoom_index = new_index
        self._controls_changed()

    def _zoom_requested(self, direction: int) -> None:
        # Wheel up zooms in, which means a smaller visible radius.
        self._step_zoom(-direction)

    def _pan_state_changed(self, panned: bool) -> None:
        self.recenter.setEnabled(panned)
        self.recenter_animation.stop()

        current_height = max(0, self.recenter_container.height())
        target_height = 26 if panned else 0
        if current_height == target_height:
            self.recenter_container.setMaximumHeight(target_height)
            self._position_map_overlays()
            return

        self.recenter_animation.setStartValue(current_height)
        self.recenter_animation.setEndValue(target_height)
        self.recenter_animation.setEasingCurve(
            QtCore.QEasingCurve.Type.OutCubic
            if panned
            else QtCore.QEasingCurve.Type.InCubic
        )
        self.recenter_animation.start()

    def _controls_changed(self) -> None:
        radius, zoom_label = self.ZOOM_LEVELS[self.zoom_index]
        self.radar.show_texture = True
        self.radar.heading_up = False
        self.radar.rounded = False
        poi_visibility = {
            kind: button.isChecked() for kind, button in self.poi_filters.items()
        }
        loot_visibility = {
            kind: button.isChecked() for kind, button in self.loot_filters.items()
        }
        loot_icon_mode = {
            kind: button.isChecked() for kind, button in self.loot_icon_modes.items()
        }
        self.radar.poi_kind_visibility = poi_visibility
        self.radar.loot_kind_visibility = loot_visibility
        self.radar.loot_kind_icon_mode = loot_icon_mode
        self.radar.show_party_members = True
        self.radar.show_pois = any(poi_visibility.values())
        visible_custom_waypoints = self._visible_custom_waypoints()
        self.radar.set_custom_waypoints(
            visible_custom_waypoints,
            visible=True,
            active_id=self.active_custom_waypoint_id,
        )
        self.radar.set_zoom_radius(float(radius))
        self.zoom_label.setText(zoom_label)
        self.zoom_label.setToolTip(
            f"Scale reference: ±{radius} m across "
            f"{int(self.radar.ZOOM_REFERENCE_HEIGHT_PX)} px height"
        )
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
        # Retain the aggregate key only for downgrade compatibility.
        self._settings.setValue(
            "map/show_custom_waypoints", bool(visible_custom_waypoints)
        )
        self._settings.setValue("map/zoom_radius", radius)
        self.radar.update()

    def _update_party_status(self, members: list[dict[str, Any]]) -> None:
        for key in [
            key for key in self.party_status_widgets if key.startswith("__empty_")
        ]:
            widget = self.party_status_widgets.pop(key)
            self.party_status_layout.removeWidget(widget)
            widget.deleteLater()

        live_keys: set[str] = set()
        for index, member in enumerate(members):
            key = str(member.get("uid") or member.get("name") or f"member-{index}")
            live_keys.add(key)
            widget = self.party_status_widgets.get(key)
            if widget is None:
                widget = PartyMemberStatusWidget(self.party_status_container)
                self.party_status_widgets[key] = widget
            self.party_status_layout.removeWidget(widget)
            self.party_status_layout.insertWidget(index, widget)
            widget.update_member(member)
            widget.setVisible(True)

        for key in list(self.party_status_widgets):
            if key in live_keys:
                continue
            widget = self.party_status_widgets.pop(key)
            self.party_status_layout.removeWidget(widget)
            widget.deleteLater()

        empty_slots = max(0, self.PARTY_SLOT_COUNT - len(members))
        for empty_index in range(empty_slots):
            key = f"__empty_{empty_index}"
            widget = PartyMemberStatusWidget(self.party_status_container)
            widget.set_placeholder()
            self.party_status_widgets[key] = widget
            self.party_status_layout.addWidget(widget)
            widget.show()

        self.party_status_container.setVisible(True)

    def update_snapshot(self, snapshot: Snapshot) -> None:
        self.latest_snapshot = snapshot
        self._cache_connected_player(snapshot)
        self.radar.set_offline_mode(not self.online_mode, self._cached_map_center)
        if (
            self.main_navigation_overlay.isVisible()
            and self.main_navigation_overlay.current_section_index == 5
        ):
            self.main_navigation_overlay.update_bridge_status(
                snapshot, self.map_message
            )
        self.radar.set_snapshot(snapshot)
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
            self.radar.is_panned(),
            len(snapshot.pois),
        )
        if connection_signature != self._connection_signature:
            self._connection_signature = connection_signature
            if connection_state == "offline":
                self.connection.setText(f"● Offline{poi_suffix}")
            elif connection_state == "connected":
                view_suffix = " · Free view" if self.radar.is_panned() else ""
                self.connection.setText(
                    f"● Connected{view_suffix}{poi_suffix}"
                )
            elif connection_state == "failure":
                detail = html.escape(snapshot.message)
                self.connection.setText(f"● FAILURE · {detail}")
            else:
                timer = (
                    f" ({waiting_seconds}s)"
                    if waiting_seconds is not None
                    else ""
                )
                self.connection.setText(
                    f'● Waiting{timer} &nbsp;'
                    '<span style="color:#4d5963">FOCUS THE GAME WINDOW</span>'
                )
            self.connection.setProperty("status", connection_state)
            style = self.connection.style()
            style.unpolish(self.connection)
            style.polish(self.connection)

        player = snapshot.state.get("player", {}) if isinstance(snapshot.state, dict) else {}
        if not isinstance(player, dict):
            player = {}
        position_text = (
            f"X {safe_float(player.get('x')):.1f}   "
            f"Y {safe_float(player.get('y')):.1f}"
            if player
            else "X —   Y —"
        )
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
        if self.online_mode:
            self.character_status.update_snapshot(snapshot)
        else:
            self.character_status.update_offline(self._cached_player_profile)
