"""Compact draggable DPS overlay on the map canvas."""

from __future__ import annotations

import math
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .config import fmt_number, safe_float, safe_int
from .map_widgets import DraggableMapOverlay


class DpsOverlayMixin:
    """Build, update, and persist the compact DPS overlay."""

    def _init_dps_overlay(self) -> None:
        self.dps_overlay = DraggableMapOverlay(self.radar)
        self.dps_overlay.setObjectName("dpsOverlay")
        self.dps_overlay.setFixedWidth(208)
        self.dps_overlay.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self.dps_overlay.setToolTip("Drag to reposition the DPS overlay")
        self.dps_overlay.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )
        dps_layout = QtWidgets.QVBoxLayout(self.dps_overlay)
        dps_layout.setContentsMargins(8, 6, 8, 7)
        dps_layout.setSpacing(3)

        dps_header = QtWidgets.QHBoxLayout()
        dps_header.setContentsMargins(0, 0, 0, 0)
        self.dps_overlay_state = QtWidgets.QLabel("DPS · IDLE")
        self.dps_overlay_state.setObjectName("dpsOverlayTitle")
        self.dps_overlay_open = QtWidgets.QToolButton()
        self.dps_overlay_open.setObjectName("dpsOverlayOpen")
        self.dps_overlay_open.setText("↗")
        self.dps_overlay_open.setToolTip("Open the full Combat Meter")
        self.dps_overlay_collapse = QtWidgets.QToolButton()
        self.dps_overlay_collapse.setObjectName("dpsOverlayOpen")
        self.dps_overlay_collapse.setText("−")
        self.dps_overlay_collapse.setToolTip("Collapse the DPS overlay")
        dps_header.addWidget(self.dps_overlay_state)
        dps_header.addStretch(1)
        dps_header.addWidget(self.dps_overlay_open)
        dps_header.addWidget(self.dps_overlay_collapse)
        dps_layout.addLayout(dps_header)

        self.dps_overlay_summary = QtWidgets.QLabel("0 DPS · 0 total")
        self.dps_overlay_summary.setObjectName("dpsOverlaySummary")
        dps_layout.addWidget(self.dps_overlay_summary)

        self.dps_overlay_rows: list[
            tuple[QtWidgets.QWidget, QtWidgets.QLabel, QtWidgets.QProgressBar]
        ] = []
        self._dps_overlay_signature: tuple[Any, ...] | None = None
        for _index in range(3):
            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 1, 0, 0)
            row_layout.setSpacing(1)
            row_label = QtWidgets.QLabel()
            row_label.setObjectName("dpsOverlaySkill")
            row_bar = QtWidgets.QProgressBar()
            row_bar.setObjectName("dpsOverlayBar")
            row_bar.setRange(0, 1000)
            row_bar.setTextVisible(False)
            row_bar.setFixedHeight(5)
            row_layout.addWidget(row_label)
            row_layout.addWidget(row_bar)
            dps_layout.addWidget(row_widget)
            self.dps_overlay_rows.append((row_widget, row_label, row_bar))
            row_widget.hide()

        self.dps_overlay.adjustSize()
        show_dps_overlay = self._setting_bool("map/show_dps_overlay", True)
        self.dps_overlay_collapsed = self._setting_bool(
            "map/dps_overlay_collapsed", not show_dps_overlay
        )
        self._dps_overlay_x_ratio = safe_float(
            self._settings.value("map/dps_overlay_x_ratio"), math.nan
        )
        self._dps_overlay_y_ratio = safe_float(
            self._settings.value("map/dps_overlay_y_ratio"), math.nan
        )
        self.dps_overlay.setVisible(not self.dps_overlay_collapsed)
        self.dps_overlay.raise_()

        self.dps_collapsed_button = QtWidgets.QToolButton(self.radar)
        self.dps_collapsed_button.setObjectName("dpsCollapsedButton")
        self.dps_collapsed_button.setText("DPS")
        self.dps_collapsed_button.setToolTip("Expand the compact DPS overlay")
        self.dps_collapsed_button.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self.dps_collapsed_button.setFixedSize(44, 24)
        self.dps_collapsed_button.setVisible(self.dps_overlay_collapsed)
        self.dps_collapsed_button.raise_()

    def _set_dps_overlay_collapsed(self, collapsed: bool) -> None:
        self.dps_overlay_collapsed = bool(collapsed)
        self.dps_overlay.setVisible(not self.dps_overlay_collapsed)
        self.dps_collapsed_button.setVisible(self.dps_overlay_collapsed)
        self._settings.setValue(
            "map/dps_overlay_collapsed", self.dps_overlay_collapsed
        )
        # Retain the old visibility key for downgrade compatibility.
        self._settings.setValue(
            "map/show_dps_overlay", not self.dps_overlay_collapsed
        )
        if not self.dps_overlay_collapsed:
            self._dps_overlay_signature = None
            state = (
                self.latest_snapshot.state
                if isinstance(self.latest_snapshot.state, dict)
                else {}
            )
            self._update_dps_overlay(state)
        self._position_map_overlays()

    def _dps_overlay_moved(self, position: QtCore.QPoint) -> None:
        margin = DraggableMapOverlay.SAFE_INSET
        available_x = max(
            1,
            self.radar.width() - self.dps_overlay.width() - (margin * 2),
        )
        available_y = max(
            1,
            self.radar.height() - self.dps_overlay.height() - (margin * 2),
        )
        self._dps_overlay_x_ratio = max(
            0.0, min(1.0, (position.x() - margin) / available_x)
        )
        self._dps_overlay_y_ratio = max(
            0.0, min(1.0, (position.y() - margin) / available_y)
        )
        self._settings.setValue(
            "map/dps_overlay_x_ratio", self._dps_overlay_x_ratio
        )
        self._settings.setValue(
            "map/dps_overlay_y_ratio", self._dps_overlay_y_ratio
        )

    def _update_dps_overlay(self, state: dict[str, Any]) -> None:
        if not self.dps_overlay.isVisible():
            return
        dps = state.get("dps", {}) if isinstance(state, dict) else {}
        if not isinstance(dps, dict):
            dps = {}
        elapsed = max(0.0, safe_float(dps.get("elapsed")))
        metrics = sorted(
            (
                item
                for item in (dps.get("damage_skills", []) or [])
                if isinstance(item, dict)
            ),
            key=lambda item: safe_float(item.get("total")),
            reverse=True,
        )
        total = sum(max(0.0, safe_float(item.get("total"))) for item in metrics)
        rate = total / elapsed if elapsed > 0.0 else safe_float(dps.get("current"))
        if dps.get("in_combat"):
            status = "COMBAT"
        elif metrics or safe_int(dps.get("fight_id"), 0) > 0:
            status = "COMPLETE"
        else:
            status = "IDLE"
        signature = (
            status,
            safe_int(dps.get("fight_id"), 0),
            int(elapsed * 4.0),
        )
        if signature == self._dps_overlay_signature:
            return
        self._dps_overlay_signature = signature
        self.dps_overlay_state.setText(f"DPS · {status}")
        combat_property = bool(dps.get("in_combat"))
        if self.dps_overlay_state.property("combat") != combat_property:
            self.dps_overlay_state.setProperty("combat", combat_property)
            state_style = self.dps_overlay_state.style()
            state_style.unpolish(self.dps_overlay_state)
            state_style.polish(self.dps_overlay_state)
        self.dps_overlay_summary.setText(
            f"{fmt_number(rate)} DPS · {fmt_number(total)} total"
        )

        for index, (row_widget, row_label, row_bar) in enumerate(
            self.dps_overlay_rows
        ):
            if index >= len(metrics):
                row_widget.hide()
                continue
            metric = metrics[index]
            skill_total = max(0.0, safe_float(metric.get("total")))
            share = skill_total / total if total > 0.0 else 0.0
            skill = str(metric.get("skill") or "Unknown")
            row_label.setText(
                f"{skill}   {fmt_number(skill_total)} · {share * 100:.0f}%"
            )
            row_bar.setValue(round(share * 1000))
            row_widget.show()
        self.dps_overlay.adjustSize()
