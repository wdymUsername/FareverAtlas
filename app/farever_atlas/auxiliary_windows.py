"""Optional combat meter window."""

from __future__ import annotations

from typing import Any, Iterable

from PySide6 import QtCore, QtGui, QtWidgets

from .config import (
    fmt_number,
    safe_float,
    safe_int,
)
from .pages.map.data import Snapshot
from .window_base import PersistentWindow, apply_always_on_top


class NumericTableItem(QtWidgets.QTableWidgetItem):
    def __lt__(self, other: QtWidgets.QTableWidgetItem) -> bool:
        own_value = self.data(QtCore.Qt.ItemDataRole.UserRole)
        other_value = other.data(QtCore.Qt.ItemDataRole.UserRole)
        if own_value is not None and other_value is not None:
            return float(own_value) < float(other_value)
        return super().__lt__(other)


class MetricTable(QtWidgets.QTableWidget):
    def __init__(self, rate_name: str):
        super().__init__(0, 7)
        self.rate_name = rate_name
        self.setHorizontalHeaderLabels(
            ["Skill", "Share", rate_name, "Total", "Hits", "Crit %", "Max"]
        )
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 112)
        for column, width in ((2, 74), (3, 82), (4, 58), (5, 66), (6, 78)):
            header.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.Fixed
            )
            self.setColumnWidth(column, width)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)

    def update_metrics(self, metrics: Iterable[dict[str, Any]], elapsed: float) -> None:
        rows = sorted(
            (item for item in metrics if isinstance(item, dict)),
            key=lambda item: safe_float(item.get("total")),
            reverse=True,
        )
        total_sum = sum(max(0.0, safe_float(item.get("total"))) for item in rows)
        sorting = self.isSortingEnabled()
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))
        elapsed = max(elapsed, 0.001)
        for row, metric in enumerate(rows):
            total = safe_float(metric.get("total"))
            hits = safe_int(metric.get("hits"))
            crits = safe_int(metric.get("crits"))
            crit_pct = (crits / hits * 100.0) if hits else 0.0
            share = (total / total_sum * 100.0) if total_sum > 0 else 0.0
            skill_item = QtWidgets.QTableWidgetItem(
                str(metric.get("skill") or "Unknown")
            )
            self.setItem(row, 0, skill_item)

            contribution = QtWidgets.QProgressBar()
            contribution.setRange(0, 1000)
            contribution.setValue(round(share * 10))
            contribution.setFormat(f"{share:.1f}%")
            contribution.setTextVisible(True)
            contribution.setStyleSheet(
                "QProgressBar { background:#10171e; border:1px solid #2d3b48;"
                " border-radius:3px; text-align:center; color:#e6edf3; }"
                "QProgressBar::chunk { background:#3478b7; border-radius:2px; }"
            )
            self.setCellWidget(row, 1, contribution)

            values = (
                (total / elapsed, fmt_number(total / elapsed)),
                (total, fmt_number(total)),
                (hits, str(hits)),
                (crit_pct, f"{crit_pct:.1f}%"),
                (safe_float(metric.get("max")), fmt_number(metric.get("max"))),
            )
            for col, (numeric_value, text) in enumerate(values, start=2):
                item = NumericTableItem(text)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, numeric_value)
                item.setTextAlignment(
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                )
                self.setItem(row, col, item)
        self.setColumnWidth(1, 112)
        self.setSortingEnabled(sorting)


