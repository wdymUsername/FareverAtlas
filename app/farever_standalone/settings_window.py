"""Preview-only settings interface.

Controls intentionally have no application wiring yet.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class SettingsWindow(QtWidgets.QMainWindow):
    """Settings concept window whose entries are intentionally inert."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Farever — Settings")
        self.resize(560, 520)
        self.setMinimumSize(480, 420)

        central = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(12, 11, 12, 11)
        root.setSpacing(9)

        notice = QtWidgets.QLabel(
            "PREVIEW ONLY  ·  Settings controls are not active yet"
        )
        notice.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        notice.setStyleSheet(
            "padding:7px; color:#e0b96d; background:#211d16;"
            "border:1px solid #594b2f; border-radius:5px;"
            "font-size:10px; font-weight:700; letter-spacing:0.5px"
        )
        root.addWidget(notice)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self._general_tab(), "General")
        self.tabs.addTab(self._map_tab(), "Map")
        self.tabs.addTab(self._party_tab(), "Party")
        self.tabs.addTab(self._combat_tab(), "Combat")
        self.tabs.addTab(self._alerts_tab(), "Alerts")
        root.addWidget(self.tabs, 1)

        footer = QtWidgets.QHBoxLayout()
        reset_all = QtWidgets.QPushButton("Reset all settings")
        reset_all.setToolTip("Preview only")
        close_preview = QtWidgets.QPushButton("Close")
        close_preview.setToolTip("Preview only")
        footer.addWidget(reset_all)
        footer.addStretch(1)
        footer.addWidget(close_preview)
        root.addLayout(footer)

        self.setCentralWidget(central)

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
    def _slider(value: int) -> QtWidgets.QSlider:
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(25, 150)
        slider.setValue(value)
        return slider

    @staticmethod
    def _combo(*items: str) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        combo.addItems(items)
        return combo

    @staticmethod
    def _finish(
        page: QtWidgets.QWidget,
        layout: QtWidgets.QVBoxLayout,
        section_name: str,
    ) -> QtWidgets.QWidget:
        layout.addStretch(1)
        reset = QtWidgets.QPushButton(f"Reset {section_name}")
        reset.setToolTip("Preview only")
        layout.addWidget(reset, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        return page

    def _general_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        behavior, form = self._group("Application behavior")
        form.addRow("Always on top", QtWidgets.QCheckBox())
        form.addRow("Start minimized", QtWidgets.QCheckBox())
        single = QtWidgets.QCheckBox()
        single.setChecked(True)
        form.addRow("Single instance", single)
        form.addRow(
            "Telemetry refresh",
            self._combo("5 Hz", "4 Hz", "2 Hz", "1 Hz"),
        )
        restore = QtWidgets.QCheckBox()
        restore.setChecked(True)
        form.addRow("Restore window positions", restore)
        layout.addWidget(behavior)

        windows, window_form = self._group("Windows")
        window_form.addRow("Reset window layouts", QtWidgets.QPushButton("Reset"))
        layout.addWidget(windows)
        return self._finish(page, layout, "General")

    def _map_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        display, form = self._group("Map display")
        form.addRow(
            "Default zoom",
            self._combo("2x", "1x", "0.7x", "0.5x", "0.25x"),
        )
        texture = QtWidgets.QCheckBox()
        texture.setChecked(True)
        form.addRow("Show map texture", texture)
        form.addRow("Marker scale", self._slider(100))
        form.addRow("Name scale", self._slider(100))
        route = QtWidgets.QCheckBox()
        route.setChecked(True)
        form.addRow("Waypoint route line", route)
        layout.addWidget(display)

        defaults, default_form = self._group("Default visibility")
        defaults_poi = QtWidgets.QCheckBox()
        defaults_poi.setChecked(True)
        default_form.addRow("POIs", defaults_poi)
        default_form.addRow("Loot", QtWidgets.QCheckBox())
        default_form.addRow(
            "Reset overlay positions", QtWidgets.QPushButton("Reset")
        )
        layout.addWidget(defaults)
        return self._finish(page, layout, "Map")

    def _party_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        cards, form = self._group("Party cards")
        empty = QtWidgets.QCheckBox()
        empty.setChecked(True)
        form.addRow("Show empty slots", empty)
        form.addRow("Number of slots", self._combo("3", "2", "1", "4"))
        distance = QtWidgets.QCheckBox()
        distance.setChecked(True)
        form.addRow("Show distance", distance)
        form.addRow("Distance rounding", self._combo("1 m", "5 m", "10 m"))
        form.addRow("Empty-slot opacity", self._slider(45))
        layout.addWidget(cards)

        markers, marker_form = self._group("Map markers")
        names = QtWidgets.QCheckBox()
        names.setChecked(True)
        marker_form.addRow("Show names", names)
        marker_form.addRow("Arrow scale", self._slider(100))
        rings = QtWidgets.QCheckBox()
        rings.setChecked(True)
        marker_form.addRow("Health rings", rings)
        dim = QtWidgets.QCheckBox()
        dim.setChecked(True)
        marker_form.addRow("Dim invalid members", dim)
        layout.addWidget(markers)
        return self._finish(page, layout, "Party")

    def _combat_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        hud, form = self._group("Compact DPS HUD")
        enabled = QtWidgets.QCheckBox()
        enabled.setChecked(True)
        form.addRow("Enabled", enabled)
        form.addRow(
            "Auto behavior",
            self._combo("Always visible", "Combat only", "Auto-collapse"),
        )
        form.addRow("Scale", self._slider(100))
        form.addRow("Opacity", self._slider(85))
        form.addRow("Visible rows", self._combo("3", "1", "2", "4", "5"))
        form.addRow("Default view", self._combo("Damage", "Healing"))
        layout.addWidget(hud)

        meter, meter_form = self._group("Full Combat Meter")
        meter_form.addRow("Refresh rate", self._combo("2 FPS", "4 FPS", "1 FPS"))
        meter_form.addRow("Encounter history", self._combo("5", "10", "20", "Off"))
        meter_form.addRow(
            "Auto reset",
            self._combo("New fight ID", "Manual", "After combat"),
        )
        layout.addWidget(meter)
        return self._finish(page, layout, "Combat")

    def _alerts_tab(self) -> QtWidgets.QWidget:
        page, layout = self._page()
        casting, form = self._group("Target cast warnings")
        enabled = QtWidgets.QCheckBox()
        enabled.setChecked(True)
        form.addRow("Enabled", enabled)
        sound = QtWidgets.QCheckBox()
        sound.setChecked(True)
        form.addRow("Warning sound", sound)
        toast = QtWidgets.QCheckBox()
        toast.setChecked(True)
        form.addRow("Toast notification", toast)
        form.addRow("Minimum cast duration", self._combo("0.5 s", "1.0 s", "2.0 s"))
        form.addRow("Per-skill overrides", QtWidgets.QPushButton("Configure…"))
        layout.addWidget(casting)

        return self._finish(page, layout, "Alerts")
