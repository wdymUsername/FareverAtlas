"""Codex page: Collection + regional catalog with live progress."""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from .catalog import (
    CODEX_SUBCATEGORIES,
    COLLECTION_CATEGORIES,
    all_dungeon_ids,
    codex_unit_progress,
    collection_ids,
    completed_activity_ids,
    display_name_for,
    drop_rows_for,
    drop_search_text_from_rows,
    drop_sections_for,
    dungeon_description_for,
    dungeon_header_path_for,
    load_codex_catalog,
    ordered_type_ids,
    owned_collection_ids,
    region_entry_ids,
    regions,
    unit_codex_status,
    unit_kill_max,
    unit_tile_progress,
    unit_type_id,
)
from .widgets import CodexBrowsePanel, CodexEntry

_CODEX_MODES = ("collection", "codex", "dungeons")


class CodexPageMixin:
    """Codex page construction and snapshot-driven browse refresh."""

    def _init_codex_page(self) -> None:
        self._codex_catalog = load_codex_catalog()
        self._codex_mode = "collection"
        self._codex_collection_category = "mounts"
        self._codex_region_id = "Z1"
        self._codex_subcategory = "monsters"
        self._codex_progress_signature: tuple[Any, ...] | None = None
        self._codex_entry_meta: dict[str, dict[str, Any]] = {}

        region_list = regions(self._codex_catalog)
        if region_list:
            self._codex_region_id = str(region_list[0].get("id") or "Z1")

        self.codex_toolbar = QtWidgets.QWidget()
        self.codex_toolbar.setObjectName("codexToolbar")
        self.codex_toolbar.setFixedHeight(46)
        toolbar_layout = QtWidgets.QHBoxLayout(self.codex_toolbar)
        toolbar_layout.setContentsMargins(7, 0, 7, 0)
        toolbar_layout.setSpacing(7)

        self.codex_mode_group = QtWidgets.QButtonGroup(self.codex_toolbar)
        self.codex_mode_group.setExclusive(True)

        self.codex_collection_mode_button = QtWidgets.QToolButton(self.codex_toolbar)
        self.codex_collection_mode_button.setObjectName("codexModeButton")
        self.codex_collection_mode_button.setText("Collection")
        self.codex_collection_mode_button.setCheckable(True)
        self.codex_collection_mode_button.setChecked(True)
        self.codex_collection_mode_button.setFixedHeight(28)
        self.codex_collection_mode_button.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )

        self.codex_regions_mode_button = QtWidgets.QToolButton(self.codex_toolbar)
        self.codex_regions_mode_button.setObjectName("codexModeButton")
        self.codex_regions_mode_button.setText("Codex")
        self.codex_regions_mode_button.setCheckable(True)
        self.codex_regions_mode_button.setFixedHeight(28)
        self.codex_regions_mode_button.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )

        self.codex_dungeons_mode_button = QtWidgets.QToolButton(self.codex_toolbar)
        self.codex_dungeons_mode_button.setObjectName("codexModeButton")
        self.codex_dungeons_mode_button.setText("Dungeons")
        self.codex_dungeons_mode_button.setCheckable(True)
        self.codex_dungeons_mode_button.setFixedHeight(28)
        self.codex_dungeons_mode_button.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )

        self.codex_mode_group.addButton(self.codex_collection_mode_button)
        self.codex_mode_group.addButton(self.codex_regions_mode_button)
        self.codex_mode_group.addButton(self.codex_dungeons_mode_button)
        toolbar_layout.addWidget(self.codex_collection_mode_button)
        toolbar_layout.addWidget(self.codex_regions_mode_button)
        toolbar_layout.addWidget(self.codex_dungeons_mode_button)

        # Mode-specific nav lives in a stack so show/hide never reflows the bar.
        self.codex_nav_stack = QtWidgets.QStackedWidget(self.codex_toolbar)
        self.codex_nav_stack.setObjectName("codexNavStack")
        self.codex_nav_stack.setFixedHeight(28)

        collection_nav = QtWidgets.QWidget()
        collection_nav_layout = QtWidgets.QHBoxLayout(collection_nav)
        collection_nav_layout.setContentsMargins(0, 0, 0, 0)
        collection_nav_layout.setSpacing(7)
        self.codex_category_combo = QtWidgets.QComboBox(collection_nav)
        self.codex_category_combo.setObjectName("codexNavCombo")
        self.codex_category_combo.setFixedHeight(28)
        self.codex_category_combo.setMinimumWidth(120)
        for category_id, label in COLLECTION_CATEGORIES:
            self.codex_category_combo.addItem(label, category_id)
        collection_nav_layout.addWidget(self.codex_category_combo)
        collection_nav_layout.addStretch(1)

        codex_nav = QtWidgets.QWidget()
        codex_nav_layout = QtWidgets.QHBoxLayout(codex_nav)
        codex_nav_layout.setContentsMargins(0, 0, 0, 0)
        codex_nav_layout.setSpacing(7)
        self.codex_region_combo = QtWidgets.QComboBox(codex_nav)
        self.codex_region_combo.setObjectName("codexNavCombo")
        self.codex_region_combo.setFixedHeight(28)
        self.codex_region_combo.setMinimumWidth(180)
        for region in region_list:
            self.codex_region_combo.addItem(
                str(region.get("name") or region.get("id")),
                str(region.get("id")),
            )
        codex_nav_layout.addWidget(self.codex_region_combo)
        self.codex_subcategory_combo = QtWidgets.QComboBox(codex_nav)
        self.codex_subcategory_combo.setObjectName("codexNavCombo")
        self.codex_subcategory_combo.setFixedHeight(28)
        self.codex_subcategory_combo.setMinimumWidth(110)
        for subcategory_id, label in CODEX_SUBCATEGORIES:
            self.codex_subcategory_combo.addItem(label, subcategory_id)
        codex_nav_layout.addWidget(self.codex_subcategory_combo)
        codex_nav_layout.addStretch(1)

        dungeons_nav = QtWidgets.QWidget()
        dungeons_nav_layout = QtWidgets.QHBoxLayout(dungeons_nav)
        dungeons_nav_layout.setContentsMargins(0, 0, 0, 0)
        dungeons_nav_layout.addStretch(1)

        self.codex_nav_stack.addWidget(collection_nav)  # 0
        self.codex_nav_stack.addWidget(codex_nav)  # 1
        self.codex_nav_stack.addWidget(dungeons_nav)  # 2
        self.codex_nav_stack.setMinimumWidth(300)
        toolbar_layout.addWidget(self.codex_nav_stack, 1)

        self.codex_summary_label = QtWidgets.QLabel("")
        self.codex_summary_label.setObjectName("codexSummaryLabel")
        self.codex_summary_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        toolbar_layout.addWidget(self.codex_summary_label)

        self.codex_body = QtWidgets.QWidget()
        self.codex_body.setObjectName("codexPage")
        body_layout = QtWidgets.QVBoxLayout(self.codex_body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(0)

        self.codex_browse = CodexBrowsePanel(self.codex_body)
        body_layout.addWidget(self.codex_browse, 1)

        self.codex_collection_mode_button.clicked.connect(
            lambda: self._set_codex_mode("collection")
        )
        self.codex_regions_mode_button.clicked.connect(
            lambda: self._set_codex_mode("codex")
        )
        self.codex_dungeons_mode_button.clicked.connect(
            lambda: self._set_codex_mode("dungeons")
        )
        self.codex_category_combo.currentIndexChanged.connect(
            self._codex_collection_category_changed
        )
        self.codex_region_combo.currentIndexChanged.connect(
            self._codex_region_changed
        )
        self.codex_subcategory_combo.currentIndexChanged.connect(
            self._codex_subcategory_changed
        )
        self.codex_browse.entrySelected.connect(self._codex_entry_selected)

        self._sync_codex_toolbar_visibility()
        self._refresh_codex_list(force=True)

    def _set_codex_mode(self, mode: str) -> None:
        if mode not in _CODEX_MODES:
            mode = "collection"
        if self._codex_mode == mode:
            self._sync_codex_mode_buttons()
            return
        self._codex_mode = mode
        self._sync_codex_mode_buttons()
        self._sync_codex_toolbar_visibility()
        if hasattr(self, "codex_browse"):
            self.codex_browse.filter_popup.hide()
            self.codex_browse.filter_button.setChecked(False)
            self.codex_browse.filter_popup.clear_filters()
            self.codex_browse.search_edit.blockSignals(True)
            self.codex_browse.search_edit.clear()
            self.codex_browse.search_edit.blockSignals(False)
        self._refresh_codex_list(force=True, reset_selection=True)

    def _sync_codex_mode_buttons(self) -> None:
        self.codex_collection_mode_button.setChecked(self._codex_mode == "collection")
        self.codex_regions_mode_button.setChecked(self._codex_mode == "codex")
        self.codex_dungeons_mode_button.setChecked(self._codex_mode == "dungeons")

    def _sync_codex_toolbar_visibility(self) -> None:
        index = {"collection": 0, "codex": 1, "dungeons": 2}.get(self._codex_mode, 0)
        self.codex_nav_stack.setCurrentIndex(index)
        if hasattr(self, "codex_browse"):
            if self._codex_mode == "dungeons":
                self.codex_browse.search_edit.setPlaceholderText(
                    "Search dungeons or items …"
                )
            else:
                self.codex_browse.search_edit.setPlaceholderText("Search …")

    def _codex_collection_category_changed(self, _index: int = 0) -> None:
        category = self.codex_category_combo.currentData()
        if not category:
            return
        self._codex_collection_category = str(category)
        self._refresh_codex_list(force=True)

    def _codex_region_changed(self, _index: int = 0) -> None:
        region_id = self.codex_region_combo.currentData()
        if not region_id:
            return
        self._codex_region_id = str(region_id)
        self._refresh_codex_list(force=True)

    def _codex_subcategory_changed(self, _index: int = 0) -> None:
        subcategory = self.codex_subcategory_combo.currentData()
        if not subcategory:
            return
        self._codex_subcategory = str(subcategory)
        self._refresh_codex_list(force=True)

    def _codex_snapshot_state(self) -> dict[str, Any]:
        snapshot = getattr(self, "latest_snapshot", None)
        state = getattr(snapshot, "state", None) if snapshot is not None else None
        return state if isinstance(state, dict) else {}

    def _codex_progress_signature_for(self, state: dict[str, Any]) -> tuple[Any, ...]:
        collection = state.get("collection") if isinstance(state.get("collection"), dict) else {}
        units = state.get("codex_units") if isinstance(state.get("codex_units"), dict) else {}
        activities = state.get("completed_activities")
        activity_sig = tuple(
            sorted(str(value) for value in activities)
        ) if isinstance(activities, list) else ()
        return (
            self._codex_mode,
            self._codex_collection_category,
            self._codex_region_id,
            self._codex_subcategory,
            tuple(
                sorted(str(value) for value in (collection.get("mounts") or []))
            ),
            tuple(
                sorted(str(value) for value in (collection.get("gliders") or []))
            ),
            tuple(
                sorted(str(value) for value in (collection.get("pets") or []))
            ),
            tuple(
                sorted(str(value) for value in (collection.get("gears") or []))
            ),
            tuple(
                sorted(
                    (str(unit_id), int(entry.get("kills") or 0), int(entry.get("rank") or 0))
                    for unit_id, entry in units.items()
                    if isinstance(entry, dict)
                )
            ),
            activity_sig,
        )

    def update_codex_from_snapshot(self, snapshot: Any = None) -> None:
        if snapshot is not None:
            pass
        self._refresh_codex_list(force=False)

    def _refresh_codex_list(
        self, *, force: bool = False, reset_selection: bool = False
    ) -> None:
        if not hasattr(self, "codex_browse"):
            return
        state = self._codex_snapshot_state()
        signature = self._codex_progress_signature_for(state)
        if not force and signature == self._codex_progress_signature:
            return
        self._codex_progress_signature = signature

        selected = None if reset_selection else self.codex_browse.selected_id
        if self._codex_mode == "collection":
            entries, summary, meta = self._build_collection_entries(state)
        elif self._codex_mode == "dungeons":
            entries, summary, meta = self._build_dungeon_entries(state)
        else:
            entries, summary, meta = self._build_region_entries(state)

        self._codex_entry_meta = meta
        type_ids = ordered_type_ids(
            {entry.type_id for entry in entries if entry.type_id}
        )
        self.codex_browse.set_entries(
            entries,
            type_ids=type_ids,
            select_id=selected,
            columns=4,
            show_titles=True,
        )
        self.codex_summary_label.setText(summary)
        # Detail is refreshed via CodexBrowsePanel.entrySelected from set_entries.

    def _codex_entry_selected(self, entry_id: str) -> None:
        meta = self._codex_entry_meta.get(entry_id)
        if not meta:
            self.codex_browse.detail.clear()
            return
        drop_sections = meta.get("drop_sections")
        if not isinstance(drop_sections, list):
            drop_sections = drop_sections_for(entry_id)
        drop_rows = meta.get("drop_rows")
        if not isinstance(drop_rows, list):
            drop_rows = drop_rows_for(entry_id)
        header = meta.get("header_path")
        completion = meta.get("completion")
        self.codex_browse.detail.show_entry(
            str(meta.get("title") or entry_id),
            flavor=str(meta.get("flavor") or ""),
            kills_text=str(meta.get("kills_text") or ""),
            status_text=str(meta.get("status_text") or ""),
            mastered=bool(meta.get("mastered")),
            show_status=bool(meta.get("show_status", True)),
            completion=bool(completion) if completion is not None else None,
            header_path=str(header) if header else None,
            drop_rows=[row for row in drop_rows if isinstance(row, dict)],
            drop_sections=drop_sections if isinstance(drop_sections, list) else None,
        )

    def _build_collection_entries(
        self,
        state: dict[str, Any],
    ) -> tuple[list[CodexEntry], str, dict[str, dict[str, Any]]]:
        category = self._codex_collection_category
        ids = collection_ids(category, self._codex_catalog)
        owned = owned_collection_ids(state, category)
        rows: list[CodexEntry] = []
        meta: dict[str, dict[str, Any]] = {}
        owned_count = 0
        for entry_id in ids:
            is_owned = entry_id in owned
            if is_owned:
                owned_count += 1
            title = display_name_for(entry_id, kind="collection")
            status = "mastered" if is_owned else "unknown"
            rows.append(
                CodexEntry(
                    entry_id,
                    title,
                    "",
                    is_owned,
                    True,  # collection shows silhouettes for missing entries
                    "",
                    status,
                )
            )
            meta[entry_id] = {
                "title": title,
                "flavor": "",
                "kills_text": "Owned" if is_owned else "Not owned",
                "status_text": "Collected" if is_owned else "Missing",
                "mastered": is_owned,
                "drop_rows": [],
            }
        rows.sort(key=lambda row: (row.complete, row.title.lower()))
        summary = f"{owned_count} / {len(ids)}"
        return rows, summary, meta

    def _build_region_entries(
        self,
        state: dict[str, Any],
    ) -> tuple[list[CodexEntry], str, dict[str, dict[str, Any]]]:
        subcategory = self._codex_subcategory
        ids = region_entry_ids(
            self._codex_region_id,
            subcategory,
            self._codex_catalog,
        )
        rows: list[CodexEntry] = []
        meta: dict[str, dict[str, Any]] = {}
        done_count = 0

        if subcategory == "monsters":
            for unit_id in ids:
                kills, rank = codex_unit_progress(state, unit_id)
                maximum = unit_kill_max(unit_id, self._codex_catalog)
                overlay, complete, revealed = unit_tile_progress(
                    unit_id, kills, rank, self._codex_catalog
                )
                status = unit_codex_status(
                    unit_id, kills, rank, self._codex_catalog
                )
                if complete:
                    done_count += 1
                title = display_name_for(unit_id, kind="monster")
                rows.append(
                    CodexEntry(
                        unit_id,
                        title,
                        overlay,
                        complete,
                        revealed,
                        unit_type_id(unit_id),
                        status,
                    )
                )
                meta[unit_id] = {
                    "title": title,
                    "flavor": "",
                    "kills_text": f"{kills} Killed" if revealed else "",
                    "status_text": (
                        "Mastered"
                        if complete
                        else (f"{min(kills, maximum)} / {maximum}" if revealed else "Locked")
                    ),
                    "mastered": complete,
                    "drop_rows": drop_rows_for(unit_id) if revealed else [],
                }
        else:
            # Activities (dungeons live in the top-level Dungeons mode).
            completed = completed_activity_ids(state)
            for entry_id in ids:
                complete = entry_id in completed
                if complete:
                    done_count += 1
                title = display_name_for(entry_id, kind="auto")
                status = "mastered" if complete else "unknown"
                rows.append(
                    CodexEntry(
                        entry_id,
                        title,
                        "",
                        complete,
                        True,
                        "",
                        status,
                    )
                )
                meta[entry_id] = {
                    "title": title,
                    "flavor": "",
                    "kills_text": "Completed" if complete else "Not completed",
                    "status_text": "Done" if complete else "Open",
                    "mastered": complete,
                    "drop_rows": [],
                }

        rows.sort(key=lambda row: (row.complete, row.title.lower()))
        summary = f"{done_count} / {len(ids)}"
        return rows, summary, meta

    def _build_dungeon_entries(
        self,
        state: dict[str, Any],
    ) -> tuple[list[CodexEntry], str, dict[str, dict[str, Any]]]:
        ids = all_dungeon_ids(self._codex_catalog)
        completed = completed_activity_ids(state)
        rows: list[CodexEntry] = []
        meta: dict[str, dict[str, Any]] = {}
        done_count = 0
        for entry_id in ids:
            complete = entry_id in completed
            if complete:
                done_count += 1
            title = display_name_for(entry_id, kind="dungeon")
            status = "mastered" if complete else "unknown"
            drop_sections = drop_sections_for(entry_id)
            drop_rows = drop_rows_for(entry_id)
            header = dungeon_header_path_for(entry_id)
            rows.append(
                CodexEntry(
                    entry_id,
                    title,
                    "",
                    complete,
                    True,
                    "",
                    status,
                    drop_search_text_from_rows(drop_rows),
                )
            )
            meta[entry_id] = {
                "title": title,
                "flavor": dungeon_description_for(entry_id),
                "kills_text": "",
                "status_text": "",
                "show_status": False,
                "completion": complete,
                "mastered": complete,
                "header_path": str(header) if header else "",
                "drop_rows": drop_rows,
                "drop_sections": drop_sections,
            }

        rows.sort(key=lambda row: (row.complete, row.title.lower()))
        summary = f"{done_count} / {len(ids)}"
        return rows, summary, meta


class CodexPage:
    """Registered codex page: shared context bar + body hosted by the shell."""

    PAGE_ID = "codex"

    def __init__(self, context_bar, body) -> None:
        self.context_bar = context_bar
        self.body = body

    def on_activated(self) -> None:
        return None

    def on_deactivated(self) -> None:
        return None
