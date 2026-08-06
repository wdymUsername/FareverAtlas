"""Frameless shell title bar, window controls, and resize grips."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..config import ASSET_ROOT
from ..controls import PowerStatusButton
from ..pages.map.widgets import WindowResizeGrip
from .navigation import MainNavigationOverlay


class TitleBarMixin:
    """Shell title bar: page tabs, menus, online switch, and window controls."""

    def _init_frameless_chrome(self) -> None:
        self.app_title_bar = QtWidgets.QWidget()
        self.app_title_bar.setObjectName("fareverTitleBar")
        self.app_title_bar.setFixedHeight(31)
        self.app_title_bar_layout = QtWidgets.QHBoxLayout(self.app_title_bar)
        self.app_title_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.app_title_bar_layout.setSpacing(0)

        self.online_switch = PowerStatusButton(
            str(ASSET_ROOT / "power.svg"),
            self.app_title_bar,
        )
        self.online_switch.setObjectName("onlineModeSwitch")
        self.online_switch.setAccessibleName("Online mode")
        self.online_switch.setAccessibleDescription(
            "Checked enables live bridge polling; unchecked enables Offline Mode"
        )
        self.online_switch.setChecked(self.online_mode)
        self.online_switch.setToolTip(
            "Online · live bridge polling enabled"
            if self.online_mode
            else "Offline · live bridge polling stopped"
        )
        self.app_title_bar_layout.addSpacing(7)
        self.app_title_bar_layout.addWidget(
            self.online_switch, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.app_title_bar_layout.addSpacing(5)
        self.online_switch.toggled.connect(self._online_mode_toggled)

        self.page_button_group = QtWidgets.QButtonGroup(self.app_title_bar)
        self.page_button_group.setExclusive(True)

        self.map_page_button = QtWidgets.QToolButton(self.app_title_bar)
        self.map_page_button.setObjectName("mapPageButton")
        self.map_page_button.setText("Map")
        self.map_page_button.setCheckable(True)
        self.map_page_button.setChecked(True)
        self.map_page_button.setFixedSize(48, 25)
        self.map_page_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.map_page_button.setToolTip("Show the map")

        self.planner_page_button = QtWidgets.QToolButton(self.app_title_bar)
        self.planner_page_button.setObjectName("plannerPageButton")
        self.planner_page_button.setText("Planner")
        self.planner_page_button.setCheckable(True)
        self.planner_page_button.setFixedSize(60, 25)
        self.planner_page_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.planner_page_button.setToolTip("Show the planner")

        self.codex_page_button = QtWidgets.QToolButton(self.app_title_bar)
        self.codex_page_button.setObjectName("codexPageButton")
        self.codex_page_button.setText("Codex")
        self.codex_page_button.setCheckable(True)
        self.codex_page_button.setFixedSize(52, 25)
        self.codex_page_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.codex_page_button.setToolTip("Show the codex")

        self.page_button_group.addButton(self.map_page_button)
        self.page_button_group.addButton(self.planner_page_button)
        self.page_button_group.addButton(self.codex_page_button)
        self.app_title_bar_layout.addWidget(
            self.map_page_button, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.app_title_bar_layout.addWidget(
            self.planner_page_button, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.app_title_bar_layout.addWidget(
            self.codex_page_button, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.app_title_bar_layout.addSpacing(5)
        self.map_page_button.clicked.connect(lambda: self._set_active_page("map"))
        self.planner_page_button.clicked.connect(
            lambda: self._set_active_page("planner")
        )
        self.codex_page_button.clicked.connect(
            lambda: self._set_active_page("codex")
        )

        self.app_menu_bar = QtWidgets.QMenuBar(self.app_title_bar)
        self.app_menu_bar.setNativeMenuBar(False)
        self.app_menu_bar.setObjectName("fareverMenuBar")
        self.app_menu_bar.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.app_title_bar_layout.addWidget(self.app_menu_bar, 1)
        self._build_preview_menu()
        self.setMenuWidget(self.app_title_bar)
        self.app_title_label = QtWidgets.QLabel("Farever Atlas", self.app_title_bar)
        self.app_title_label.setObjectName("fareverTitleLabel")
        self.app_title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.app_title_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.app_title_label.adjustSize()
        self._position_title_label()
        self.app_title_label.raise_()
        self.app_menu_bar.installEventFilter(self)
        self.app_title_bar.installEventFilter(self)
        self._build_resize_grips()

    def _build_preview_menu(self) -> None:
        """Build the button that opens the in-window navigation surface."""
        self.reload_ui_button: QtWidgets.QToolButton | None = None
        if getattr(self, "dev_mode", False):
            self.reload_ui_button = QtWidgets.QToolButton(self.app_title_bar)
            self.reload_ui_button.setObjectName("reloadUiButton")
            self.reload_ui_button.setText("")
            self.reload_ui_icon_normal = QtGui.QIcon(
                str(ASSET_ROOT / "reload.svg")
            )
            self.reload_ui_icon_hover = QtGui.QIcon(
                str(ASSET_ROOT / "reload_hover.svg")
            )
            self.reload_ui_button.setIcon(self.reload_ui_icon_normal)
            self.reload_ui_button.setIconSize(QtCore.QSize(17, 17))
            self.reload_ui_button.setFixedSize(30, 27)
            self.reload_ui_button.setToolTip("Reload UI (dev)")
            self.reload_ui_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            self.reload_ui_button.installEventFilter(self)
            self.reload_ui_button.clicked.connect(self._request_ui_reload)

        self.main_menu_button = QtWidgets.QToolButton(self.app_title_bar)
        self.main_menu_button.setObjectName("mainMenuButton")
        self.main_menu_button.setText("")
        self.main_menu_icon_normal = QtGui.QIcon(
            str(ASSET_ROOT / "settings.svg")
        )
        self.main_menu_icon_hover = QtGui.QIcon(
            str(ASSET_ROOT / "settings_hover.svg")
        )
        self.main_menu_button.setIcon(self.main_menu_icon_normal)
        self.main_menu_button.setIconSize(QtCore.QSize(17, 17))
        self.main_menu_button.setFixedSize(30, 27)
        self.main_menu_button.setToolTip("Settings")
        self.main_menu_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.main_menu_button.installEventFilter(self)
        self.main_menu_button.clicked.connect(self._toggle_main_navigation)

    def _request_ui_reload(self) -> None:
        button = getattr(self, "reload_ui_button", None)
        if button is not None:
            button.setEnabled(False)
            button.setToolTip("Reloading…")
        self.uiReloadRequested.emit()

    def _build_window_controls(self) -> None:
        controls = QtWidgets.QWidget()
        controls.setObjectName("windowControls")
        controls_layout = QtWidgets.QHBoxLayout(controls)
        controls_layout.setContentsMargins(2, 0, 0, 0)
        controls_layout.setSpacing(0)

        if self.reload_ui_button is not None:
            controls_layout.addWidget(self.reload_ui_button)
        controls_layout.addWidget(self.main_menu_button)
        controls_layout.addSpacing(8)

        separator = QtWidgets.QFrame()
        separator.setObjectName("windowControlsSeparator")
        separator.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        separator.setFixedSize(1, 11)
        controls_layout.addWidget(separator)
        controls_layout.addSpacing(2)

        self.window_minimize_button = QtWidgets.QToolButton()
        self.window_minimize_button.setObjectName("windowMinimizeButton")
        self.window_minimize_button.setText("")
        self.window_minimize_button.setToolTip("Minimize")

        self.window_maximize_button = QtWidgets.QToolButton()
        self.window_maximize_button.setObjectName("windowMaximizeButton")
        self.window_maximize_button.setText("")
        self.window_maximize_button.setToolTip("Maximize")

        self.window_close_button = QtWidgets.QToolButton()
        self.window_close_button.setObjectName("windowCloseButton")
        self.window_close_button.setText("")
        self.window_close_button.setToolTip("Close")

        assets = ASSET_ROOT
        self._window_button_icon_pairs = {
            self.window_minimize_button: (
                QtGui.QIcon(str(assets / "window_minimize.svg")),
                QtGui.QIcon(str(assets / "window_minimize_hover.svg")),
            ),
            self.window_maximize_button: (
                QtGui.QIcon(str(assets / "window_maximize.svg")),
                QtGui.QIcon(str(assets / "window_maximize_hover.svg")),
            ),
            self.window_close_button: (
                QtGui.QIcon(str(assets / "window_close.svg")),
                QtGui.QIcon(str(assets / "window_close_hover.svg")),
            ),
        }

        for button in (
            self.window_minimize_button,
            self.window_maximize_button,
            self.window_close_button,
        ):
            button.setFixedSize(21, 23)
            button.setIcon(self._window_button_icon_pairs[button][0])
            button.setIconSize(QtCore.QSize(15, 15))
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            button.installEventFilter(self)
            controls_layout.addWidget(button)

        self.app_title_bar_layout.addWidget(controls, 0)
        self.window_minimize_button.clicked.connect(self.showMinimized)
        self.window_maximize_button.clicked.connect(self._toggle_maximized)
        self.window_close_button.clicked.connect(self.close)

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._sync_maximize_button()

    def _sync_maximize_button(self) -> None:
        maximized = self.isMaximized()
        assets = ASSET_ROOT
        if maximized:
            self._window_button_icon_pairs[self.window_maximize_button] = (
                QtGui.QIcon(str(assets / "window_restore.svg")),
                QtGui.QIcon(str(assets / "window_restore_hover.svg")),
            )
        else:
            self._window_button_icon_pairs[self.window_maximize_button] = (
                QtGui.QIcon(str(assets / "window_maximize.svg")),
                QtGui.QIcon(str(assets / "window_maximize_hover.svg")),
            )
        icon_pair = self._window_button_icon_pairs[self.window_maximize_button]
        self.window_maximize_button.setIcon(
            icon_pair[1] if self.window_maximize_button.underMouse() else icon_pair[0]
        )
        self.window_maximize_button.setToolTip(
            "Restore" if maximized else "Maximize"
        )
        for grip in self.window_resize_grips.values():
            grip.setVisible(not maximized)

    def _build_resize_grips(self) -> None:
        edge = QtCore.Qt.Edge
        cursor = QtCore.Qt.CursorShape
        definitions = {
            "top": (edge.TopEdge, cursor.SizeVerCursor),
            "bottom": (edge.BottomEdge, cursor.SizeVerCursor),
            "left": (edge.LeftEdge, cursor.SizeHorCursor),
            "right": (edge.RightEdge, cursor.SizeHorCursor),
            "top_left": (
                edge.TopEdge | edge.LeftEdge,
                cursor.SizeFDiagCursor,
            ),
            "top_right": (
                edge.TopEdge | edge.RightEdge,
                cursor.SizeBDiagCursor,
            ),
            "bottom_left": (
                edge.BottomEdge | edge.LeftEdge,
                cursor.SizeBDiagCursor,
            ),
            "bottom_right": (
                edge.BottomEdge | edge.RightEdge,
                cursor.SizeFDiagCursor,
            ),
        }
        self.window_resize_grips = {
            name: WindowResizeGrip(self, edges, shape)
            for name, (edges, shape) in definitions.items()
        }
        self._position_resize_grips()

    def _position_resize_grips(self) -> None:
        if not hasattr(self, "window_resize_grips"):
            return
        edge_width = 5
        corner_size = 10
        width = self.width()
        height = self.height()
        geometries = {
            "top": (corner_size, 0, max(0, width - 2 * corner_size), edge_width),
            "bottom": (
                corner_size,
                height - edge_width,
                max(0, width - 2 * corner_size),
                edge_width,
            ),
            "left": (0, corner_size, edge_width, max(0, height - 2 * corner_size)),
            "right": (
                width - edge_width,
                corner_size,
                edge_width,
                max(0, height - 2 * corner_size),
            ),
            "top_left": (0, 0, corner_size, corner_size),
            "top_right": (width - corner_size, 0, corner_size, corner_size),
            "bottom_left": (0, height - corner_size, corner_size, corner_size),
            "bottom_right": (
                width - corner_size,
                height - corner_size,
                corner_size,
                corner_size,
            ),
        }
        for name, geometry in geometries.items():
            grip = self.window_resize_grips[name]
            grip.setGeometry(*geometry)
            grip.raise_()

    def _position_title_label(self) -> None:
        if not hasattr(self, "app_title_label"):
            return
        self.app_title_label.adjustSize()
        x = max(0, (self.app_title_bar.width() - self.app_title_label.width()) // 2)
        y = max(0, (self.app_title_bar.height() - self.app_title_label.height()) // 2)
        self.app_title_label.move(x, y)

    def _toggle_main_navigation(self) -> None:
        self._set_main_navigation_visible(
            not self.main_navigation_overlay.isVisible()
        )

    def _set_main_navigation_visible(self, visible: bool) -> None:
        if visible:
            self._set_map_help_visible(False)
            if hasattr(self, "_set_planner_build_overlay_visible"):
                self._set_planner_build_overlay_visible(False)
            if hasattr(self, "_set_waypoint_manager_visible"):
                self._set_waypoint_manager_visible(False)
            if hasattr(self, "_set_waypoint_edit_visible"):
                self._set_waypoint_edit_visible(False)
            if hasattr(self, "_set_waypoint_confirm_visible"):
                self._set_waypoint_confirm_visible(False)
            if hasattr(self.main_navigation_overlay, "settings_panel"):
                self.main_navigation_overlay.settings_panel.reload_from_settings()
            if hasattr(self.main_navigation_overlay, "_reset_pending_settings_reset"):
                self.main_navigation_overlay._reset_pending_settings_reset()
            self.main_navigation_overlay.update_bridge_status(
                self.latest_snapshot, self.map_message
            )
            self._position_main_navigation()
            self.main_navigation_overlay.show()
            self.main_navigation_overlay.raise_()
            self.main_navigation_overlay.setFocus()
        else:
            if hasattr(self.main_navigation_overlay, "_reset_pending_settings_reset"):
                self.main_navigation_overlay._reset_pending_settings_reset()
            self.main_navigation_overlay.hide()

    def _position_main_navigation(self) -> None:
        if not hasattr(self, "main_navigation_overlay"):
            return
        side_margin = 24
        top_margin = self.app_title_bar.height() + 14
        bottom_margin = 18
        available_width = max(0, self.width() - (side_margin * 2))
        available_height = max(0, self.height() - top_margin - bottom_margin)
        overlay_width = min(720, available_width)
        overlay_height = min(540, available_height)
        self.main_navigation_overlay.setGeometry(
            max(side_margin, (self.width() - overlay_width) // 2),
            top_margin + max(0, (available_height - overlay_height) // 2),
            overlay_width,
            overlay_height,
        )
