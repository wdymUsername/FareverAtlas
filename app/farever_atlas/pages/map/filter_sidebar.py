"""Floating WAYPOINTS filter panel and separate NODE GUIDE panel."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import (
    ASSET_ROOT,
    LOOSE_KIND_ICON_FILES,
    UI_CLOSE_RELATIVE_PATH,
    UI_COLLECT_RELATIVE_PATH,
    UI_WAYPOINT_RELATIVE_PATH,
    discover_project_asset,
)
from .gather_nav import GatherNavPanel

_FILTER_SEGMENTS = (
    ("actors", "Actors"),
    ("poi", "POI"),
    ("loot", "Loot"),
    ("custom", "Custom"),
)

# Visible custom waypoint rows before the list scrolls inside WAYPOINTS.
_CUSTOM_WAYPOINT_LIST_MAX_ROWS = 12
_CUSTOM_WAYPOINT_ROW_HEIGHT = 22
_CUSTOM_WAYPOINT_ROW_SPACING = 2

# Collapse NODE GUIDE after this long with no interaction on the panel.
_GATHER_SIDEBAR_IDLE_MS = 60_000

# Shared chrome for WAYPOINTS / NODE GUIDE collapsed icon squares.
# Keep the same panel inset in both states so the icon never shifts on open.
_PANEL_ICON_BTN = 18
_PANEL_ICON_GLYPH = 16
_PANEL_MARGIN = 7
_PANEL_COLLAPSED_SIZE = _PANEL_MARGIN * 2 + _PANEL_ICON_BTN  # 32
_PANEL_EXPANDED_WIDTH = 220

_HEADER_ICON_BUTTON_QSS = """
QToolButton {
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
    padding: 0px;
    margin: 0px;
    border: none;
    background: transparent;
}
QToolButton:hover {
    background: #202b36;
    border-radius: 4px;
}
"""

_HEADER_CLOSE_BUTTON_QSS = """
QToolButton {
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
    padding: 0px;
    margin: 0px;
    border: none;
    background: transparent;
}
QToolButton:hover {
    background: #202b36;
    border-radius: 4px;
}
"""


def _make_header_icon_button(
    object_name: str,
    icon: QtGui.QIcon,
    fallback_text: str,
) -> QtWidgets.QToolButton:
    button = QtWidgets.QToolButton()
    button.setObjectName(object_name)
    # App-wide QToolButton rules use min-width: 42px; lock size on the widget
    # itself so the glyph stays centered and does not shift on open/close.
    button.setStyleSheet(_HEADER_ICON_BUTTON_QSS)
    button.setFixedSize(_PANEL_ICON_BTN, _PANEL_ICON_BTN)
    button.setIconSize(QtCore.QSize(_PANEL_ICON_GLYPH, _PANEL_ICON_GLYPH))
    button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setAutoRaise(True)
    button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
    button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    if not icon.isNull():
        button.setIcon(icon)
    else:
        button.setText(fallback_text)
    return button


def _make_header_close_button(object_name: str, tooltip: str) -> QtWidgets.QToolButton:
    button = QtWidgets.QToolButton()
    button.setObjectName(object_name)
    button.setStyleSheet(_HEADER_CLOSE_BUTTON_QSS)
    button.setToolTip(tooltip)
    button.setFixedSize(_PANEL_ICON_BTN, _PANEL_ICON_BTN)
    button.setIconSize(QtCore.QSize(12, 12))
    button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setAutoRaise(True)
    button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
    button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    close_icon = discover_project_asset(UI_CLOSE_RELATIVE_PATH) or (
        ASSET_ROOT / UI_CLOSE_RELATIVE_PATH
    )
    if close_icon.is_file():
        button.setIcon(QtGui.QIcon(str(close_icon)))
    else:
        button.setText("×")
    return button


def _set_panel_collapsed_chrome(
    panel: QtWidgets.QWidget,
    header: QtWidgets.QWidget,
    *,
    collapsed: bool,
) -> None:
    """Keep identical icon inset collapsed/expanded so the glyph does not jump."""
    panel_layout = panel.layout()
    header_layout = header.layout()
    if panel_layout is None or header_layout is None:
        return
    m = _PANEL_MARGIN
    panel_layout.setContentsMargins(m, m, m, m)
    header_layout.setContentsMargins(0, 0, 0, 0)
    if collapsed:
        # Header is only the icon; size matches the inset content box.
        header.setFixedSize(_PANEL_ICON_BTN, _PANEL_ICON_BTN)
    else:
        header.setMinimumSize(0, 0)
        header.setMaximumSize(16777215, 16777215)
        header.setFixedHeight(_PANEL_ICON_BTN)


class _GatherSidebarIdleWatcher(QtCore.QObject):
    """Reset the NODE GUIDE idle timer on interaction inside the panel."""

    def __init__(self, owner: object) -> None:
        super().__init__(owner)  # type: ignore[arg-type]
        self._owner = owner
        self._installed = False

    def set_active(self, active: bool) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if active and not self._installed:
            app.installEventFilter(self)
            self._installed = True
        elif not active and self._installed:
            app.removeEventFilter(self)
            self._installed = False

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if event.type() not in {
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.MouseButtonDblClick,
            QtCore.QEvent.Type.Wheel,
            QtCore.QEvent.Type.KeyPress,
        }:
            return False
        sidebar = getattr(self._owner, "gather_sidebar", None)
        if not isinstance(sidebar, QtWidgets.QWidget):
            return False
        if getattr(self._owner, "gather_sidebar_collapsed", True):
            return False
        if not isinstance(watched, QtWidgets.QWidget):
            return False
        if watched is sidebar or sidebar.isAncestorOf(watched):
            bump = getattr(self._owner, "_bump_gather_sidebar_idle", None)
            if callable(bump):
                bump()
        return False


class FilterSidebarMixin:
    """Floating WAYPOINTS filter panel with segment pages + GATHER overlay."""

    def _init_filter_sidebar(self) -> None:
        icon_path = discover_project_asset(UI_WAYPOINT_RELATIVE_PATH) or (
            ASSET_ROOT / UI_WAYPOINT_RELATIVE_PATH
        )
        waypoint_icon = (
            QtGui.QIcon(str(icon_path)) if icon_path.is_file() else QtGui.QIcon()
        )

        # One panel for both states: collapsed is the same chrome shrunk to an
        # icon square; expanded grows the window with icon left / close right.
        self.sidebar = QtWidgets.QWidget(self.radar)
        self.sidebar.setObjectName("minimapSidebar")
        self.sidebar.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(
            _PANEL_MARGIN,
            _PANEL_MARGIN,
            _PANEL_MARGIN,
            _PANEL_MARGIN,
        )
        sidebar_layout.setSpacing(5)

        self.sidebar_header = QtWidgets.QWidget()
        self.sidebar_header.setObjectName("waypointsSidebarHeader")
        header_layout = QtWidgets.QHBoxLayout(self.sidebar_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.sidebar_header_icon = _make_header_icon_button(
            "waypointsSidebarHeaderIcon", waypoint_icon, "⌖"
        )
        self.sidebar_header_icon.setToolTip("Open WAYPOINTS")
        self.sidebar_header_icon.clicked.connect(self._on_sidebar_icon_clicked)
        header_layout.addWidget(
            self.sidebar_header_icon, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.sidebar_title = QtWidgets.QLabel("WAYPOINTS")
        self.sidebar_title.setObjectName("waypointsSidebarTitle")
        self.sidebar_title.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        header_layout.addWidget(
            self.sidebar_title, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.sidebar_header_spacer = QtWidgets.QWidget()
        self.sidebar_header_spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        header_layout.addWidget(self.sidebar_header_spacer, 1)

        self.sidebar_close = _make_header_close_button(
            "waypointsSidebarCloseButton", "Close WAYPOINTS"
        )
        header_layout.addWidget(
            self.sidebar_close, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        sidebar_layout.addWidget(self.sidebar_header)
        self.sidebar_close.clicked.connect(self._close_sidebar)

        self.sidebar_content = QtWidgets.QWidget()
        self.sidebar_content.setObjectName("sidebarContent")
        sidebar_content_layout = QtWidgets.QVBoxLayout(self.sidebar_content)
        sidebar_content_layout.setContentsMargins(0, 1, 4, 0)
        sidebar_content_layout.setSpacing(4)
        sidebar_content_layout.setSizeConstraint(
            QtWidgets.QLayout.SizeConstraint.SetMinAndMaxSize
        )

        self.sidebar_segment_bar = QtWidgets.QWidget()
        self.sidebar_segment_bar.setObjectName("sidebarSegmentBar")
        segment_layout = QtWidgets.QHBoxLayout(self.sidebar_segment_bar)
        segment_layout.setContentsMargins(0, 0, 0, 0)
        segment_layout.setSpacing(0)

        self.sidebar_segment_group = QtWidgets.QButtonGroup(self.sidebar_segment_bar)
        self.sidebar_segment_group.setExclusive(True)
        self.sidebar_segment_buttons: dict[str, QtWidgets.QPushButton] = {}
        for segment_id, label in _FILTER_SEGMENTS:
            button = QtWidgets.QPushButton(label)
            button.setObjectName("sidebarSegmentButton")
            button.setCheckable(True)
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(22)
            button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            button.setProperty("segmentId", segment_id)
            self.sidebar_segment_group.addButton(button)
            self.sidebar_segment_buttons[segment_id] = button
            segment_layout.addWidget(button)
        sidebar_content_layout.addWidget(self.sidebar_segment_bar)

        self.sidebar_filter_stack = QtWidgets.QStackedWidget()
        self.sidebar_filter_stack.setObjectName("sidebarFilterStack")

        def _chip_grid_page(
            chips: list[QtWidgets.QWidget],
            *,
            footer: QtWidgets.QWidget | None = None,
        ) -> QtWidgets.QWidget:
            page = QtWidgets.QWidget()
            page_layout = QtWidgets.QVBoxLayout(page)
            page_layout.setContentsMargins(0, 2, 0, 0)
            page_layout.setSpacing(4)
            grid_host = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(grid_host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(4)
            grid.setVerticalSpacing(4)
            for index, chip in enumerate(chips):
                chip.setObjectName("sidebarFilterChip")
                grid.addWidget(chip, index // 2, index % 2)
            page_layout.addWidget(grid_host)
            if footer is not None:
                page_layout.addWidget(footer)
            page_layout.addStretch(1)
            return page

        actors_hint = QtWidgets.QLabel("right-click Enemies toggles patrol paths")
        actors_hint.setObjectName("sidebarFilterHint")
        actors_hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        actors_page = _chip_grid_page(
            [self.enemies_filter, self.critters_filter, self.players_filter],
            footer=actors_hint,
        )
        self.sidebar_filter_stack.addWidget(actors_page)
        poi_page = _chip_grid_page(
            [self.poi_filters[kind] for kind, _label in self.POI_FILTERS]
        )
        self.sidebar_filter_stack.addWidget(poi_page)

        loot_hint = QtWidgets.QLabel("right-click toggles icon / dot")
        loot_hint.setObjectName("sidebarFilterHint")
        loot_hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        loot_page = _chip_grid_page(
            [self.loot_filters[kind] for kind, _label in self.LOOT_FILTERS],
            footer=loot_hint,
        )
        self.sidebar_filter_stack.addWidget(loot_page)

        custom_page = QtWidgets.QWidget()
        custom_page_layout = QtWidgets.QVBoxLayout(custom_page)
        custom_page_layout.setContentsMargins(0, 2, 0, 0)
        custom_page_layout.setSpacing(4)

        self.custom_actions_row = QtWidgets.QWidget()
        self.custom_actions_row.setObjectName("customActionsRow")
        actions_layout = QtWidgets.QHBoxLayout(self.custom_actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)
        for custom_button in (self.custom_add_current, self.custom_manage):
            custom_button.setObjectName("sidebarFilterChip")
            custom_button.setProperty("hasDot", False)
            custom_button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            custom_button.setFixedHeight(24)
            actions_layout.addWidget(custom_button)
        custom_page_layout.addWidget(self.custom_actions_row)

        self.custom_list_separator = QtWidgets.QFrame()
        self.custom_list_separator.setObjectName("sidebarFilterSeparator")
        self.custom_list_separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.custom_list_separator.setFixedHeight(1)
        custom_page_layout.addWidget(self.custom_list_separator)

        self.custom_filter_container = QtWidgets.QWidget()
        self.custom_filter_container.setObjectName("customFilterContainer")
        self.custom_filter_layout = QtWidgets.QVBoxLayout(self.custom_filter_container)
        self.custom_filter_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_filter_layout.setSpacing(2)

        # Cap visible custom rows so a long list scrolls inside WAYPOINTS
        # instead of growing into the gather panel below.
        self.custom_filter_scroll = QtWidgets.QScrollArea()
        self.custom_filter_scroll.setObjectName("customFilterScroll")
        self.custom_filter_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.custom_filter_scroll.setWidgetResizable(True)
        self.custom_filter_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.custom_filter_scroll.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.custom_filter_scroll.setWidget(self.custom_filter_container)
        self.custom_filter_scroll.setMinimumHeight(0)
        self.custom_filter_scroll.setFixedHeight(0)
        self.custom_filter_scroll.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        custom_page_layout.addWidget(self.custom_filter_scroll)
        custom_page_layout.addStretch(1)
        self.sidebar_filter_stack.addWidget(custom_page)

        sidebar_content_layout.addWidget(self.sidebar_filter_stack)

        self.sidebar_scroll = QtWidgets.QScrollArea()
        self.sidebar_scroll.setObjectName("sidebarScroll")
        self.sidebar_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sidebar_scroll.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sidebar_scroll.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self.sidebar_scroll.setWidget(self.sidebar_content)
        self.sidebar_scroll.setMinimumHeight(0)
        self.sidebar_scroll.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        sidebar_layout.addWidget(self.sidebar_scroll)

        self.sidebar_segment_group.buttonClicked.connect(self._on_sidebar_segment_button)

        self.sidebar_collapsed_size = _PANEL_COLLAPSED_SIZE
        self.sidebar_expanded_width = _PANEL_EXPANDED_WIDTH
        self.sidebar_width = self.sidebar_expanded_width
        self.sidebar.setFixedWidth(self.sidebar_width)
        self._sidebar_body_height = 0
        self.sidebar_filter_segment = "loot"
        self.sidebar_collapsed = False
        self.sidebar.show()
        self.sidebar.raise_()

        self.sidebar_animation = QtCore.QVariantAnimation(self)
        self.sidebar_animation.setDuration(180)
        self.sidebar_animation.valueChanged.connect(self._sidebar_height_changed)
        self.sidebar_animation.finished.connect(self._sidebar_animation_finished)

        self._init_gather_sidebar()

    def _init_gather_sidebar(self) -> None:
        icon_path = discover_project_asset(UI_COLLECT_RELATIVE_PATH) or (
            ASSET_ROOT / UI_COLLECT_RELATIVE_PATH
        )
        guide_icon = (
            QtGui.QIcon(str(icon_path)) if icon_path.is_file() else QtGui.QIcon()
        )

        # Same panel when collapsed/expanded. Header stays on top; icon left,
        # close right when open.
        self.gather_sidebar = QtWidgets.QWidget(self.radar)
        self.gather_sidebar.setObjectName("minimapSidebar")
        self.gather_sidebar.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        gather_layout = QtWidgets.QVBoxLayout(self.gather_sidebar)
        gather_layout.setContentsMargins(
            _PANEL_MARGIN,
            _PANEL_MARGIN,
            _PANEL_MARGIN,
            _PANEL_MARGIN,
        )
        gather_layout.setSpacing(5)

        self.gather_header = QtWidgets.QWidget()
        self.gather_header.setObjectName("gatherSidebarHeader")
        header_layout = QtWidgets.QHBoxLayout(self.gather_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.gather_sidebar_icon = _make_header_icon_button(
            "gatherSidebarHeaderIcon", guide_icon, "◎"
        )
        self.gather_sidebar_icon.setToolTip("Open NODE GUIDE")
        self.gather_sidebar_icon.clicked.connect(self._on_gather_sidebar_icon_clicked)
        header_layout.addWidget(
            self.gather_sidebar_icon, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.gather_sidebar_title = QtWidgets.QLabel("NODE GUIDE")
        self.gather_sidebar_title.setObjectName("gatherSidebarTitle")
        self.gather_sidebar_title.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        header_layout.addWidget(
            self.gather_sidebar_title, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.gather_header_spacer = QtWidgets.QWidget()
        self.gather_header_spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        header_layout.addWidget(self.gather_header_spacer, 1)

        self.gather_sidebar_close = _make_header_close_button(
            "gatherSidebarCloseButton", "Close NODE GUIDE"
        )
        header_layout.addWidget(
            self.gather_sidebar_close, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        gather_layout.addWidget(self.gather_header)
        self.gather_sidebar_close.clicked.connect(self._close_gather_sidebar)

        self.gather_panel = GatherNavPanel(compact=True)
        self.gather_scroll = QtWidgets.QScrollArea()
        self.gather_scroll.setObjectName("sidebarScroll")
        self.gather_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.gather_scroll.setWidgetResizable(True)
        self.gather_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.gather_scroll.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.gather_scroll.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self.gather_scroll.setWidget(self.gather_panel)
        self.gather_scroll.setMinimumHeight(0)
        self.gather_scroll.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        gather_layout.addWidget(self.gather_scroll)

        self.gather_sidebar_collapsed_size = _PANEL_COLLAPSED_SIZE
        self.gather_sidebar_expanded_width = _PANEL_EXPANDED_WIDTH
        self.gather_sidebar_width = self.gather_sidebar_collapsed_size
        self.gather_sidebar.setFixedWidth(self.gather_sidebar_width)
        self._gather_sidebar_body_height = 0
        self.gather_sidebar_collapsed = True
        self.gather_sidebar_title.hide()
        self.gather_sidebar_close.hide()
        self.gather_header_spacer.hide()
        self.gather_scroll.hide()
        _set_panel_collapsed_chrome(
            self.gather_sidebar,
            self.gather_header,
            collapsed=True,
        )
        self.gather_sidebar.show()
        self.gather_sidebar.raise_()

        self.gather_sidebar_animation = QtCore.QVariantAnimation(self)
        self.gather_sidebar_animation.setDuration(180)
        self.gather_sidebar_animation.valueChanged.connect(
            self._gather_sidebar_height_changed
        )
        self.gather_sidebar_animation.finished.connect(
            self._gather_sidebar_animation_finished
        )

        self._gather_sidebar_idle = QtCore.QTimer(self)
        self._gather_sidebar_idle.setSingleShot(True)
        self._gather_sidebar_idle.setInterval(_GATHER_SIDEBAR_IDLE_MS)
        self._gather_sidebar_idle.timeout.connect(self._on_gather_sidebar_idle)
        self._gather_sidebar_idle_watcher = _GatherSidebarIdleWatcher(self)

    def _bump_gather_sidebar_idle(self) -> None:
        if getattr(self, "gather_sidebar_collapsed", True):
            return
        if getattr(self, "gather_nav_enabled", False):
            self._stop_gather_sidebar_idle_timer_only()
            return
        timer = getattr(self, "_gather_sidebar_idle", None)
        if timer is None:
            return
        timer.start(_GATHER_SIDEBAR_IDLE_MS)

    def _stop_gather_sidebar_idle_timer_only(self) -> None:
        timer = getattr(self, "_gather_sidebar_idle", None)
        if timer is not None:
            timer.stop()

    def _stop_gather_sidebar_idle(self) -> None:
        self._stop_gather_sidebar_idle_timer_only()
        watcher = getattr(self, "_gather_sidebar_idle_watcher", None)
        if watcher is not None:
            watcher.set_active(False)

    def _on_gather_sidebar_idle(self) -> None:
        if getattr(self, "gather_sidebar_collapsed", True):
            return
        if getattr(self, "gather_nav_enabled", False):
            return
        self._set_gather_sidebar_collapsed(True)

    def _on_gather_sidebar_icon_clicked(self) -> None:
        if self.gather_sidebar_collapsed:
            self._set_gather_sidebar_collapsed(False)

    def _close_gather_sidebar(self) -> None:
        if not self.gather_sidebar_collapsed:
            self._set_gather_sidebar_collapsed(True)

    def _custom_waypoint_list_max_height(self) -> int:
        rows = _CUSTOM_WAYPOINT_LIST_MAX_ROWS
        if rows <= 0:
            return 0
        return (
            rows * _CUSTOM_WAYPOINT_ROW_HEIGHT
            + max(0, rows - 1) * _CUSTOM_WAYPOINT_ROW_SPACING
        )

    def _sync_custom_filter_scroll_height(self) -> None:
        scroll = getattr(self, "custom_filter_scroll", None)
        container = getattr(self, "custom_filter_container", None)
        if scroll is None or container is None:
            return
        layout = container.layout()
        if layout is not None:
            layout.activate()
            content_height = max(0, layout.sizeHint().height())
        else:
            content_height = 0
        max_height = self._custom_waypoint_list_max_height()
        height = min(content_height, max_height)
        scroll.setMaximumHeight(max_height)
        scroll.setFixedHeight(height)
        scroll.setVisible(True)
        scroll.updateGeometry()
        sidebar_content = getattr(self, "sidebar_content", None)
        if sidebar_content is not None:
            sidebar_content.updateGeometry()

    def _on_sidebar_segment_button(self, button: QtWidgets.QAbstractButton) -> None:
        segment_id = str(button.property("segmentId") or "loot")
        self._set_sidebar_filter_segment(segment_id)

    def _set_sidebar_filter_segment(
        self,
        segment_id: str,
        *,
        persist: bool = True,
    ) -> None:
        valid = {item[0] for item in _FILTER_SEGMENTS}
        if segment_id not in valid:
            segment_id = "loot"
        self.sidebar_filter_segment = segment_id
        index = next(
            i for i, (sid, _label) in enumerate(_FILTER_SEGMENTS) if sid == segment_id
        )
        button = self.sidebar_segment_buttons.get(segment_id)
        if button is not None and not button.isChecked():
            blocked = button.blockSignals(True)
            button.setChecked(True)
            button.blockSignals(blocked)
        self.sidebar_filter_stack.setCurrentIndex(index)
        if segment_id == "custom":
            self._sync_custom_filter_scroll_height()
        if not getattr(self, "sidebar_collapsed", False):
            self._set_sidebar_body_height(self._sidebar_target_body_height())
            self._position_map_overlays()
        if persist:
            self._settings.setValue("map/sidebar_filter_segment", segment_id)

    def _toggle_sidebar(self) -> None:
        self._set_sidebar_collapsed(not self.sidebar_collapsed)

    def _on_sidebar_icon_clicked(self) -> None:
        if self.sidebar_collapsed:
            self._set_sidebar_collapsed(False)

    def _close_sidebar(self) -> None:
        if not self.sidebar_collapsed:
            self._set_sidebar_collapsed(True)

    def _toggle_gather_sidebar(self) -> None:
        self._set_gather_sidebar_collapsed(not self.gather_sidebar_collapsed)

    def _overlay_animation_step(self, _value: object = None) -> None:
        self._position_map_overlays()

    def _apply_sidebar_collapsed_chrome(self) -> None:
        collapsed = bool(getattr(self, "sidebar_collapsed", False))
        self.sidebar_title.setVisible(not collapsed)
        self.sidebar_close.setVisible(not collapsed)
        self.sidebar_header_spacer.setVisible(not collapsed)
        self.sidebar_header_icon.setToolTip(
            "Open WAYPOINTS" if collapsed else "WAYPOINTS"
        )
        size = int(getattr(self, "sidebar_collapsed_size", _PANEL_COLLAPSED_SIZE))
        self.sidebar_width = (
            size
            if collapsed
            else int(getattr(self, "sidebar_expanded_width", _PANEL_EXPANDED_WIDTH))
        )
        self.sidebar.setFixedWidth(self.sidebar_width)
        _set_panel_collapsed_chrome(
            self.sidebar,
            self.sidebar_header,
            collapsed=collapsed,
        )

    def _apply_gather_sidebar_collapsed_chrome(self) -> None:
        collapsed = bool(getattr(self, "gather_sidebar_collapsed", True))
        self.gather_sidebar_title.setVisible(not collapsed)
        self.gather_sidebar_close.setVisible(not collapsed)
        self.gather_header_spacer.setVisible(not collapsed)
        self.gather_sidebar_icon.setToolTip(
            "Open NODE GUIDE" if collapsed else "NODE GUIDE"
        )
        size = int(
            getattr(self, "gather_sidebar_collapsed_size", _PANEL_COLLAPSED_SIZE)
        )
        self.gather_sidebar_width = (
            size
            if collapsed
            else int(
                getattr(self, "gather_sidebar_expanded_width", _PANEL_EXPANDED_WIDTH)
            )
        )
        self.gather_sidebar.setFixedWidth(self.gather_sidebar_width)
        _set_panel_collapsed_chrome(
            self.gather_sidebar,
            self.gather_header,
            collapsed=collapsed,
        )

    def _sidebar_chrome_height(self, body_height: int) -> int:
        if getattr(self, "sidebar_collapsed", False):
            return int(getattr(self, "sidebar_collapsed_size", _PANEL_COLLAPSED_SIZE))
        sidebar_layout = self.sidebar.layout()
        margins = sidebar_layout.contentsMargins()
        spacing = sidebar_layout.spacing() if body_height > 0 else 0
        header_height = max(_PANEL_ICON_BTN, self.sidebar_header.sizeHint().height())
        return margins.top() + header_height + spacing + margins.bottom()

    def _gather_sidebar_chrome_height(self, body_height: int) -> int:
        if getattr(self, "gather_sidebar_collapsed", True):
            return int(
                getattr(self, "gather_sidebar_collapsed_size", _PANEL_COLLAPSED_SIZE)
            )
        gather_layout = self.gather_sidebar.layout()
        margins = gather_layout.contentsMargins()
        spacing = gather_layout.spacing() if body_height > 0 else 0
        header_height = max(_PANEL_ICON_BTN, self.gather_header.sizeHint().height())
        return margins.top() + header_height + spacing + margins.bottom()

    def _sync_scroll_bar_policy(
        self,
        scroll: QtWidgets.QScrollArea,
        *,
        content_height: int,
        animating: bool,
    ) -> None:
        """Hide scrollbars while opening; show only when content overflows."""
        if animating or content_height <= 0 or not scroll.isVisible():
            scroll.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            return
        view_height = max(0, scroll.viewport().height())
        if content_height > view_height + 1:
            scroll.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
        else:
            scroll.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

    def _sync_sidebar_scroll_bar(self, *, animating: bool | None = None) -> None:
        if animating is None:
            animating = (
                self.sidebar_animation.state()
                == QtCore.QAbstractAnimation.State.Running
            )
        self._sync_scroll_bar_policy(
            self.sidebar_scroll,
            content_height=self._sidebar_content_height()
            if not getattr(self, "sidebar_collapsed", False)
            else 0,
            animating=bool(animating),
        )

    def _sync_gather_scroll_bar(self, *, animating: bool | None = None) -> None:
        if animating is None:
            animating = (
                self.gather_sidebar_animation.state()
                == QtCore.QAbstractAnimation.State.Running
            )
        self._sync_scroll_bar_policy(
            self.gather_scroll,
            content_height=self._gather_sidebar_content_height()
            if not getattr(self, "gather_sidebar_collapsed", True)
            else 0,
            animating=bool(animating),
        )

    def _sidebar_content_height(self) -> int:
        if getattr(self, "sidebar_filter_segment", "") == "custom":
            self._sync_custom_filter_scroll_height()
        content_layout = self.sidebar_content.layout()
        content_layout.activate()
        return max(0, content_layout.sizeHint().height())

    def _gather_sidebar_content_height(self) -> int:
        panel = self.gather_panel
        panel.adjustSize()
        if hasattr(panel, "full_content_height"):
            return max(0, int(panel.full_content_height()))
        return max(0, panel.sizeHint().height())

    def _sidebar_body_limit(self, margin: int = 4) -> int:
        available_height = max(0, self.radar.height() - (margin * 2))
        # Leave room for a collapsed gather header at the bottom when both open.
        gather_reserve = self._gather_sidebar_chrome_height(0) + margin
        return max(
            0,
            available_height - self._sidebar_chrome_height(1) - gather_reserve,
        )

    def _gather_sidebar_body_limit(self, margin: int = 4) -> int:
        available_height = max(0, self.radar.height() - (margin * 2))
        waypoints_used = self._sidebar_chrome_height(self._sidebar_body_height)
        if self._sidebar_body_height > 0:
            waypoints_used += self._sidebar_body_height
        return max(
            0,
            available_height
            - waypoints_used
            - margin
            - self._gather_sidebar_chrome_height(1),
        )

    def _sidebar_target_body_height(self, margin: int = 4) -> int:
        if getattr(self, "sidebar_collapsed", False):
            return 0
        return min(self._sidebar_content_height(), self._sidebar_body_limit(margin))

    def _gather_sidebar_target_body_height(self, margin: int = 4) -> int:
        if getattr(self, "gather_sidebar_collapsed", True):
            return 0
        return min(
            self._gather_sidebar_content_height(),
            self._gather_sidebar_body_limit(margin),
        )

    def _set_sidebar_body_height(self, height: int) -> None:
        height = max(0, int(height))
        self._sidebar_body_height = height
        self.sidebar_scroll.setFixedHeight(height)
        self.sidebar_scroll.setVisible(height > 0)
        animating = (
            self.sidebar_animation.state() == QtCore.QAbstractAnimation.State.Running
        )
        self._sync_sidebar_scroll_bar(animating=animating)

    def _set_gather_sidebar_body_height(self, height: int) -> None:
        height = max(0, int(height))
        self._gather_sidebar_body_height = height
        self.gather_scroll.setFixedHeight(height)
        self.gather_scroll.setVisible(height > 0)
        animating = (
            self.gather_sidebar_animation.state()
            == QtCore.QAbstractAnimation.State.Running
        )
        self._sync_gather_scroll_bar(animating=animating)

    def _sidebar_height_changed(self, value: object) -> None:
        try:
            requested_height = round(float(value))
        except (TypeError, ValueError):
            requested_height = self._sidebar_target_body_height()
        self._set_sidebar_body_height(
            min(requested_height, self._sidebar_body_limit())
        )
        self._position_map_overlays()

    def _gather_sidebar_height_changed(self, value: object) -> None:
        try:
            requested_height = round(float(value))
        except (TypeError, ValueError):
            requested_height = self._gather_sidebar_target_body_height()
        self._set_gather_sidebar_body_height(
            min(requested_height, self._gather_sidebar_body_limit())
        )
        self._position_map_overlays()

    def _sidebar_animation_finished(self) -> None:
        self._set_sidebar_body_height(self._sidebar_target_body_height())
        self._sync_sidebar_scroll_bar(animating=False)
        self._position_map_overlays()

    def _gather_sidebar_animation_finished(self) -> None:
        self._set_gather_sidebar_body_height(self._gather_sidebar_target_body_height())
        self._sync_gather_scroll_bar(animating=False)
        self._position_map_overlays()

    def _set_sidebar_collapsed(
        self,
        collapsed: bool,
        *,
        persist: bool = True,
        animate: bool = True,
    ) -> None:
        self.sidebar_collapsed = bool(collapsed)
        self._apply_sidebar_collapsed_chrome()
        self.sidebar.show()
        self.sidebar.raise_()

        self.sidebar_animation.stop()
        current_height = self._sidebar_body_height
        target_height = self._sidebar_target_body_height()
        if self.sidebar_collapsed:
            self._set_sidebar_body_height(0)
            self._position_map_overlays()
        elif animate and current_height != target_height:
            self._sync_sidebar_scroll_bar(animating=True)
            self.sidebar_animation.setStartValue(current_height)
            self.sidebar_animation.setEndValue(target_height)
            self.sidebar_animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
            self.sidebar_animation.start()
        else:
            self._set_sidebar_body_height(target_height)
            self._sync_sidebar_scroll_bar(animating=False)
            self._position_map_overlays()

        if persist:
            self._settings.setValue("map/sidebar_collapsed", self.sidebar_collapsed)

    def _set_gather_sidebar_collapsed(
        self,
        collapsed: bool,
        *,
        persist: bool = True,
        animate: bool = True,
    ) -> None:
        self.gather_sidebar_collapsed = bool(collapsed)
        self._apply_gather_sidebar_collapsed_chrome()
        self.gather_sidebar.show()
        self.gather_sidebar.raise_()

        if self.gather_sidebar_collapsed:
            self._stop_gather_sidebar_idle()
            self.gather_sidebar_animation.stop()
            self._set_gather_sidebar_body_height(0)
            self._position_map_overlays()
        else:
            self.gather_sidebar_animation.stop()
            current_height = self._gather_sidebar_body_height
            target_height = self._gather_sidebar_target_body_height()
            if animate and current_height != target_height:
                self._sync_gather_scroll_bar(animating=True)
                self.gather_sidebar_animation.setStartValue(current_height)
                self.gather_sidebar_animation.setEndValue(target_height)
                self.gather_sidebar_animation.setEasingCurve(
                    QtCore.QEasingCurve.Type.OutCubic
                )
                self.gather_sidebar_animation.start()
            else:
                self._set_gather_sidebar_body_height(target_height)
                self._sync_gather_scroll_bar(animating=False)
                self._position_map_overlays()
            watcher = getattr(self, "_gather_sidebar_idle_watcher", None)
            if watcher is not None:
                watcher.set_active(True)
            self._bump_gather_sidebar_idle()

        if persist:
            self._settings.setValue(
                "map/gather_sidebar_collapsed", self.gather_sidebar_collapsed
            )

    def _toggle_loot_icon_mode(
        self, kind: str, _position: QtCore.QPoint | None = None
    ) -> None:
        if kind not in self.loot_icon_modes:
            return
        self.loot_icon_modes[kind] = not bool(self.loot_icon_modes.get(kind, True))
        self._loot_icon_mode_changed(kind, self.loot_icon_modes[kind])

    def _toggle_patrol_paths_mode(
        self, _position: QtCore.QPoint | None = None
    ) -> None:
        self.show_patrol_paths = not bool(getattr(self, "show_patrol_paths", True))
        self._update_enemies_filter_tooltip()
        self._controls_changed()

    def _update_enemies_filter_tooltip(self) -> None:
        button = getattr(self, "enemies_filter", None)
        if button is None:
            return
        base = "Show or hide nearby enemies on the map"
        if bool(getattr(self, "show_patrol_paths", True)):
            button.setToolTip(
                f"{base}\nPatrol paths ON · Right-click to hide paths"
            )
        else:
            button.setToolTip(
                f"{base}\nPatrol paths OFF · Right-click to show paths"
            )

    def _update_loot_mode_button(self, kind: str) -> None:
        button = self.loot_filters.get(kind)
        if button is None:
            return
        use_icon = bool(self.loot_icon_modes.get(kind, True))
        radar = getattr(self, "radar", None)
        icon_available = bool(
            radar is not None and radar.icon_available_for_kind(kind)
        )
        label = button.text()
        base = f"Show or hide {label.lower()}"
        if use_icon and not icon_available:
            filename = LOOSE_KIND_ICON_FILES.get(kind)
            expected = f"assets/{filename}" if filename else "the configured icon asset"
            button.setToolTip(
                f"{base}\nICON mode selected, but {expected} is unavailable; "
                "the colored dot remains in use. Right-click to switch to DOT."
            )
        elif use_icon:
            button.setToolTip(f"{base}\nICON mode · Right-click for DOT")
        else:
            button.setToolTip(f"{base}\nDOT mode · Right-click for ICON")

    def _loot_icon_mode_changed(self, kind: str, _checked: bool) -> None:
        self._update_loot_mode_button(kind)
        self._controls_changed()

    def _poi_filter_changed(self, _checked: bool) -> None:
        self._controls_changed()
