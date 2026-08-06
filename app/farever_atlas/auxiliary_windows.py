"""Optional player, target, party, and combat windows."""

from __future__ import annotations

import math
from typing import Any, Iterable

from PySide6 import QtCore, QtGui, QtWidgets

from .config import (
    cardinal,
    fmt_hp,
    fmt_number,
    map_heading_degrees,
    safe_float,
    safe_int,
)
from .pages.map.data import Snapshot
from .window_base import PersistentWindow


class StatusWindow(PersistentWindow):
    def __init__(self, settings: QtCore.QSettings):
        super().__init__(settings, "status")
        self.setWindowTitle("Farever Atlas — Player / Target")
        self.resize(520, 520)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        self.connection = QtWidgets.QLabel("Waiting for bridge output")
        self.connection.setStyleSheet("font-weight: 600")
        layout.addWidget(self.connection)

        player_box = QtWidgets.QGroupBox("Player")
        player_layout = QtWidgets.QFormLayout(player_box)
        self.identity = QtWidgets.QLabel("—")
        self.position = QtWidgets.QLabel("—")
        self.heading = QtWidgets.QLabel("—")
        self.hp = QtWidgets.QProgressBar()
        self.hp.setRange(0, 1000)
        self.resources = QtWidgets.QLabel("—")
        player_layout.addRow("Identity", self.identity)
        player_layout.addRow("Position", self.position)
        player_layout.addRow("Heading", self.heading)
        player_layout.addRow("Health", self.hp)
        player_layout.addRow("Resources", self.resources)
        layout.addWidget(player_box)

        target_box = QtWidgets.QGroupBox("Target")
        target_layout = QtWidgets.QFormLayout(target_box)
        self.target_name = QtWidgets.QLabel("None")
        self.target_hp = QtWidgets.QProgressBar()
        self.target_hp.setRange(0, 1000)
        self.target_cast = QtWidgets.QProgressBar()
        self.target_cast.setRange(0, 1000)
        target_layout.addRow("Target", self.target_name)
        target_layout.addRow("Health", self.target_hp)
        target_layout.addRow("Cast", self.target_cast)
        layout.addWidget(target_box)

        party_box = QtWidgets.QGroupBox("Party")
        party_layout = QtWidgets.QVBoxLayout(party_box)
        self.party = QtWidgets.QTableWidget(0, 4)
        self.party.setHorizontalHeaderLabels(["Name", "Class", "HP", "Distance"])
        self.party.horizontalHeader().setStretchLastSection(True)
        self.party.verticalHeader().setVisible(False)
        self.party.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        party_layout.addWidget(self.party)
        layout.addWidget(party_box, 1)
        self.setCentralWidget(central)

    @QtCore.Slot(object)
    def update_snapshot(self, snapshot: Snapshot) -> None:
        self.connection.setText(snapshot.message)
        state = snapshot.state or {}
        player = state.get("player", {}) or {}
        name = player.get("name") or "Unknown"
        klass = player.get("class") or "Unknown class"
        self.identity.setText(f"{name} — {klass}, level {safe_int(player.get('level'))}")
        self.position.setText(
            f"X {safe_float(player.get('x')):.2f}, "
            f"Y {safe_float(player.get('y')):.2f}, "
            f"Z {safe_float(player.get('z')):.2f}"
        )
        degrees = map_heading_degrees(player.get("heading"))
        self.heading.setText(f"{degrees:.1f}° {cardinal(degrees)}")
        hp_pct = max(0.0, min(1.0, safe_float(player.get("hp_pct"))))
        self.hp.setValue(round(hp_pct * 1000))
        self.hp.setFormat(
            f"{fmt_number(player.get('hp'))} / {fmt_number(player.get('max_hp'))}  "
            f"({hp_pct * 100:.1f}%)"
        )
        self.resources.setText(
            f"Shield {fmt_number(player.get('shield'))}   "
            f"Energy {fmt_number(player.get('energy'))}"
        )

        target = state.get("target", {}) or {}
        if target.get("exists"):
            self.target_name.setText(
                f"{target.get('name') or 'Unknown'} — level {safe_int(target.get('level'))}"
            )
            target_pct = max(0.0, min(1.0, safe_float(target.get("hp_pct"))))
            self.target_hp.setValue(round(target_pct * 1000))
            self.target_hp.setFormat(
                f"{fmt_number(target.get('hp'))} / {fmt_number(target.get('max_hp'))}  "
                f"({target_pct * 100:.1f}%)"
            )
            if target.get("is_casting"):
                cast_pct = max(0.0, min(1.0, safe_float(target.get("cast_progress"))))
                self.target_cast.setValue(round(cast_pct * 1000))
                self.target_cast.setFormat(
                    f"{target.get('cast_skill') or 'Casting'} — "
                    f"{safe_float(target.get('cast_remaining')):.1f}s"
                )
            else:
                self.target_cast.setValue(0)
                self.target_cast.setFormat("Idle")
        else:
            self.target_name.setText("None")
            self.target_hp.setValue(0)
            self.target_hp.setFormat("—")
            self.target_cast.setValue(0)
            self.target_cast.setFormat("—")

        party = [item for item in (state.get("party", []) or []) if isinstance(item, dict)]
        self.party.setRowCount(len(party))
        px, py = safe_float(player.get("x")), safe_float(player.get("y"))
        for row, member in enumerate(party):
            hp = safe_float(member.get("hp"))
            max_hp = safe_float(member.get("max_hp"))
            hp_text = f"{fmt_hp(hp)} / {fmt_hp(max_hp)}" if max_hp > 0 else "—"
            distance = math.hypot(
                safe_float(member.get("x")) - px,
                safe_float(member.get("y")) - py,
            )
            values = (
                str(member.get("name") or "Unknown"),
                str(member.get("class") or ""),
                hp_text,
                f"{distance:.1f} m",
            )
            for col, value in enumerate(values):
                self.party.setItem(row, col, QtWidgets.QTableWidgetItem(value))
        self.party.resizeColumnsToContents()


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
    def _set_compact(self, compact: bool) -> None:
        for table in (self.damage, self.healing):
            for column in range(3, 7):
                table.setColumnHidden(column, compact)
        self.status.setVisible(not compact)
        self.always_on_top.setVisible(not compact)
        self.reset_button.setVisible(not compact)
        if compact:
            self.resize(470, 280)

    @QtCore.Slot(bool)
    def _set_always_on_top(self, enabled: bool) -> None:
        self.setWindowFlag(
            QtCore.Qt.WindowType.WindowStaysOnTopHint, enabled
        )
        self.show()

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
            or now_ms - self._last_render_ms >= 500
        ):
            self._render_dps(dps)
            self._last_render_ms = now_ms
            self._last_combat_state = combat_state
