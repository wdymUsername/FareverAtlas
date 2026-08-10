"""Codex page: Collection + regional catalog with live progress."""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from .catalog import (
    CODEX_SUBCATEGORIES,
    COLLECTION_CATEGORIES,
    codex_unit_progress,
    collection_ids,
    completed_activity_ids,
    display_name_for,
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

        self.codex_mode_group.addButton(self.codex_collection_mode_button)
        self.codex_mode_group.addButton(self.codex_regions_mode_button)
        toolbar_layout.addWidget(self.codex_collection_mode_button)
        toolbar_layout.addWidget(self.codex_regions_mode_button)

        self.codex_category_combo = QtWidgets.QComboBox(self.codex_toolbar)
        self.codex_category_combo.setObjectName("codexNavCombo")
        self.codex_category_combo.setFixedHeight(28)
        self.codex_category_combo.setMinimumWidth(120)
        for category_id, label in COLLECTION_CATEGORIES:
            self.codex_category_combo.addItem(label, category_id)
        toolbar_layout.addWidget(self.codex_category_combo)

        self.codex_region_combo = QtWidgets.QComboBox(self.codex_toolbar)
        self.codex_region_combo.setObjectName("codexNavCombo")
        self.codex_region_combo.setFixedHeight(28)
        self.codex_region_combo.setMinimumWidth(180)
        for region in region_list:
            self.codex_region_combo.addItem(
                str(region.get("name") or region.get("id")),
                str(region.get("id")),
            )
        toolbar_layout.addWidget(self.codex_region_combo)

        self.codex_subcategory_combo = QtWidgets.QComboBox(self.codex_toolbar)
        self.codex_subcategory_combo.setObjectName("codexNavCombo")
        self.codex_subcategory_combo.setFixedHeight(28)
        self.codex_subcategory_combo.setMinimumWidth(110)
        for subcategory_id, label in CODEX_SUBCATEGORIES:
            self.codex_subcategory_combo.addItem(label, subcategory_id)
        toolbar_layout.addWidget(self.codex_subcategory_combo)

        toolbar_layout.addStretch(1)

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
        mode = "codex" if mode == "codex" else "collection"
        if self._codex_mode == mode:
            self.codex_collection_mode_button.setChecked(mode == "collection")
            self.codex_regions_mode_button.setChecked(mode == "codex")
            return
        self._codex_mode = mode
        self.codex_collection_mode_button.setChecked(mode == "collection")
        self.codex_regions_mode_button.setChecked(mode == "codex")
        self._sync_codex_toolbar_visibility()
        self._refresh_codex_list(force=True)

    def _sync_codex_toolbar_visibility(self) -> None:
        collection_mode = self._codex_mode == "collection"
        self.codex_category_combo.setVisible(collection_mode)
        self.codex_region_combo.setVisible(not collection_mode)
        self.codex_subcategory_combo.setVisible(not collection_mode)

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

    def _refresh_codex_list(self, *, force: bool = False) -> None:
        if not hasattr(self, "codex_browse"):
            return
        state = self._codex_snapshot_state()
        signature = self._codex_progress_signature_for(state)
        if not force and signature == self._codex_progress_signature:
            return
        self._codex_progress_signature = signature

        selected = self.codex_browse.selected_id
        if self._codex_mode == "collection":
            entries, summary, meta = self._build_collection_entries(state)
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
        )
        self.codex_summary_label.setText(summary)
        if self.codex_browse.selected_id:
            self._codex_entry_selected(self.codex_browse.selected_id)

    def _codex_entry_selected(self, entry_id: str) -> None:
        meta = self._codex_entry_meta.get(entry_id)
        if not meta:
            self.codex_browse.detail.clear()
            return
        self.codex_browse.detail.show_entry(
            str(meta.get("title") or entry_id),
            flavor=str(meta.get("flavor") or ""),
            kills_text=str(meta.get("kills_text") or ""),
            status_text=str(meta.get("status_text") or ""),
            mastered=bool(meta.get("mastered")),
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
                # Unrevealed: hide the real name in the grid tooltip/detail until known.
                display_title = title if revealed else "???"
                rows.append(
                    CodexEntry(
                        unit_id,
                        display_title,
                        overlay,
                        complete,
                        revealed,
                        unit_type_id(unit_id),
                        status,
                    )
                )
                meta[unit_id] = {
                    "title": display_title if revealed else "Unknown",
                    "flavor": "",
                    "kills_text": f"{kills} Killed" if revealed else "",
                    "status_text": (
                        "Mastered"
                        if complete
                        else (f"{min(kills, maximum)} / {maximum}" if revealed else "Locked")
                    ),
                    "mastered": complete,
                }
        else:
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
