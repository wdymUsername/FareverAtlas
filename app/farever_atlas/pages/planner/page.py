"""Planner page construction and build persistence."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ...config import ASSET_ROOT, PROJECT_ROOT, safe_int
from .widgets import (
    PlannerBuildLoadOverlay,
    PlannerClassSelector,
    PlannerClassSkillSlot,
    PlannerEquipmentSlot,
    PlannerStatRow,
    PlannerTalentTree,
)


class PlannerPageMixin:
    """Build planner UI, talent ranks, and saved-build overlays."""

    def _init_planner_page(self) -> None:
        # Context bar (shell-hosted) and body (page stack) are separate so the
        # shell can swap toolbars independently of page content.
        self.planner_toolbar = QtWidgets.QWidget()
        self.planner_toolbar.setObjectName("plannerToolbar")
        self.planner_toolbar.setFixedHeight(46)
        planner_toolbar_layout = QtWidgets.QHBoxLayout(self.planner_toolbar)
        planner_toolbar_layout.setContentsMargins(7, 0, 7, 0)
        planner_toolbar_layout.setSpacing(7)

        saved_level = max(
            1,
            min(30, safe_int(self._settings.value("planner/level", 1), 1)),
        )
        self.planner_level_value = saved_level
        self.planner_level = QtWidgets.QWidget()
        self.planner_level.setObjectName("plannerLevelSelector")
        self.planner_level.setToolTip("Build level")
        self.planner_level.setFixedSize(130, 32)
        level_layout = QtWidgets.QHBoxLayout(self.planner_level)
        level_layout.setContentsMargins(0, 0, 0, 0)
        level_layout.setSpacing(0)

        self.planner_level_combo = QtWidgets.QComboBox()
        self.planner_level_combo.setObjectName("plannerLevelCombo")
        self.planner_level_combo.setToolTip("Select build level")
        self.planner_level_combo.setFixedSize(102, 32)
        for level in range(1, 31):
            self.planner_level_combo.addItem(f"LEVEL {level}", level)
        self.planner_level_combo.setCurrentIndex(saved_level - 1)
        level_layout.addWidget(self.planner_level_combo)

        level_step_column = QtWidgets.QWidget()
        level_step_column.setObjectName("plannerLevelStepColumn")
        level_step_column.setFixedSize(28, 32)
        level_step_layout = QtWidgets.QVBoxLayout(level_step_column)
        level_step_layout.setContentsMargins(0, 0, 0, 0)
        level_step_layout.setSpacing(0)

        self.planner_level_plus = QtWidgets.QToolButton()
        self.planner_level_plus.setObjectName("plannerLevelPlusButton")
        self.planner_level_plus.setIcon(
            QtGui.QIcon(str(ASSET_ROOT / "level_plus.svg"))
        )
        self.planner_level_plus.setIconSize(QtCore.QSize(8, 8))
        self.planner_level_plus.setFixedSize(28, 16)
        self.planner_level_plus.setToolTip("Increase level")
        self.planner_level_plus.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        level_step_layout.addWidget(self.planner_level_plus)

        self.planner_level_minus = QtWidgets.QToolButton()
        self.planner_level_minus.setObjectName("plannerLevelMinusButton")
        self.planner_level_minus.setIcon(
            QtGui.QIcon(str(ASSET_ROOT / "level_minus.svg"))
        )
        self.planner_level_minus.setIconSize(QtCore.QSize(8, 8))
        self.planner_level_minus.setFixedSize(28, 16)
        self.planner_level_minus.setToolTip("Decrease level")
        self.planner_level_minus.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        level_step_layout.addWidget(self.planner_level_minus)
        level_layout.addWidget(level_step_column)

        planner_classes = (
            ("Warrior", "Warrior", "classWarrior.webp"),
            ("Mage", "Mage", "classMage.webp"),
            ("Priest", "Priest", "classPriest.webp"),
            ("Rogue", "Rogue", "classRogue.webp"),
        )
        saved_class = ""
        self.planner_class = PlannerClassSelector(
            self,
            planner_classes,
            saved_class,
            self.planner_toolbar,
        )
        self._settings.setValue("planner/class", "")

        self.planner_build_name = QtWidgets.QLineEdit()
        self.planner_build_name.setObjectName("plannerBuildName")
        self.planner_build_name.setPlaceholderText("Build name")
        self.planner_build_name.setToolTip("Name of this build")
        self.planner_build_name.setMaxLength(80)
        self.planner_build_name.setText(
            str(self._settings.value("planner/build_name", ""))
        )
        self.planner_build_name.setFixedSize(230, 32)

        self.planner_save = QtWidgets.QToolButton()
        self.planner_save.setObjectName("plannerSaveButton")
        self.planner_save.setText("Save")
        self.planner_save.setToolTip("Save this planner build")
        self.planner_save.setFixedSize(62, 32)
        self.planner_save.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._planner_pending_overwrite_path: Path | None = None

        self.planner_load = QtWidgets.QToolButton()
        self.planner_load.setObjectName("plannerLoadButton")
        self.planner_load.setText("Load")
        self.planner_load.setToolTip("Load a saved planner build")
        self.planner_load.setFixedSize(52, 32)
        self.planner_load.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        self.planner_reset = QtWidgets.QToolButton()
        self.planner_reset.setObjectName("plannerResetButton")
        self.planner_reset.setText("Reset")
        self.planner_reset.setToolTip("Reset planner build")
        self.planner_reset.setFixedSize(58, 32)
        self.planner_reset.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        planner_toolbar_layout.addWidget(self.planner_class)
        planner_toolbar_layout.addWidget(self.planner_level)
        planner_toolbar_layout.addWidget(self.planner_build_name)
        planner_toolbar_layout.addStretch(1)
        planner_toolbar_layout.addWidget(self.planner_load)
        planner_toolbar_layout.addWidget(self.planner_save)
        planner_toolbar_layout.addWidget(self.planner_reset)

        self.planner_body = QtWidgets.QWidget()
        self.planner_body.setObjectName("plannerPage")
        planner_layout = QtWidgets.QVBoxLayout(self.planner_body)
        planner_layout.setContentsMargins(0, 0, 0, 0)
        planner_layout.setSpacing(7)

        def set_planner_level(level: int) -> None:
            level = max(1, min(30, int(level)))
            self.planner_level_value = level
            if self.planner_level_combo.currentData() != level:
                self.planner_level_combo.setCurrentIndex(level - 1)
            self.planner_level_minus.setEnabled(level > 1)
            self.planner_level_plus.setEnabled(level < 30)
            self._settings.setValue("planner/level", level)

            if hasattr(self, "_normalize_planner_talent_ranks"):
                self._normalize_planner_talent_ranks()
                self._refresh_planner_talent_state()
            elif hasattr(self, "planner_talent_points_value"):
                self.planner_talent_points_value.setText(
                    str(max(0, level - 9))
                )

            if hasattr(self, "planner_class_skill_slots"):
                for skill_index, slot in (
                    self.planner_class_skill_slots.items()
                ):
                    unlock_level = (
                        self.planner_class_skill_unlock_levels[
                            skill_index
                        ]
                    )
                    unlocked = level >= unlock_level

                    # Do not disable the parent QToolButton: disabled
                    # parents also disable their child QLabel, which made
                    # the muted unlock note disappear under PySide6.
                    slot.setEnabled(True)
                    slot.setProperty("unlocked", unlocked)
                    slot.setProperty("locked", not unlocked)
                    slot.setProperty("unlockLevel", unlock_level)
                    slot.title_label.setProperty("locked", not unlocked)

                    if unlocked:
                        slot.setCursor(
                            QtCore.Qt.CursorShape.PointingHandCursor
                        )
                        slot.unlock_note.hide()
                        slot.setToolTip(
                            f"Class skill {skill_index} · "
                            f"unlocked at level {unlock_level}"
                        )
                    else:
                        slot.setCursor(
                            QtCore.Qt.CursorShape.ArrowCursor
                        )
                        slot.unlock_note.setText(
                            f"Unlocks at level {unlock_level}"
                        )
                        slot.unlock_note.show()
                        slot.setToolTip(
                            f"Class skill {skill_index} · "
                            f"unlocks at level {unlock_level}"
                        )
                    slot.style().unpolish(slot)
                    slot.style().polish(slot)
                    slot.title_label.style().unpolish(slot.title_label)
                    slot.title_label.style().polish(slot.title_label)
                    slot.title_label.update()

        self._planner_builds_dir = PROJECT_ROOT / "user_data" / "builds"
        self._planner_builds_dir.mkdir(parents=True, exist_ok=True)

        def planner_build_payload() -> dict[str, object]:
            return {
                "format": "farever-atlas-planner-build",
                "version": 1,
                "name": self.planner_build_name.text().strip(),
                "level": self.planner_level_value,
                "class": self.planner_class.current_class(),
                "talents": {
                    str(index): rank
                    for index, rank in getattr(
                        self,
                        "planner_talent_ranks",
                        {},
                    ).items()
                    if rank > 0
                },
            }

        def planner_build_filename(build_name: str) -> str:
            normalized_name = unicodedata.normalize("NFKD", build_name)
            ascii_name = normalized_name.encode(
                "ascii",
                "ignore",
            ).decode("ascii")
            # Whitespace becomes an underscore. Every other character outside
            # ASCII letters, digits, underscore, and hyphen is removed:
            # "Nyx's Bonker Priest" -> "nyxs_bonker_priest.json".
            slug = re.sub(r"\s+", "_", ascii_name.lower())
            slug = re.sub(r"[^a-z0-9_-]", "", slug)
            slug = re.sub(r"_+", "_", slug).strip("_-")
            return f"{slug or 'unnamed_build'}.json"

        def reset_planner_save_confirm() -> None:
            if self.planner_save.property("confirmOverwrite") is True:
                self.planner_save.setText("Save")
                self.planner_save.setToolTip("Save this planner build")
                self.planner_save.setProperty("confirmOverwrite", False)
                self.planner_save.style().unpolish(self.planner_save)
                self.planner_save.style().polish(self.planner_save)
            self._planner_pending_overwrite_path = None

        def write_planner_build(file_path: Path, *, created: bool) -> None:
            try:
                file_path.write_text(
                    json.dumps(planner_build_payload(), indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError as error:
                reset_planner_save_confirm()
                self.show_toast(f"Could not save build: {error}", kind="error")
                return
            reset_planner_save_confirm()
            label = self.planner_build_name.text().strip() or file_path.stem
            if created:
                self.show_toast(f"Build created: {label}")
            else:
                self.show_toast(f"Build updated: {label}")

        def save_planner_build() -> None:
            build_name = self.planner_build_name.text().strip()
            file_path = self._planner_builds_dir / planner_build_filename(build_name)
            existed = file_path.is_file()

            # New files save immediately. Existing files require a second click
            # on Save (now Confirm), matching the delete-confirmation pattern.
            if existed:
                if self._planner_pending_overwrite_path != file_path:
                    reset_planner_save_confirm()
                    self._planner_pending_overwrite_path = file_path
                    self.planner_save.setText("Confirm")
                    self.planner_save.setToolTip(
                        f"Click again to overwrite {file_path.name}"
                    )
                    self.planner_save.setProperty("confirmOverwrite", True)
                    self.planner_save.style().unpolish(self.planner_save)
                    self.planner_save.style().polish(self.planner_save)
                    return

            write_planner_build(file_path, created=not existed)

        def apply_planner_build(file_path: Path) -> None:
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError(
                        "The selected file does not contain a build object."
                    )

                level = max(1, min(30, int(payload.get("level", 1))))
                class_id = str(payload.get("class", ""))
                build_name = str(payload.get("name", ""))[:80]
                talent_ranks = payload.get("talents", {})
                if not isinstance(talent_ranks, dict):
                    talent_ranks = {}

                set_planner_level(level)
                if hasattr(self, "_set_planner_talent_ranks"):
                    self._set_planner_talent_ranks(talent_ranks)
                self.planner_class.set_class(class_id)
                self.planner_build_name.setText(build_name)
                self._settings.setValue("planner/build_name", build_name)
                self._set_planner_build_overlay_visible(False)
                label = build_name or file_path.stem.replace("_", " ")
                self.show_toast(f"Build loaded: {label}")
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                self.show_toast(f"Could not load build: {error}", kind="error")

        self._apply_planner_build = apply_planner_build

        def load_planner_build() -> None:
            self._set_planner_build_overlay_visible(True)

        def reset_planner() -> None:
            reset_planner_save_confirm()
            set_planner_level(1)
            if hasattr(self, "_reset_planner_talents"):
                self._reset_planner_talents()
            self.planner_class.reset()
            self.planner_build_name.clear()
            self._settings.setValue("planner/build_name", "")
            self.show_toast("Planner reset")

        self.planner_level_combo.currentIndexChanged.connect(
            lambda _index: set_planner_level(
                int(self.planner_level_combo.currentData() or 1)
            )
        )
        self.planner_level_minus.clicked.connect(
            lambda: set_planner_level(self.planner_level_value - 1)
        )
        self.planner_level_plus.clicked.connect(
            lambda: set_planner_level(self.planner_level_value + 1)
        )
        self.planner_class.classChanged.connect(
            lambda class_id: self._settings.setValue("planner/class", class_id)
        )
        self.planner_build_name.textChanged.connect(
            lambda _text: reset_planner_save_confirm()
        )
        self.planner_build_name.editingFinished.connect(
            lambda: self._settings.setValue(
                "planner/build_name", self.planner_build_name.text().strip()
            )
        )
        self.planner_save.clicked.connect(save_planner_build)
        self.planner_load.clicked.connect(load_planner_build)
        self.planner_reset.clicked.connect(reset_planner)
        set_planner_level(saved_level)

        self.planner_main_splitter = QtWidgets.QSplitter(
            QtCore.Qt.Orientation.Horizontal
        )
        self.planner_main_splitter.setObjectName("plannerMainSplitter")
        self.planner_main_splitter.setChildrenCollapsible(False)
        self.planner_main_splitter.setHandleWidth(7)

        self.planner_stats_panel = QtWidgets.QFrame()
        self.planner_stats_panel.setObjectName("plannerStatsPanel")
        self.planner_stats_panel.setMinimumWidth(230)
        stats_layout = QtWidgets.QVBoxLayout(self.planner_stats_panel)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(0)

        stats_header = QtWidgets.QLabel("STATS")
        stats_header.setObjectName("plannerPanelHeader")
        stats_header.setFixedHeight(34)
        stats_header.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        stats_layout.addWidget(stats_header)

        self.planner_stats_content = QtWidgets.QWidget()
        self.planner_stats_content.setObjectName("plannerStatsContent")
        self.planner_stats_content_layout = QtWidgets.QVBoxLayout(
            self.planner_stats_content
        )
        self.planner_stats_content_layout.setContentsMargins(12, 10, 12, 12)
        self.planner_stats_content_layout.setSpacing(5)

        self.planner_stat_values: dict[str, QtWidgets.QLabel] = {}

        primary_stats = (
            ("vitality", "Vitality", "0"),
            ("strength", "Strength", "0"),
            ("dexterity", "Dexterity", "0"),
            ("faith", "Faith", "0"),
            ("intellect", "Intellect", "0"),
        )
        derived_stats = (
            ("critical_chance", "Critical chance", "0%"),
            ("critical_bonus", "Critical bonus", "0%"),
            ("armor_penetration", "Armor penetration", "0%"),
            ("magic_penetration", "Magic penetration", "0%"),
            ("fervor", "Fervor", "0%"),
            ("block", "Block", "0%"),
            ("dodge_chance", "Dodge chance", "0%"),
            ("magic_mastery", "Magic mastery", "0%"),
            ("physical_mastery", "Physical mastery", "0%"),
            ("armor", "Armor", "0  (0%)"),
            ("max_health", "Max health", "0"),
            ("health_regen", "Health regen", "0"),
        )

        for stat_id, label, value in primary_stats:
            row = PlannerStatRow(label, value)
            self.planner_stats_content_layout.addWidget(row)
            self.planner_stat_values[stat_id] = row.value

        stat_divider = QtWidgets.QFrame()
        stat_divider.setObjectName("plannerStatsDivider")
        stat_divider.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        stat_divider.setFixedHeight(1)
        self.planner_stats_content_layout.addSpacing(3)
        self.planner_stats_content_layout.addWidget(stat_divider)
        self.planner_stats_content_layout.addSpacing(3)

        for stat_id, label, value in derived_stats:
            row = PlannerStatRow(label, value)
            self.planner_stats_content_layout.addWidget(row)
            self.planner_stat_values[stat_id] = row.value

        self.planner_stats_content_layout.addStretch(1)
        stats_layout.addWidget(self.planner_stats_content, 1)

        self.planner_equipment_splitter = QtWidgets.QSplitter(
            QtCore.Qt.Orientation.Vertical
        )
        self.planner_equipment_splitter.setObjectName(
            "plannerEquipmentSplitter"
        )
        self.planner_equipment_splitter.setChildrenCollapsible(False)
        self.planner_equipment_splitter.setHandleWidth(7)

        self.planner_armor_panel = QtWidgets.QFrame()
        self.planner_armor_panel.setObjectName("plannerArmorPanel")
        self.planner_armor_panel.setMinimumHeight(150)
        armor_layout = QtWidgets.QVBoxLayout(self.planner_armor_panel)
        armor_layout.setContentsMargins(0, 0, 0, 0)
        armor_layout.setSpacing(0)

        armor_header = QtWidgets.QLabel("ARMOR PIECES")
        armor_header.setObjectName("plannerPanelHeader")
        armor_header.setFixedHeight(34)
        armor_header.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        armor_layout.addWidget(armor_header)

        self.planner_armor_content = QtWidgets.QWidget()
        self.planner_armor_content.setObjectName("plannerArmorContent")
        self.planner_armor_content_layout = QtWidgets.QGridLayout(
            self.planner_armor_content
        )
        self.planner_armor_content_layout.setContentsMargins(12, 10, 12, 12)
        self.planner_armor_content_layout.setHorizontalSpacing(8)
        self.planner_armor_content_layout.setVerticalSpacing(8)
        self.planner_armor_content_layout.setColumnStretch(0, 1)
        self.planner_armor_content_layout.setColumnStretch(1, 1)

        armor_slots = (
            ("helmet", "Helmet", 0, 0),
            ("gloves", "Gloves", 0, 1),
            ("pendant", "Pendant", 1, 0),
            ("belt", "Belt", 1, 1),
            ("shoulders", "Shoulders", 2, 0),
            ("pants", "Pants", 2, 1),
            ("chest", "Chest", 3, 0),
            ("boots", "Boots", 3, 1),
            ("cape", "Cape", 4, 0),
            ("trinket", "Trinket", 4, 1),
            ("ring_left", "Ring", 5, 0),
            ("ring_right", "Ring", 5, 1),
        )
        self.planner_armor_slots: dict[str, PlannerEquipmentSlot] = {}
        for slot_id, label, row, column in armor_slots:
            slot = PlannerEquipmentSlot(label)
            slot.setProperty("slotId", slot_id)
            self.planner_armor_content_layout.addWidget(slot, row, column)
            self.planner_armor_slots[slot_id] = slot

        armor_layout.addWidget(self.planner_armor_content, 1)

        self.planner_weapons_panel = QtWidgets.QFrame()
        self.planner_weapons_panel.setObjectName("plannerWeaponsPanel")
        self.planner_weapons_panel.setMinimumHeight(130)
        weapons_layout = QtWidgets.QVBoxLayout(self.planner_weapons_panel)
        weapons_layout.setContentsMargins(0, 0, 0, 0)
        weapons_layout.setSpacing(0)

        weapons_header = QtWidgets.QLabel("WEAPONS")
        weapons_header.setObjectName("plannerPanelHeader")
        weapons_header.setFixedHeight(34)
        weapons_header.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        weapons_layout.addWidget(weapons_header)

        self.planner_weapons_content = QtWidgets.QWidget()
        self.planner_weapons_content.setObjectName("plannerWeaponsContent")
        self.planner_weapons_content_layout = QtWidgets.QGridLayout(
            self.planner_weapons_content
        )
        self.planner_weapons_content_layout.setContentsMargins(12, 10, 12, 12)
        self.planner_weapons_content_layout.setHorizontalSpacing(8)
        self.planner_weapons_content_layout.setVerticalSpacing(8)

        weapon_slots = (
            ("main_hand", "Main Hand", 0),
            ("offhand", "Offhand", 1),
            ("arsenal", "Arsenal", 2),
        )
        self.planner_weapon_slots: dict[str, PlannerEquipmentSlot] = {}
        for slot_id, label, column in weapon_slots:
            slot = PlannerEquipmentSlot(label)
            slot.setProperty("slotId", slot_id)
            self.planner_weapons_content_layout.addWidget(slot, 0, column)
            self.planner_weapons_content_layout.setColumnStretch(column, 1)
            self.planner_weapon_slots[slot_id] = slot

        weapons_layout.addWidget(self.planner_weapons_content, 1)

        self.planner_equipment_splitter.addWidget(self.planner_armor_panel)
        self.planner_equipment_splitter.addWidget(self.planner_weapons_panel)
        self.planner_equipment_splitter.setStretchFactor(0, 3)
        self.planner_equipment_splitter.setStretchFactor(1, 2)
        self.planner_equipment_splitter.setSizes((320, 220))

        self.planner_progression_panel = QtWidgets.QFrame()
        self.planner_progression_panel.setObjectName(
            "plannerProgressionPanel"
        )
        self.planner_progression_panel.setMinimumWidth(300)

        progression_layout = QtWidgets.QVBoxLayout(
            self.planner_progression_panel
        )
        progression_layout.setContentsMargins(0, 0, 0, 0)
        progression_layout.setSpacing(0)

        self.planner_progression_tabs = QtWidgets.QTabWidget()
        self.planner_progression_tabs.setObjectName(
            "plannerProgressionTabs"
        )
        self.planner_progression_tabs.setDocumentMode(True)
        self.planner_progression_tabs.tabBar().setExpanding(True)
        self.planner_progression_tabs.tabBar().setDrawBase(False)

        self.planner_progression_collapse_button = (
            QtWidgets.QToolButton()
        )
        self.planner_progression_collapse_button.setObjectName(
            "plannerProgressionCollapseButton"
        )
        self.planner_progression_collapse_button.setText("»")
        self.planner_progression_collapse_button.setToolTip(
            "Collapse Class Skills / Talents"
        )
        self.planner_progression_collapse_button.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self.planner_progression_collapse_button.setFixedSize(30, 32)
        self.planner_progression_tabs.setCornerWidget(
            self.planner_progression_collapse_button,
            QtCore.Qt.Corner.TopRightCorner,
        )

        self.planner_progression_expand_button = QtWidgets.QToolButton()
        self.planner_progression_expand_button.setObjectName(
            "plannerProgressionExpandButton"
        )
        self.planner_progression_expand_button.setText("«")
        self.planner_progression_expand_button.setToolTip(
            "Expand Class Skills / Talents"
        )
        self.planner_progression_expand_button.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self.planner_progression_expand_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.planner_progression_expand_button.hide()
        progression_layout.addWidget(
            self.planner_progression_expand_button,
            1,
        )

        self.planner_class_skills_panel = QtWidgets.QWidget()
        self.planner_class_skills_panel.setObjectName(
            "plannerClassSkillsPage"
        )
        class_skills_layout = QtWidgets.QVBoxLayout(
            self.planner_class_skills_panel
        )
        class_skills_layout.setContentsMargins(0, 0, 0, 0)
        class_skills_layout.setSpacing(0)

        self.planner_class_skills_scroll = QtWidgets.QScrollArea()
        self.planner_class_skills_scroll.setObjectName(
            "plannerClassSkillsScroll"
        )
        self.planner_class_skills_scroll.setWidgetResizable(True)
        self.planner_class_skills_scroll.setFrameShape(
            QtWidgets.QFrame.Shape.NoFrame
        )
        self.planner_class_skills_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.planner_class_skills_content = QtWidgets.QWidget()
        self.planner_class_skills_content.setObjectName(
            "plannerClassSkillsContent"
        )
        self.planner_class_skills_content_layout = QtWidgets.QVBoxLayout(
            self.planner_class_skills_content
        )
        self.planner_class_skills_content_layout.setContentsMargins(
            12, 10, 12, 12
        )
        self.planner_class_skills_content_layout.setSpacing(7)

        self.planner_class_skill_unlock_levels = {
            1: 1,
            2: 1,
            3: 1,
            4: 1,
            5: 3,
            6: 5,
            7: 7,
            8: 10,
            9: 15,
            10: 20,
            11: 30,
        }
        self.planner_class_skill_slots: dict[
            int, PlannerClassSkillSlot
        ] = {}
        for skill_index in range(1, 12):
            slot = PlannerClassSkillSlot(skill_index)
            slot.setProperty(
                "unlockLevel",
                self.planner_class_skill_unlock_levels[skill_index],
            )
            self.planner_class_skills_content_layout.addWidget(slot)
            self.planner_class_skill_slots[skill_index] = slot

        self.planner_class_skills_content_layout.addStretch(1)
        self.planner_class_skills_scroll.setWidget(
            self.planner_class_skills_content
        )
        class_skills_layout.addWidget(
            self.planner_class_skills_scroll,
            1,
        )

        self.planner_talents_panel = QtWidgets.QWidget()
        self.planner_talents_panel.setObjectName("plannerTalentsPage")
        talents_layout = QtWidgets.QVBoxLayout(self.planner_talents_panel)
        talents_layout.setContentsMargins(0, 0, 0, 0)
        talents_layout.setSpacing(0)

        talent_points_row = QtWidgets.QWidget()
        talent_points_row.setObjectName("plannerTalentPointsRow")
        talent_points_row.setFixedHeight(32)
        talent_points_layout = QtWidgets.QHBoxLayout(talent_points_row)
        talent_points_layout.setContentsMargins(10, 0, 10, 0)
        talent_points_layout.setSpacing(6)

        talent_points_caption = QtWidgets.QLabel(
            "Talent points available"
        )
        talent_points_caption.setObjectName("plannerTalentPointsCaption")
        talent_points_layout.addWidget(talent_points_caption, 1)

        self.planner_talent_points_value = QtWidgets.QLabel("0")
        self.planner_talent_points_value.setObjectName(
            "plannerTalentPointsValue"
        )
        self.planner_talent_points_value.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        talent_points_layout.addWidget(self.planner_talent_points_value)
        talents_layout.addWidget(talent_points_row)

        self.planner_talents_scroll = QtWidgets.QScrollArea()
        self.planner_talents_scroll.setObjectName("plannerTalentsScroll")
        self.planner_talents_scroll.setWidgetResizable(True)
        self.planner_talents_scroll.setFrameShape(
            QtWidgets.QFrame.Shape.NoFrame
        )
        self.planner_talents_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.planner_talents_content = QtWidgets.QWidget()
        self.planner_talents_content.setObjectName("plannerTalentsContent")
        self.planner_talents_content_layout = QtWidgets.QVBoxLayout(
            self.planner_talents_content
        )
        self.planner_talents_content_layout.setContentsMargins(
            8, 8, 8, 10
        )
        self.planner_talents_content_layout.setSpacing(0)

        self.planner_talent_tree = PlannerTalentTree()
        self.planner_talents_content_layout.addWidget(
            self.planner_talent_tree
        )
        self.planner_talents_content_layout.addStretch(1)

        self.planner_talent_buttons = (
            self.planner_talent_tree.talent_buttons
        )
        self.planner_talent_rank_labels = (
            self.planner_talent_tree.rank_labels
        )
        self.planner_talent_maximum_ranks = {
            index: int(button.property("maximumRank") or 1)
            for index, button in self.planner_talent_buttons.items()
        }
        self.planner_talent_ranks = {
            index: 0
            for index in self.planner_talent_buttons
        }

        def normalize_planner_talent_ranks() -> None:
            for index, maximum_rank in (
                self.planner_talent_maximum_ranks.items()
            ):
                try:
                    rank = int(self.planner_talent_ranks.get(index, 0))
                except (TypeError, ValueError):
                    rank = 0
                self.planner_talent_ranks[index] = max(
                    0,
                    min(maximum_rank, rank),
                )

            talent_point_budget = max(
                0,
                self.planner_level_value - 9,
            )
            excess = (
                sum(self.planner_talent_ranks.values())
                - talent_point_budget
            )
            if excess <= 0:
                return

            for index in sorted(
                self.planner_talent_ranks,
                reverse=True,
            ):
                if excess <= 0:
                    break
                removable = min(
                    excess,
                    self.planner_talent_ranks[index],
                )
                self.planner_talent_ranks[index] -= removable
                excess -= removable

        def refresh_planner_talent_state() -> None:
            spent_points = sum(self.planner_talent_ranks.values())
            talent_point_budget = max(
                0,
                self.planner_level_value - 9,
            )
            available_points = max(
                0,
                talent_point_budget - spent_points,
            )
            self.planner_talent_points_value.setText(
                str(available_points)
            )

            for index, button in self.planner_talent_buttons.items():
                rank = self.planner_talent_ranks[index]
                maximum_rank = self.planner_talent_maximum_ranks[index]
                self.planner_talent_rank_labels[index].setText(
                    f"{rank}/{maximum_rank}"
                )
                button.setProperty("ranked", rank > 0)
                button.setProperty(
                    "atMaximum",
                    rank >= maximum_rank,
                )
                button.setIcon(
                    button._talent_icon_ranked
                    if rank > 0
                    else button._talent_icon_unranked
                )
                button.setToolTip(
                    f"Talent {index}\n"
                    f"Rank {rank}/{maximum_rank}\n"
                    "Left click: assign point\n"
                    "Right click: remove point"
                )
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()

        def adjust_planner_talent_rank(
            index: int,
            change: int,
        ) -> None:
            current_rank = self.planner_talent_ranks[index]
            maximum_rank = self.planner_talent_maximum_ranks[index]

            if change > 0:
                talent_point_budget = max(
                    0,
                    self.planner_level_value - 9,
                )
                available_points = (
                    talent_point_budget
                    - sum(self.planner_talent_ranks.values())
                )
                if available_points <= 0 or current_rank >= maximum_rank:
                    return
                self.planner_talent_ranks[index] = current_rank + 1
            elif change < 0:
                if current_rank <= 0:
                    return
                self.planner_talent_ranks[index] = current_rank - 1
            else:
                return

            refresh_planner_talent_state()

        def set_planner_talent_ranks(
            raw_ranks: dict[object, object],
        ) -> None:
            for index in self.planner_talent_ranks:
                raw_value = raw_ranks.get(
                    str(index),
                    raw_ranks.get(index, 0),
                )
                try:
                    self.planner_talent_ranks[index] = int(raw_value)
                except (TypeError, ValueError):
                    self.planner_talent_ranks[index] = 0

            normalize_planner_talent_ranks()
            refresh_planner_talent_state()

        def reset_planner_talents() -> None:
            for index in self.planner_talent_ranks:
                self.planner_talent_ranks[index] = 0
            refresh_planner_talent_state()

        self._normalize_planner_talent_ranks = (
            normalize_planner_talent_ranks
        )
        self._refresh_planner_talent_state = (
            refresh_planner_talent_state
        )
        self._set_planner_talent_ranks = set_planner_talent_ranks
        self._reset_planner_talents = reset_planner_talents

        for index, button in self.planner_talent_buttons.items():
            button.clicked.connect(
                lambda _checked=False, talent_index=index:
                    adjust_planner_talent_rank(talent_index, 1)
            )
            button.setContextMenuPolicy(
                QtCore.Qt.ContextMenuPolicy.CustomContextMenu
            )
            button.customContextMenuRequested.connect(
                lambda _position, talent_index=index:
                    adjust_planner_talent_rank(talent_index, -1)
            )

        refresh_planner_talent_state()

        self.planner_talents_scroll.setWidget(
            self.planner_talents_content
        )
        talents_layout.addWidget(self.planner_talents_scroll, 1)

        self.planner_progression_tabs.addTab(
            self.planner_class_skills_panel,
            "CLASS SKILLS",
        )
        self.planner_progression_tabs.addTab(
            self.planner_talents_panel,
            "TALENTS",
        )
        progression_layout.addWidget(self.planner_progression_tabs, 1)

        self.planner_main_splitter.addWidget(self.planner_stats_panel)
        self.planner_main_splitter.addWidget(self.planner_equipment_splitter)
        self.planner_main_splitter.addWidget(
            self.planner_progression_panel
        )

        self.planner_main_splitter.setStretchFactor(0, 2)
        self.planner_main_splitter.setStretchFactor(1, 4)
        self.planner_main_splitter.setStretchFactor(2, 4)
        self.planner_main_splitter.setSizes((240, 430, 430))

        self._planner_progression_expanded_width = 430

        def set_progression_collapsed(collapsed: bool) -> None:
            sizes = self.planner_main_splitter.sizes()

            if collapsed:
                if len(sizes) >= 3:
                    self._planner_progression_expanded_width = max(
                        300,
                        sizes[2],
                    )
                self.planner_progression_tabs.hide()
                self.planner_progression_expand_button.show()
                self.planner_progression_panel.setMinimumWidth(36)
                self.planner_progression_panel.setMaximumWidth(36)
                return

            # QWIDGETSIZE_MAX is a Qt C++ macro and is not exported by
            # PySide6.QtWidgets. 16777215 is QWidget's standard maximum.
            self.planner_progression_panel.setMaximumWidth(16777215)
            self.planner_progression_panel.setMinimumWidth(300)
            self.planner_progression_expand_button.hide()
            self.planner_progression_tabs.show()

            sizes = self.planner_main_splitter.sizes()
            if len(sizes) >= 3:
                desired = self._planner_progression_expanded_width
                growth = max(0, desired - sizes[2])
                equipment_width = max(1, sizes[1] - growth)
                self.planner_main_splitter.setSizes(
                    (sizes[0], equipment_width, desired)
                )

        self.planner_progression_collapse_button.clicked.connect(
            lambda: set_progression_collapsed(True)
        )
        self.planner_progression_expand_button.clicked.connect(
            lambda: set_progression_collapsed(False)
        )

        # The first level refresh ran before these panels existed.
        # Refresh again now that talent points and class-skill slots do.
        set_planner_level(self.planner_level_value)

        planner_layout.addWidget(self.planner_main_splitter, 1)

        # Back-compat alias used by page switching before the shell context bar.
        self.planner_page = self.planner_body

    def _init_planner_build_overlay(self) -> None:
        self.planner_build_load_overlay = PlannerBuildLoadOverlay(
            self._planner_builds_dir,
            self,
        )
        self.planner_build_load_overlay.closeRequested.connect(
            lambda: self._set_planner_build_overlay_visible(False)
        )
        self.planner_build_load_overlay.buildSelected.connect(
            self._apply_planner_build
        )
        self.planner_build_load_overlay.hide()
        self._position_planner_build_overlay()

    def _set_planner_build_overlay_visible(self, visible: bool) -> None:
        if not hasattr(self, "planner_build_load_overlay"):
            return
        if visible:
            if hasattr(self, "main_navigation_overlay"):
                self._set_main_navigation_visible(False)
            self._set_waypoint_manager_visible(False)
            self._set_waypoint_edit_visible(False)
            self._set_waypoint_confirm_visible(False)
            self.planner_class.hide_popup()
            self._position_planner_build_overlay()
            self.planner_build_load_overlay.show_overlay()
        else:
            self.planner_build_load_overlay.hide()

    def _position_planner_build_overlay(self) -> None:
        if not hasattr(self, "planner_build_load_overlay"):
            return
        side_margin = 24
        top_margin = self.app_title_bar.height() + 14
        bottom_margin = 18
        available_width = max(0, self.width() - (side_margin * 2))
        available_height = max(0, self.height() - top_margin - bottom_margin)
        overlay_width = min(720, available_width)
        overlay_height = min(420, available_height)
        self.planner_build_load_overlay.setGeometry(
            max(side_margin, (self.width() - overlay_width) // 2),
            top_margin + max(0, (available_height - overlay_height) // 2),
            overlay_width,
            overlay_height,
        )


class PlannerPage:
    """Registered planner page: shared context bar + body hosted by the shell."""

    PAGE_ID = "planner"

    def __init__(self, context_bar, body) -> None:
        self.context_bar = context_bar
        self.body = body

    def on_activated(self) -> None:
        return None

    def on_deactivated(self) -> None:
        return None

