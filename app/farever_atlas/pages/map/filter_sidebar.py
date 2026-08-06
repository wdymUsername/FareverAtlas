"""Collapsible POI, loot, and custom waypoint filter sidebar."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import LOOSE_KIND_ICON_FILES
from ...controls import LootFilterButton, SidebarHeaderButton, SlideSwitch


class FilterSidebarMixin:
    """Floating WAYPOINTS panel with animated filter sections."""

    def _init_filter_sidebar(self) -> None:
        # Floating collapsible sidebar anchored inside the map viewport.
        self.sidebar = QtWidgets.QWidget(self.radar)
        self.sidebar.setObjectName("minimapSidebar")
        self.sidebar.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(5, 5, 5, 5)
        sidebar_layout.setSpacing(5)

        # One full-width header button remains visible at all times.
        # Clicking anywhere on it rolls the filter list down or up.
        self.sidebar_toggle = SidebarHeaderButton("WAYPOINTS", "sidebarHeaderButton")
        self.sidebar_toggle.setToolTip("Hide waypoint filters")
        self.sidebar_toggle.setFixedHeight(26)
        self.sidebar_toggle.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        sidebar_layout.addWidget(self.sidebar_toggle)

        self.sidebar_content = QtWidgets.QWidget()
        self.sidebar_content.setObjectName("sidebarContent")
        sidebar_content_layout = QtWidgets.QVBoxLayout(self.sidebar_content)
        # Leave a small visual gutter between filter controls and the
        # vertical scrollbar when the body overflows.
        sidebar_content_layout.setContentsMargins(0, 1, 4, 0)
        sidebar_content_layout.setSpacing(4)
        sidebar_content_layout.setSizeConstraint(
            QtWidgets.QLayout.SizeConstraint.SetMinAndMaxSize
        )

        sidebar_content_layout.addWidget(self.poi_section_toggle)

        self.poi_filter_container = QtWidgets.QWidget()
        self.poi_filter_container.setObjectName("poiFilterContainer")
        poi_filter_layout = QtWidgets.QVBoxLayout(self.poi_filter_container)
        poi_filter_layout.setContentsMargins(7, 0, 0, 0)
        poi_filter_layout.setSpacing(1)
        for kind, _label in self.POI_FILTERS:
            sidebar_item = self.poi_filters[kind]
            sidebar_item.setObjectName("sidebarSubItem")
            sidebar_item.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            poi_filter_layout.addWidget(sidebar_item)
        sidebar_content_layout.addWidget(self.poi_filter_container)
        self.poi_filter_container.setMinimumHeight(0)

        self.poi_filter_animation = QtCore.QPropertyAnimation(
            self.poi_filter_container, b"maximumHeight", self
        )
        self.poi_filter_animation.setDuration(160)
        self.poi_filter_animation.valueChanged.connect(self._overlay_animation_step)
        self.poi_filter_animation.finished.connect(self._poi_animation_finished)

        sidebar_content_layout.addWidget(self.loot_section_toggle)

        self.loot_filter_container = QtWidgets.QWidget()
        self.loot_filter_container.setObjectName("lootFilterContainer")
        loot_filter_layout = QtWidgets.QVBoxLayout(self.loot_filter_container)
        loot_filter_layout.setContentsMargins(7, 0, 0, 0)
        loot_filter_layout.setSpacing(1)
        for kind, _label in self.LOOT_FILTERS:
            sidebar_item = self.loot_filters[kind]
            sidebar_item.setObjectName("sidebarSubItem")
            sidebar_item.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            loot_filter_layout.addWidget(sidebar_item)
        sidebar_content_layout.addWidget(self.loot_filter_container)
        self.loot_filter_container.setMinimumHeight(0)

        self.loot_filter_animation = QtCore.QPropertyAnimation(
            self.loot_filter_container, b"maximumHeight", self
        )
        self.loot_filter_animation.setDuration(160)
        self.loot_filter_animation.valueChanged.connect(self._overlay_animation_step)
        self.loot_filter_animation.finished.connect(self._loot_animation_finished)

        sidebar_content_layout.addWidget(self.custom_section_toggle)

        self.custom_filter_container = QtWidgets.QWidget()
        self.custom_filter_container.setObjectName("customFilterContainer")
        self.custom_filter_layout = QtWidgets.QVBoxLayout(self.custom_filter_container)
        self.custom_filter_layout.setContentsMargins(7, 0, 0, 0)
        self.custom_filter_layout.setSpacing(1)
        for custom_button in (self.custom_add_current, self.custom_manage):
            custom_button.setObjectName("sidebarSubItem")
            custom_button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            self.custom_filter_layout.addWidget(custom_button)
        sidebar_content_layout.addWidget(self.custom_filter_container)
        self.custom_filter_container.setMinimumHeight(0)

        self.custom_filter_animation = QtCore.QPropertyAnimation(
            self.custom_filter_container, b"maximumHeight", self
        )
        self.custom_filter_animation.setDuration(160)
        self.custom_filter_animation.valueChanged.connect(self._overlay_animation_step)
        self.custom_filter_animation.finished.connect(self._custom_animation_finished)

        # Keep the permanent WAYPOINTS header outside the scrolling region.
        # The body may grow indefinitely as custom waypoints are added.
        self.sidebar_scroll = QtWidgets.QScrollArea()
        self.sidebar_scroll.setObjectName("sidebarScroll")
        self.sidebar_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sidebar_scroll.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
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

        # The WAYPOINTS header remains full-width at all times. Only the
        # filter rows roll down/up beneath it.
        self.sidebar_width = 186
        self.sidebar.setFixedWidth(self.sidebar_width)
        self._sidebar_body_height = 0
        self.sidebar.raise_()

        self.sidebar_animation = QtCore.QVariantAnimation(self)
        self.sidebar_animation.setDuration(180)
        self.sidebar_animation.valueChanged.connect(self._sidebar_height_changed)
        self.sidebar_animation.finished.connect(self._sidebar_animation_finished)

    def _toggle_sidebar(self) -> None:
        self._set_sidebar_collapsed(not self.sidebar_collapsed)

    def _overlay_animation_step(self, _value: object = None) -> None:
        self._position_map_overlays()

    def _sidebar_chrome_height(self, body_height: int) -> int:
        sidebar_layout = self.sidebar.layout()
        margins = sidebar_layout.contentsMargins()
        spacing = sidebar_layout.spacing() if body_height > 0 else 0
        return (
            margins.top()
            + self.sidebar_toggle.height()
            + spacing
            + margins.bottom()
        )

    def _sidebar_content_height(self) -> int:
        content_layout = self.sidebar_content.layout()
        content_layout.activate()
        return max(0, content_layout.sizeHint().height())

    def _sidebar_body_limit(self, margin: int = 4) -> int:
        available_height = max(0, self.radar.height() - (margin * 2))
        return max(0, available_height - self._sidebar_chrome_height(1))

    def _sidebar_target_body_height(self, margin: int = 4) -> int:
        if getattr(self, "sidebar_collapsed", False):
            return 0
        return min(self._sidebar_content_height(), self._sidebar_body_limit(margin))

    def _set_sidebar_body_height(self, height: int) -> None:
        height = max(0, int(height))
        self._sidebar_body_height = height
        self.sidebar_scroll.setFixedHeight(height)
        self.sidebar_scroll.setVisible(height > 0)

    def _sidebar_height_changed(self, value: object) -> None:
        try:
            requested_height = round(float(value))
        except (TypeError, ValueError):
            requested_height = self._sidebar_target_body_height()
        self._set_sidebar_body_height(
            min(requested_height, self._sidebar_body_limit())
        )
        self._position_map_overlays()

    def _sidebar_animation_finished(self) -> None:
        self._set_sidebar_body_height(self._sidebar_target_body_height())
        self._position_map_overlays()

    def _poi_animation_finished(self) -> None:
        if self.poi_collapsed:
            self.poi_filter_container.setVisible(False)
        else:
            self.poi_filter_container.setMaximumHeight(16777215)
        self._position_map_overlays()

    def _loot_animation_finished(self) -> None:
        if self.loot_collapsed:
            self.loot_filter_container.setVisible(False)
        else:
            self.loot_filter_container.setMaximumHeight(16777215)
        self._position_map_overlays()

    def _custom_animation_finished(self) -> None:
        if self.custom_collapsed:
            self.custom_filter_container.setVisible(False)
        else:
            self.custom_filter_container.setMaximumHeight(16777215)
        self._position_map_overlays()

    def _set_sidebar_collapsed(
        self,
        collapsed: bool,
        *,
        persist: bool = True,
        animate: bool = True,
    ) -> None:
        self.sidebar_collapsed = bool(collapsed)

        # Keep the full-width WAYPOINTS header visible and preserve the panel width.
        # Only the filter rows animate vertically beneath it.
        self.sidebar.setFixedWidth(self.sidebar_width)
        self.sidebar_toggle.set_expanded(not self.sidebar_collapsed)
        self.sidebar_toggle.setToolTip(
            "Show waypoint filters" if self.sidebar_collapsed else "Hide waypoint filters"
        )

        self.sidebar_animation.stop()
        current_height = self._sidebar_body_height
        target_height = self._sidebar_target_body_height()

        if animate and current_height != target_height:
            self.sidebar_animation.setStartValue(current_height)
            self.sidebar_animation.setEndValue(target_height)
            self.sidebar_animation.setEasingCurve(
                QtCore.QEasingCurve.Type.InCubic
                if self.sidebar_collapsed
                else QtCore.QEasingCurve.Type.OutCubic
            )
            self.sidebar_animation.start()
        else:
            self._set_sidebar_body_height(target_height)
            self._position_map_overlays()

        if persist:
            self._settings.setValue("map/sidebar_collapsed", self.sidebar_collapsed)

    def _toggle_poi_section(self) -> None:
        self._set_poi_collapsed(not self.poi_collapsed)

    def _set_poi_collapsed(
        self,
        collapsed: bool,
        *,
        persist: bool = True,
        animate: bool = True,
    ) -> None:
        self.poi_collapsed = bool(collapsed)
        self.poi_section_toggle.set_expanded(not self.poi_collapsed)
        self.poi_section_toggle.setToolTip(
            "Show POI filters" if self.poi_collapsed else "Hide POI filters"
        )

        self.poi_filter_animation.stop()
        current_height = max(0, self.poi_filter_container.height())
        expanded_height = max(
            0, self.poi_filter_container.layout().sizeHint().height()
        )
        target_height = 0 if self.poi_collapsed else expanded_height

        if not self.poi_collapsed:
            self.poi_filter_container.setVisible(True)

        if animate and current_height != target_height:
            self.poi_filter_container.setMaximumHeight(current_height)
            self.poi_filter_animation.setStartValue(current_height)
            self.poi_filter_animation.setEndValue(target_height)
            self.poi_filter_animation.setEasingCurve(
                QtCore.QEasingCurve.Type.InCubic
                if self.poi_collapsed
                else QtCore.QEasingCurve.Type.OutCubic
            )
            self.poi_filter_animation.start()
        else:
            self.poi_filter_container.setMaximumHeight(
                0 if self.poi_collapsed else 16777215
            )
            self.poi_filter_container.setVisible(not self.poi_collapsed)
            self._position_map_overlays()

        if persist:
            self._settings.setValue("map/poi_collapsed", self.poi_collapsed)

    def _toggle_loot_section(self) -> None:
        self._set_loot_collapsed(not self.loot_collapsed)

    def _set_loot_collapsed(
        self,
        collapsed: bool,
        *,
        persist: bool = True,
        animate: bool = True,
    ) -> None:
        self.loot_collapsed = bool(collapsed)
        self.loot_section_toggle.set_expanded(not self.loot_collapsed)
        self.loot_section_toggle.setToolTip(
            "Show loot filters" if self.loot_collapsed else "Hide loot filters"
        )

        self.loot_filter_animation.stop()
        current_height = max(0, self.loot_filter_container.height())
        expanded_height = max(0, self.loot_filter_container.layout().sizeHint().height())
        target_height = 0 if self.loot_collapsed else expanded_height

        if not self.loot_collapsed:
            self.loot_filter_container.setVisible(True)

        if animate and current_height != target_height:
            self.loot_filter_container.setMaximumHeight(current_height)
            self.loot_filter_animation.setStartValue(current_height)
            self.loot_filter_animation.setEndValue(target_height)
            self.loot_filter_animation.setEasingCurve(
                QtCore.QEasingCurve.Type.InCubic
                if self.loot_collapsed
                else QtCore.QEasingCurve.Type.OutCubic
            )
            self.loot_filter_animation.start()
        else:
            self.loot_filter_container.setMaximumHeight(
                0 if self.loot_collapsed else 16777215
            )
            self.loot_filter_container.setVisible(not self.loot_collapsed)
            self._position_map_overlays()

        if persist:
            self._settings.setValue("map/loot_collapsed", self.loot_collapsed)

    def _toggle_custom_section(self) -> None:
        self._set_custom_collapsed(not self.custom_collapsed)

    def _set_custom_collapsed(
        self,
        collapsed: bool,
        *,
        persist: bool = True,
        animate: bool = True,
    ) -> None:
        self.custom_collapsed = bool(collapsed)
        self.custom_section_toggle.set_expanded(not self.custom_collapsed)
        self.custom_section_toggle.setToolTip(
            "Show custom waypoint filters"
            if self.custom_collapsed
            else "Hide custom waypoint filters"
        )

        self.custom_filter_animation.stop()
        current_height = max(0, self.custom_filter_container.height())
        expanded_height = max(0, self.custom_filter_container.layout().sizeHint().height())
        target_height = 0 if self.custom_collapsed else expanded_height

        if not self.custom_collapsed:
            self.custom_filter_container.setVisible(True)

        if animate and current_height != target_height:
            self.custom_filter_container.setMaximumHeight(current_height)
            self.custom_filter_animation.setStartValue(current_height)
            self.custom_filter_animation.setEndValue(target_height)
            self.custom_filter_animation.setEasingCurve(
                QtCore.QEasingCurve.Type.InCubic
                if self.custom_collapsed
                else QtCore.QEasingCurve.Type.OutCubic
            )
            self.custom_filter_animation.start()
        else:
            self.custom_filter_container.setMaximumHeight(
                0 if self.custom_collapsed else 16777215
            )
            self.custom_filter_container.setVisible(not self.custom_collapsed)
            self._position_map_overlays()

        if persist:
            self._settings.setValue("map/custom_collapsed", self.custom_collapsed)

    def _update_loot_mode_button(self, kind: str) -> None:
        button = self.loot_icon_modes[kind]
        use_icon = button.isChecked()
        radar = getattr(self, "radar", None)
        icon_available = bool(
            radar is not None and radar.icon_available_for_kind(kind)
        )
        if use_icon and not icon_available:
            filename = LOOSE_KIND_ICON_FILES.get(kind)
            expected = f"assets/{filename}" if filename else "the configured icon asset"
            button.setToolTip(
                f"ICON mode selected, but {expected} is unavailable; "
                "the colored dot remains in use. Click to select DOT mode."
            )
        elif use_icon:
            button.setToolTip("ICON mode · Click to use the colored dot")
        else:
            button.setToolTip("DOT mode · Click to use the icon")

    def _loot_icon_mode_changed(self, kind: str, _checked: bool) -> None:
        self._update_loot_mode_button(kind)
        self._controls_changed()

    def _poi_filter_changed(self, _checked: bool) -> None:
        self._controls_changed()
