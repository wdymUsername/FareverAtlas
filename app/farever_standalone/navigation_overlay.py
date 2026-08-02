"""In-window settings navigation and bridge diagnostics overlay."""

from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from . import __version__
from .config import PROJECT_ROOT, safe_float, safe_int
from .map_data import Snapshot
from .settings_window import SettingsWindow

class MainNavigationOverlay(QtWidgets.QFrame):
    """Discord-inspired navigation surface shown over the map window."""

    closeRequested = QtCore.Signal()

    ENTRIES = (
        ("General", "General", ""),
        ("Map", "Map", "Map display and waypoint preferences."),
        ("Party", "Party", "Party cards, markers, and distance display."),
        ("Combat", "Combat", "Combat meter and compact DPS overlay."),
        ("Alerts", "Alerts", "Target casts and notification preferences."),
        ("Bridge Status", "Bridge Status", "Telemetry connection diagnostics."),
        ("About", "About", ""),
    )

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("mainNavigationOverlay")

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QtWidgets.QWidget()
        sidebar.setObjectName("mainNavigationSidebar")
        sidebar.setFixedWidth(168)
        sidebar_layout = QtWidgets.QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 18, 10, 14)
        sidebar_layout.setSpacing(3)

        brand = QtWidgets.QLabel("FAREVER ATLAS")
        brand.setObjectName("mainNavigationBrand")
        sidebar_layout.addWidget(brand)
        section = QtWidgets.QLabel("NAVIGATION")
        section.setObjectName("mainNavigationSection")
        sidebar_layout.addWidget(section)

        self.buttons: list[QtWidgets.QPushButton] = []
        self.sections: list[QtWidgets.QWidget] = []
        self.current_section_index = 0
        settings_source = SettingsWindow()
        settings_pages: list[QtWidgets.QWidget] = []
        while settings_source.tabs.count():
            title = settings_source.tabs.tabText(0)
            page = settings_source.tabs.widget(0)
            settings_source.tabs.removeTab(0)
            wrapper = QtWidgets.QWidget()
            wrapper.setObjectName("mainNavigationPage")
            wrapper.setMinimumWidth(0)
            wrapper.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Ignored,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            wrapper_layout = QtWidgets.QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setSpacing(5)
            heading = QtWidgets.QLabel(title)
            heading.setObjectName("mainNavigationHeading")
            wrapper_layout.addWidget(heading)
            wrapper_layout.addWidget(page, 1)
            page.show()
            settings_pages.append(wrapper)
        for index, (entry, title, description) in enumerate(self.ENTRIES):
            if entry == "Bridge Status":
                separator = QtWidgets.QFrame()
                separator.setObjectName("mainNavigationSeparator")
                separator.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
                separator.setFixedHeight(1)
                sidebar_layout.addSpacing(8)
                sidebar_layout.addWidget(separator)
                sidebar_layout.addSpacing(8)
                app_section = QtWidgets.QLabel("APP")
                app_section.setObjectName("mainNavigationSection")
                sidebar_layout.addWidget(app_section)

            button = QtWidgets.QPushButton(entry)
            button.setObjectName("mainNavigationEntry")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(
                lambda _checked=False, page_index=index: self._select(page_index)
            )
            sidebar_layout.addWidget(button)
            self.buttons.append(button)
            if index < len(settings_pages):
                self.sections.append(settings_pages[index])
            else:
                self.sections.append(self._page(entry, title, description))
        settings_source.deleteLater()

        sidebar_layout.addStretch(1)
        version = QtWidgets.QLabel(f"v{__version__}")
        version.setObjectName("mainNavigationVersion")
        sidebar_layout.addWidget(version)
        root.addWidget(sidebar)

        content = QtWidgets.QWidget()
        content.setObjectName("mainNavigationContent")
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(24, 18, 18, 18)
        content_layout.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        preview = QtWidgets.QLabel(
            "settings are work in progress and probably do nothing~"
        )
        preview.setObjectName("mainNavigationHeaderNotice")
        header.addWidget(preview)
        header.addStretch(1)
        close_button = QtWidgets.QToolButton()
        close_button.setObjectName("mainNavigationClose")
        close_button.setIcon(
            QtGui.QIcon(str(PROJECT_ROOT / "assets" / "close.svg"))
        )
        close_button.setIconSize(QtCore.QSize(15, 15))
        close_button.setFixedSize(26, 26)
        close_button.setToolTip("Close")
        close_button.clicked.connect(self.closeRequested)
        header.addWidget(close_button)
        content_layout.addLayout(header)

        self.content_scroll = QtWidgets.QScrollArea()
        self.content_scroll.setObjectName("mainNavigationScroll")
        self.content_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self.content_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_body = QtWidgets.QWidget()
        self.content_body.setObjectName("mainNavigationScrollBody")
        self.content_body.setMinimumWidth(0)
        self.content_body.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        body_layout = QtWidgets.QVBoxLayout(self.content_body)
        body_layout.setContentsMargins(0, 0, 8, 8)
        body_layout.setSpacing(24)
        for section_widget in self.sections:
            body_layout.addWidget(section_widget)
            section_widget.show()
        body_layout.addStretch(1)
        self.content_scroll.setWidget(self.content_body)
        self.content_scroll.verticalScrollBar().valueChanged.connect(
            self._sync_bookmark_to_scroll
        )
        content_layout.addWidget(self.content_scroll, 1)
        root.addWidget(content, 1)

        self.buttons[0].setChecked(True)

        escape = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self)
        escape.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.closeRequested)

    def _page(
        self,
        entry: str,
        title: str,
        description: str,
    ) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        page.setObjectName("mainNavigationPage")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        heading = QtWidgets.QLabel(title)
        heading.setObjectName("mainNavigationHeading")
        layout.addWidget(heading)

        if entry == "Bridge Status":
            self.bridge_state = QtWidgets.QLabel("● Waiting for bridge")
            self.bridge_state.setObjectName("mainNavigationBridgeState")
            layout.addWidget(self.bridge_state)

            details = QtWidgets.QFrame()
            details.setObjectName("mainNavigationDetails")
            details_layout = QtWidgets.QFormLayout(details)
            details_layout.setContentsMargins(11, 10, 11, 10)
            details_layout.setHorizontalSpacing(16)
            details_layout.setVerticalSpacing(5)
            self.bridge_output = QtWidgets.QLabel("Unavailable")
            self.bridge_age = QtWidgets.QLabel("—")
            self.bridge_pois = QtWidgets.QLabel("0")
            self.bridge_schema = QtWidgets.QLabel("—")
            self.bridge_version = QtWidgets.QLabel("—")
            self.bridge_source_time = QtWidgets.QLabel("—")
            self.bridge_lock = QtWidgets.QLabel("—")
            self.bridge_sections = QtWidgets.QLabel("—")
            self.bridge_player = QtWidgets.QLabel("—")
            self.bridge_coordinates = QtWidgets.QLabel("—")
            self.bridge_party = QtWidgets.QLabel("0")
            self.bridge_target = QtWidgets.QLabel("—")
            self.bridge_combat = QtWidgets.QLabel("—")
            self.bridge_metrics = QtWidgets.QLabel("—")
            self.bridge_live_path = QtWidgets.QLabel("—")
            self.bridge_poi_path = QtWidgets.QLabel("—")
            self._bridge_value_labels = (
                self.bridge_output,
                self.bridge_age,
                self.bridge_pois,
                self.bridge_schema,
                self.bridge_version,
                self.bridge_source_time,
                self.bridge_lock,
                self.bridge_sections,
                self.bridge_player,
                self.bridge_coordinates,
                self.bridge_party,
                self.bridge_target,
                self.bridge_combat,
                self.bridge_metrics,
                self.bridge_live_path,
                self.bridge_poi_path,
            )
            for label in self._bridge_value_labels:
                label.setObjectName("mainNavigationDetailValue")
                label.setMinimumWidth(0)
                label.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Ignored,
                    QtWidgets.QSizePolicy.Policy.Preferred,
                )
            for label in (
                self.bridge_sections,
                self.bridge_live_path,
                self.bridge_poi_path,
            ):
                label.setWordWrap(True)
            details_layout.addRow("Output", self.bridge_output)
            details_layout.addRow("Freshness", self.bridge_age)
            details_layout.addRow("Schema", self.bridge_schema)
            details_layout.addRow("Bridge version", self.bridge_version)
            details_layout.addRow("Source time", self.bridge_source_time)
            details_layout.addRow("Game locked", self.bridge_lock)
            details_layout.addRow("Payload sections", self.bridge_sections)
            details_layout.addRow("Player", self.bridge_player)
            details_layout.addRow("Coordinates", self.bridge_coordinates)
            details_layout.addRow("Party entries", self.bridge_party)
            details_layout.addRow("Target", self.bridge_target)
            details_layout.addRow("Combat", self.bridge_combat)
            details_layout.addRow("DPS metrics", self.bridge_metrics)
            details_layout.addRow("Loaded POIs", self.bridge_pois)
            details_layout.addRow("Live output", self.bridge_live_path)
            details_layout.addRow("POI output", self.bridge_poi_path)
            layout.addWidget(details)

            context = QtWidgets.QLabel(
                "The Farever bridge writes read-only game telemetry for Atlas. "
                "Atlas reads that output to update player, party, map, and combat data."
            )
            context.setObjectName("mainNavigationBody")
            context.setWordWrap(True)
            layout.addWidget(context)
            self.bridge_context = QtWidgets.QLabel()
            self.bridge_context.setObjectName("mainNavigationDiagnostic")
            self.bridge_context.setWordWrap(True)
            layout.addWidget(self.bridge_context)
            copy_diagnostics = QtWidgets.QPushButton("Copy diagnostics")
            copy_diagnostics.setToolTip("Copy the current bridge diagnostics")
            copy_diagnostics.clicked.connect(self._copy_bridge_diagnostics)
            layout.addWidget(
                copy_diagnostics,
                0,
                QtCore.Qt.AlignmentFlag.AlignLeft,
            )
        elif entry == "About":
            product = QtWidgets.QLabel(
                f"<b>Farever Atlas</b> &nbsp;·&nbsp; v{__version__}"
            )
            product.setObjectName("aboutProduct")
            product.setTextFormat(QtCore.Qt.TextFormat.RichText)
            layout.addWidget(product)
            layout.addSpacing(5)

            author_row = QtWidgets.QWidget()
            author_row.setObjectName("aboutLinkRow")
            author_layout = QtWidgets.QHBoxLayout(author_row)
            author_layout.setContentsMargins(0, 0, 0, 0)
            author_layout.setSpacing(6)
            author_prefix = QtWidgets.QLabel("Created by")
            author_prefix.setObjectName("aboutLink")
            author_layout.addWidget(author_prefix)
            github_icon = QtWidgets.QLabel()
            github_icon.setFixedSize(17, 17)
            github_icon.setPixmap(
                QtGui.QPixmap(
                    str(PROJECT_ROOT / "assets" / "github.svg")
                ).scaled(
                    16,
                    16,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
            author_layout.addWidget(github_icon)
            author = QtWidgets.QLabel(
                '<a href="https://github.com/wdymUsername">'
                "wdymusername</a>"
                ' <span style="color:#6d6f78">aka nyxtaris</span>'
            )
            author.setObjectName("aboutLink")
            author.setTextFormat(QtCore.Qt.TextFormat.RichText)
            author.setOpenExternalLinks(True)
            author.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextBrowserInteraction
            )
            author_layout.addWidget(author)
            author_layout.addStretch(1)
            layout.addWidget(author_row)

            credit_row = QtWidgets.QWidget()
            credit_row.setObjectName("aboutLinkRow")
            credit_layout = QtWidgets.QHBoxLayout(credit_row)
            credit_layout.setContentsMargins(0, 0, 0, 0)
            credit_layout.setSpacing(6)
            credit_prefix = QtWidgets.QLabel("Made possible by")
            credit_prefix.setObjectName("aboutLink")
            credit_layout.addWidget(credit_prefix)
            credit_icon = QtWidgets.QLabel()
            credit_icon.setFixedSize(17, 17)
            credit_icon.setPixmap(
                QtGui.QPixmap(
                    str(PROJECT_ROOT / "assets" / "github.svg")
                ).scaled(
                    16,
                    16,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
            credit_layout.addWidget(credit_icon)
            credit = QtWidgets.QLabel(
                '<a href="https://github.com/ramisotti13-eng/farever-minimap">'
                "ramisotti13-eng</a>"
            )
            credit.setObjectName("aboutLink")
            credit.setTextFormat(QtCore.Qt.TextFormat.RichText)
            credit.setOpenExternalLinks(True)
            credit.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextBrowserInteraction
            )
            credit_layout.addWidget(credit)
            credit_layout.addStretch(1)
            layout.addWidget(credit_row)

            support_separator = QtWidgets.QFrame()
            support_separator.setObjectName("mainNavigationSeparator")
            support_separator.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            support_separator.setFixedHeight(1)
            layout.addSpacing(8)
            layout.addWidget(support_separator)
            layout.addSpacing(8)

            support_heading = QtWidgets.QLabel("SUPPORT THE PROJECT")
            support_heading.setObjectName("mainNavigationSection")
            layout.addWidget(support_heading)
            support_copy = QtWidgets.QLabel(
                "If Atlas saves you a detour, keeps your party together, "
                "or makes the numbers more satisfying, consider fueling "
                "the next update."
            )
            support_copy.setObjectName("mainNavigationBody")
            support_copy.setWordWrap(True)
            layout.addWidget(support_copy)

            support_buttons = QtWidgets.QHBoxLayout()
            support_buttons.setSpacing(8)
            for label in ("Support on Ko-fi", "Donate with PayPal"):
                button = QtWidgets.QPushButton(label)
                button.setObjectName("aboutSupportButton")
                button.setEnabled(False)
                button.setToolTip("Donation link not configured yet")
                support_buttons.addWidget(button)
            support_buttons.addStretch(1)
            layout.addLayout(support_buttons)
        else:
            body = QtWidgets.QLabel(description)
            body.setObjectName("mainNavigationBody")
            body.setWordWrap(True)
            layout.addWidget(body)
            preview = QtWidgets.QLabel("PREVIEW ONLY  ·  Entries are not active yet")
            preview.setObjectName("mainNavigationPreview")
            layout.addWidget(preview)

        layout.addStretch(1)
        return page

    def _select(self, index: int) -> None:
        if not 0 <= index < len(self.sections):
            return
        self.current_section_index = index
        self.buttons[index].setChecked(True)
        section = self.sections[index]
        QtCore.QTimer.singleShot(
            0,
            lambda target=section: self._scroll_to_section(target),
        )

    def _scroll_to_section(self, section: QtWidgets.QWidget) -> None:
        self._fit_content_width()
        self.content_scroll.horizontalScrollBar().setValue(0)
        vertical = self.content_scroll.verticalScrollBar()
        vertical.setValue(max(0, min(section.y(), vertical.maximum())))

    def _sync_bookmark_to_scroll(self, scroll_value: int) -> None:
        if not self.sections:
            return
        active_index = 0
        activation_line = scroll_value + 12
        for index, section in enumerate(self.sections):
            if section.y() <= activation_line:
                active_index = index
            else:
                break
        if scroll_value >= self.content_scroll.verticalScrollBar().maximum() - 2:
            active_index = len(self.sections) - 1
        if active_index == self.current_section_index:
            return
        self.current_section_index = active_index
        self.buttons[active_index].setChecked(True)

    def _fit_content_width(self) -> None:
        if not hasattr(self, "content_scroll"):
            return
        viewport_width = self.content_scroll.viewport().width()
        if viewport_width > 0 and self.content_body.width() != viewport_width:
            self.content_body.setFixedWidth(viewport_width)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._fit_content_width)

    def update_bridge_status(
        self,
        snapshot: Snapshot,
        map_context: str,
    ) -> None:
        if not hasattr(self, "bridge_state"):
            return
        state = snapshot.state if isinstance(snapshot.state, dict) else {}
        player = state.get("player", {}) if isinstance(state, dict) else {}
        if not isinstance(player, dict):
            player = {}
        party = state.get("party", []) if isinstance(state, dict) else []
        if not isinstance(party, list):
            party = []
        target = state.get("target", {}) if isinstance(state, dict) else {}
        if not isinstance(target, dict):
            target = {}
        dps = state.get("dps", {}) if isinstance(state, dict) else {}
        if not isinstance(dps, dict):
            dps = {}
        offline = snapshot.message == "Offline"
        self.bridge_state.setText(
            "● Connected" if snapshot.connected else f"● {snapshot.message}"
        )
        self.bridge_state.setProperty("connected", snapshot.connected)
        self.bridge_state.setProperty("offline", offline)
        style = self.bridge_state.style()
        style.unpolish(self.bridge_state)
        style.polish(self.bridge_state)
        self.bridge_output.setText(
            "Polling stopped"
            if offline
            else ("Live telemetry available" if snapshot.connected else "Unavailable")
        )
        self.bridge_age.setText(
            f"{snapshot.age:.1f} seconds"
            if snapshot.age is not None
            else "—"
        )
        self.bridge_pois.setText(str(len(snapshot.pois)))
        self.bridge_schema.setText(str(state.get("schema", "—")))
        self.bridge_version.setText(str(state.get("bridge_version") or "—"))
        self.bridge_source_time.setText(str(state.get("source_time") or "—"))
        self.bridge_lock.setText("Yes" if state.get("locked") else "No")
        self.bridge_sections.setText(
            ", ".join(sorted(str(key) for key in state.keys())) or "—"
        )
        player_name = str(player.get("name") or "").strip()
        self.bridge_player.setText(player_name or "Unavailable")
        x = safe_float(player.get("x"), math.nan)
        y = safe_float(player.get("y"), math.nan)
        self.bridge_coordinates.setText(
            f"X {x:.1f} · Y {y:.1f}"
            if math.isfinite(x) and math.isfinite(y)
            else "Unavailable"
        )
        self.bridge_party.setText(str(len(party)))
        self.bridge_target.setText(
            str(target.get("name") or target.get("uid") or "Unavailable")
        )
        fight_id = safe_int(dps.get("fight_id"), 0)
        self.bridge_combat.setText(
            f"{'Active' if dps.get('in_combat') else 'Idle'} · fight {fight_id}"
        )
        damage_metrics = dps.get("damage_skills", [])
        healing_metrics = dps.get("healing_skills", [])
        self.bridge_metrics.setText(
            f"{len(damage_metrics) if isinstance(damage_metrics, list) else 0} damage"
            f" · {len(healing_metrics) if isinstance(healing_metrics, list) else 0} healing"
        )
        self.bridge_live_path.setText(snapshot.live_path or "—")
        self.bridge_live_path.setToolTip(snapshot.live_path or "")
        self.bridge_poi_path.setText(snapshot.poi_path or "—")
        self.bridge_poi_path.setToolTip(snapshot.poi_path or "")
        self.bridge_context.setText(f"{snapshot.message}\n{map_context}")

    def _copy_bridge_diagnostics(self) -> None:
        if not hasattr(self, "_bridge_value_labels"):
            return
        labels = (
            "Output",
            "Freshness",
            "Loaded POIs",
            "Schema",
            "Bridge version",
            "Source time",
            "Game locked",
            "Payload sections",
            "Player",
            "Coordinates",
            "Party entries",
            "Target",
            "Combat",
            "DPS metrics",
            "Live output",
            "POI output",
        )
        values = (
            self.bridge_output,
            self.bridge_age,
            self.bridge_pois,
            self.bridge_schema,
            self.bridge_version,
            self.bridge_source_time,
            self.bridge_lock,
            self.bridge_sections,
            self.bridge_player,
            self.bridge_coordinates,
            self.bridge_party,
            self.bridge_target,
            self.bridge_combat,
            self.bridge_metrics,
            self.bridge_live_path,
            self.bridge_poi_path,
        )
        text = "\n".join(
            f"{label}: {value.text()}" for label, value in zip(labels, values)
        )
        text += f"\nContext: {self.bridge_context.text()}"
        QtWidgets.QApplication.clipboard().setText(text)