class CombatWindow(PersistentWindow):
    def __init__(self, settings: QtCore.QSettings):
        super().__init__(settings, "combat")
        self.setWindowTitle("Farever Atlas — Combat Meter")
        self.resize(760, 470)
        self.setMinimumSize(430, 240)
        self._latest_dps: dict[str, Any] = {}
        self._fight_id = -1
        self._baseline_elapsed = 0.0
        self._damage_baseline: dict[str, dict[str, float]] = {}
        self._healing_baseline: dict[str, dict[str, float]] = {}
        self._render_clock = QtCore.QElapsedTimer()
        self._render_clock.start()
        self._last_render_ms = -1000
        self._last_combat_state: bool | None = None

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(10, 9, 10, 8)
        layout.setSpacing(7)

        summary = QtWidgets.QHBoxLayout()
        self.combat_state = QtWidgets.QLabel("WAITING")
        self.combat_state.setStyleSheet(
            "font-size:12px; font-weight:700; color:#e0b96d"
        )
        self.duration = QtWidgets.QLabel("00:00")
        self.primary_rate = QtWidgets.QLabel("0 DPS")
        self.total = QtWidgets.QLabel("0 total")
        for label in (self.duration, self.primary_rate, self.total):
            label.setStyleSheet("font-size:12px; font-weight:600")
        summary.addWidget(self.combat_state)
        summary.addStretch(1)
        summary.addWidget(self.duration)
        summary.addSpacing(12)
        summary.addWidget(self.primary_rate)
        summary.addSpacing(12)
        summary.addWidget(self.total)
        layout.addLayout(summary)

        self.tabs = QtWidgets.QTabWidget()
        self.damage = MetricTable("DPS")
        self.healing = MetricTable("HPS")
        self.tabs.addTab(self.damage, "Damage")
        self.tabs.addTab(self.healing, "Healing")
        layout.addWidget(self.tabs, 1)

        controls = QtWidgets.QHBoxLayout()
        self.status = QtWidgets.QLabel("—")
        self.status.setStyleSheet("color:#8f9caa")
        self.reset_button = QtWidgets.QPushButton("Reset")
        self.compact_button = QtWidgets.QPushButton("Compact")
        self.compact_button.setCheckable(True)
        self.always_on_top = QtWidgets.QCheckBox("Always on top")
        controls.addWidget(self.status)
        controls.addStretch(1)
        controls.addWidget(self.reset_button)
        controls.addWidget(self.compact_button)
        controls.addWidget(self.always_on_top)
        layout.addLayout(controls)
        self.setCentralWidget(central)
        self.reset_button.clicked.connect(self._reset_current_view)
        self.compact_button.toggled.connect(self._set_compact)
        self.always_on_top.toggled.connect(self._set_always_on_top)
        self.apply_settings_preferences(initial=True)

    @staticmethod
    def _setting_bool(settings: QtCore.QSettings, key: str, default: bool = False) -> bool:
        value = settings.value(key, default)
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default

    def _refresh_interval_ms(self) -> int:
        return max(
            100,
            min(2000, safe_int(self._settings.value("combat/refresh_ms"), 500)),
        )

    @QtCore.Slot()
    def apply_settings_preferences(self, initial: bool = False) -> None:
        compact = self._setting_bool(self._settings, "combat/compact", False)
        always_on_top = self._setting_bool(
            self._settings, "combat/always_on_top", False
        )
        view = str(
            self._settings.value("combat/default_view", "damage") or "damage"
        ).lower()
        self.compact_button.blockSignals(True)
        self.compact_button.setChecked(compact)
        self.compact_button.blockSignals(False)
        self._set_compact(compact, persist=False)
        self.always_on_top.blockSignals(True)
        self.always_on_top.setChecked(always_on_top)
        self.always_on_top.blockSignals(False)
        self._set_always_on_top(always_on_top, persist=False)
        self.tabs.setCurrentIndex(1 if view == "healing" else 0)

    @staticmethod
    def _metric_baseline(
        metrics: Iterable[dict[str, Any]],
    ) -> dict[str, dict[str, float]]:
        return {
            str(item.get("skill") or "Unknown"): {
                "total": safe_float(item.get("total")),
                "hits": float(safe_int(item.get("hits"))),
                "crits": float(safe_int(item.get("crits"))),
            }
            for item in metrics
            if isinstance(item, dict)
        }

    @staticmethod
    def _after_baseline(
        metrics: Iterable[dict[str, Any]],
        baseline: dict[str, dict[str, float]],
    ) -> list[dict[str, Any]]:
        adjusted: list[dict[str, Any]] = []
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            skill = str(metric.get("skill") or "Unknown")
            old = baseline.get(skill, {})
            total = max(0.0, safe_float(metric.get("total")) - old.get("total", 0.0))
            hits = max(0, safe_int(metric.get("hits")) - round(old.get("hits", 0.0)))
            crits = max(0, safe_int(metric.get("crits")) - round(old.get("crits", 0.0)))
            if total <= 0.0 and hits <= 0:
                continue
            adjusted.append(
                {
                    "skill": skill,
                    "total": total,
                    "hits": hits,
                    "crits": crits,
                    "max": safe_float(metric.get("max")),
                }
            )
        return adjusted

    @QtCore.Slot()
    def _reset_current_view(self) -> None:
        dps = self._latest_dps
        self._baseline_elapsed = safe_float(dps.get("elapsed"))
        self._damage_baseline = self._metric_baseline(
            dps.get("damage_skills", []) or []
        )
        self._healing_baseline = self._metric_baseline(
            dps.get("healing_skills", []) or []
        )
        self._render_dps(dps)

    @QtCore.Slot(bool)
    def _set_compact(self, compact: bool, *, persist: bool = True) -> None:
        for table in (self.damage, self.healing):
            for column in range(3, 7):
                table.setColumnHidden(column, compact)
        self.status.setVisible(not compact)
        self.always_on_top.setVisible(not compact)
        self.reset_button.setVisible(not compact)
        if compact:
            self.resize(470, 280)
        if persist:
            self._settings.setValue("combat/compact", bool(compact))

    @QtCore.Slot(bool)
    def _set_always_on_top(self, enabled: bool, *, persist: bool = True) -> None:
        apply_always_on_top(self, enabled)
        if persist:
            self._settings.setValue("combat/always_on_top", bool(enabled))

    def _render_dps(self, dps: dict[str, Any]) -> None:
        elapsed = max(0.0, safe_float(dps.get("elapsed")) - self._baseline_elapsed)
        damage = self._after_baseline(
            dps.get("damage_skills", []) or [], self._damage_baseline
        )
        healing = self._after_baseline(
            dps.get("healing_skills", []) or [], self._healing_baseline
        )
        damage_total = sum(safe_float(item.get("total")) for item in damage)
        rate = damage_total / elapsed if elapsed > 0.0 else 0.0
        minutes, seconds = divmod(round(elapsed), 60)
        self.duration.setText(f"{minutes:02d}:{seconds:02d}")
        self.primary_rate.setText(f"{fmt_number(rate)} DPS")
        self.total.setText(f"{fmt_number(damage_total)} total")
        self.damage.update_metrics(damage, elapsed)
        self.healing.update_metrics(healing, elapsed)

        in_combat = bool(dps.get("in_combat"))
        has_encounter = bool(damage or healing or safe_int(dps.get("fight_id")) > 0)
        if in_combat:
            self.combat_state.setText("IN COMBAT")
            self.combat_state.setStyleSheet(
                "font-size:12px; font-weight:700; color:#ef806f"
            )
        elif has_encounter:
            self.combat_state.setText("ENCOUNTER COMPLETE")
            self.combat_state.setStyleSheet(
                "font-size:12px; font-weight:700; color:#74c991"
            )
        else:
            self.combat_state.setText("IDLE")
            self.combat_state.setStyleSheet(
                "font-size:12px; font-weight:700; color:#e0b96d"
            )

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._render_dps(self._latest_dps)
        self._last_render_ms = self._render_clock.elapsed()

    @QtCore.Slot(object)
    def update_snapshot(self, snapshot: Snapshot) -> None:
        state = snapshot.state or {}
        dps = state.get("dps", {}) or {}
        if not isinstance(dps, dict):
            dps = {}
        fight_id = safe_int(dps.get("fight_id"), 0)
        if self._fight_id >= 0 and fight_id != self._fight_id:
            self._baseline_elapsed = 0.0
            self._damage_baseline = {}
            self._healing_baseline = {}
        self._fight_id = fight_id
        self._latest_dps = dps
        self.status.setText(snapshot.message)
        if not self.isVisible():
            return
        now_ms = self._render_clock.elapsed()
        combat_state = bool(dps.get("in_combat"))
        if (
            combat_state != self._last_combat_state
            or now_ms - self._last_render_ms >= self._refresh_interval_ms()
        ):
            self._render_dps(dps)
            self._last_render_ms = now_ms
            self._last_combat_state = combat_state
