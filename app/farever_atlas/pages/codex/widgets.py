"""Codex browse layout: tile grid + detail panel (in-game structure)."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PySide6 import QtCore, QtGui, QtWidgets

from .catalog import (
    CODEX_STATUS_FILTERS,
    ordered_type_ids,
    portrait_path_for,
    unit_type_label,
)

_PORTRAIT_CACHE: dict[tuple[str, str], QtGui.QPixmap] = {}

# Fixed cell size; column count wraps with available width.
TILE_SIZE = 140
PORTRAIT_SIZE = 96
TILE_SPACING = 8
GRID_SPLIT_LEFT = 2
GRID_SPLIT_RIGHT = 1


def _load_portrait_pixmap(path: Path, *, mode: str) -> QtGui.QPixmap | None:
    key = (str(path), mode)
    cached = _PORTRAIT_CACHE.get(key)
    if cached is not None and not cached.isNull():
        return cached
    pixmap = QtGui.QPixmap(str(path))
    if pixmap.isNull():
        return None
    if mode == "silhouette":
        sil = QtGui.QPixmap(pixmap.size())
        sil.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(sil)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
        )
        painter.fillRect(sil.rect(), QtGui.QColor(52, 64, 76, 255))
        painter.end()
        pixmap = sil
    _PORTRAIT_CACHE[key] = pixmap
    return pixmap


class CodexEntry(NamedTuple):
    id: str
    title: str
    progress: str
    complete: bool
    revealed: bool
    type_id: str = ""
    status: str = "unknown"


class CodexTile(QtWidgets.QPushButton):
    """Clickable codex cell (QPushButton so child layout + paint both work)."""

    def __init__(
        self,
        entry_id: str,
        title: str,
        progress_text: str,
        *,
        complete: bool,
        revealed: bool,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.entry_id = entry_id
        self.title = title
        self.setObjectName("codexTile")
        self.setCheckable(True)
        self.setAutoExclusive(False)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(TILE_SIZE, TILE_SIZE)
        self.setToolTip(title)
        self.setProperty("complete", "true" if complete else "false")
        self.setProperty("revealed", "true" if revealed else "false")
        # Avoid QPushButton drawing its own label over our layout.
        self.setText("")
        self.setFlat(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(4)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setObjectName("codexTileIcon")
        self.icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedSize(PORTRAIT_SIZE, PORTRAIT_SIZE)
        self.icon_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._apply_portrait(entry_id, complete=complete, revealed=revealed, title=title)
        layout.addStretch(1)
        layout.addWidget(self.icon_label, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

        self.progress_label = QtWidgets.QLabel(
            progress_text if (progress_text and not complete) else ""
        )
        self.progress_label.setObjectName("codexTileProgress")
        self.progress_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setFixedHeight(18)
        self.progress_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.progress_label.setVisible(bool(progress_text) and not complete)
        layout.addWidget(self.progress_label, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        # Explicit override so style polish / teardown never hits a bare
        # QAbstractButton paint path (PySide raises NotImplementedError).
        super().paintEvent(event)

    def _apply_portrait(
        self,
        entry_id: str,
        *,
        complete: bool,
        revealed: bool,
        title: str,
    ) -> None:
        path = portrait_path_for(entry_id)
        if path is not None:
            mode = "color" if complete else "silhouette"
            pixmap = _load_portrait_pixmap(path, mode=mode)
            if pixmap is not None:
                if pixmap.width() != PORTRAIT_SIZE or pixmap.height() != PORTRAIT_SIZE:
                    pixmap = pixmap.scaled(
                        PORTRAIT_SIZE,
                        PORTRAIT_SIZE,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                self.icon_label.setPixmap(pixmap)
                self.icon_label.setText("")
                return
        self.icon_label.setPixmap(QtGui.QPixmap())
        if revealed:
            initial = title.strip()[:1].upper() if title.strip() else "?"
            self.icon_label.setText(initial)
        else:
            self.icon_label.setText("")


class CodexDetailPanel(QtWidgets.QWidget):
    """Right-hand selected-entry sheet."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("codexDetailPanel")
        self.setMinimumWidth(200)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        self.title_label = QtWidgets.QLabel("Select an entry")
        self.title_label.setObjectName("codexDetailTitle")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.flavor_label = QtWidgets.QLabel("")
        self.flavor_label.setObjectName("codexDetailFlavor")
        self.flavor_label.setWordWrap(True)
        self.flavor_label.setVisible(False)
        layout.addWidget(self.flavor_label)

        self.kills_label = QtWidgets.QLabel("")
        self.kills_label.setObjectName("codexDetailKills")
        layout.addWidget(self.kills_label)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setObjectName("codexDetailStatus")
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumHeight(28)
        layout.addWidget(self.status_label)

        drops_header = QtWidgets.QLabel("Drops")
        drops_header.setObjectName("codexDetailSection")
        layout.addWidget(drops_header)

        drops_row = QtWidgets.QWidget()
        drops_row.setObjectName("codexDropsRow")
        drops_layout = QtWidgets.QHBoxLayout(drops_row)
        drops_layout.setContentsMargins(0, 0, 0, 0)
        drops_layout.setSpacing(6)
        self.drop_slots: list[QtWidgets.QLabel] = []
        for _ in range(5):
            slot = QtWidgets.QLabel()
            slot.setObjectName("codexDropSlot")
            slot.setFixedSize(40, 40)
            slot.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.drop_slots.append(slot)
            drops_layout.addWidget(slot)
        drops_layout.addStretch(1)
        layout.addWidget(drops_row)

        layout.addStretch(1)

    def clear(self) -> None:
        self.title_label.setText("Select an entry")
        self.flavor_label.clear()
        self.flavor_label.setVisible(False)
        self.kills_label.clear()
        self.status_label.clear()
        self.status_label.setProperty("mastered", "false")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def show_entry(
        self,
        title: str,
        *,
        flavor: str = "",
        kills_text: str = "",
        status_text: str = "",
        mastered: bool = False,
    ) -> None:
        self.title_label.setText(title or "—")
        flavor = flavor.strip()
        self.flavor_label.setText(flavor)
        self.flavor_label.setVisible(bool(flavor))
        self.kills_label.setText(kills_text)
        self.status_label.setText(status_text)
        self.status_label.setProperty("mastered", "true" if mastered else "false")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)


class CodexFilterPopup(QtWidgets.QFrame):
    """Types + Status chip panel opened from the filter button."""

    changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(
            parent,
            QtCore.Qt.WindowType.Popup | QtCore.Qt.WindowType.FramelessWindowHint,
        )
        self.setObjectName("codexFilterPopup")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._type_buttons: dict[str, QtWidgets.QToolButton] = {}
        self._status_buttons: dict[str, QtWidgets.QToolButton] = {}
        self._selected_types: set[str] = set()
        self._selected_statuses: set[str] = set()

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.types_header = QtWidgets.QLabel("Types")
        self.types_header.setObjectName("codexFilterSection")
        root.addWidget(self.types_header)

        self.types_host = QtWidgets.QWidget()
        self.types_host.setObjectName("codexFilterTypesHost")
        self.types_layout = QtWidgets.QVBoxLayout(self.types_host)
        self.types_layout.setContentsMargins(0, 0, 0, 0)
        self.types_layout.setSpacing(4)
        root.addWidget(self.types_host)

        self.status_header = QtWidgets.QLabel("Status")
        self.status_header.setObjectName("codexFilterSection")
        root.addWidget(self.status_header)

        self.status_host = QtWidgets.QWidget()
        self.status_host.setObjectName("codexFilterStatusHost")
        self.status_layout = QtWidgets.QVBoxLayout(self.status_host)
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setSpacing(4)
        root.addWidget(self.status_host)

        for status_id, label in CODEX_STATUS_FILTERS:
            button = self._make_chip(label)
            button.toggled.connect(
                lambda checked, sid=status_id: self._status_toggled(sid, checked)
            )
            self.status_layout.addWidget(button)
            self._status_buttons[status_id] = button

        self.setMinimumWidth(160)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        parent = self.parentWidget()
        if isinstance(parent, CodexBrowsePanel):
            parent.filter_button.setChecked(False)
        super().hideEvent(event)

    def _make_chip(self, label: str) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setObjectName("codexFilterChip")
        button.setText(label)
        button.setCheckable(True)
        button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        button.setFixedHeight(26)
        return button

    def selected_types(self) -> set[str]:
        return set(self._selected_types)

    def selected_statuses(self) -> set[str]:
        return set(self._selected_statuses)

    def has_active_filters(self) -> bool:
        return bool(self._selected_types or self._selected_statuses)

    def set_available_types(self, type_ids: list[str]) -> None:
        while self.types_layout.count():
            item = self.types_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._type_buttons.clear()
        keep = set(type_ids)
        self._selected_types.intersection_update(keep)
        self.types_header.setVisible(bool(type_ids))
        self.types_host.setVisible(bool(type_ids))
        for type_id in type_ids:
            button = self._make_chip(unit_type_label(type_id))
            button.setChecked(type_id in self._selected_types)
            button.toggled.connect(
                lambda checked, tid=type_id: self._type_toggled(tid, checked)
            )
            self.types_layout.addWidget(button)
            self._type_buttons[type_id] = button
        self.adjustSize()

    def _type_toggled(self, type_id: str, checked: bool) -> None:
        if checked:
            self._selected_types.add(type_id)
        else:
            self._selected_types.discard(type_id)
        self.changed.emit()

    def _status_toggled(self, status_id: str, checked: bool) -> None:
        if checked:
            self._selected_statuses.add(status_id)
        else:
            self._selected_statuses.discard(status_id)
        self.changed.emit()


class CodexBrowsePanel(QtWidgets.QWidget):
    """In-game codex body layout: search/filter + tile grid | detail sheet."""

    entrySelected = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("codexBrowsePanel")
        self._tiles: dict[str, CodexTile] = {}
        self._selected_id: str | None = None
        self._entries: list[CodexEntry] = []
        self._columns = 1

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        left = QtWidgets.QWidget()
        left.setObjectName("codexBrowseLeft")
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        controls = QtWidgets.QWidget()
        controls.setObjectName("codexBrowseControls")
        controls_layout = QtWidgets.QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setObjectName("codexSearchEdit")
        self.search_edit.setPlaceholderText("Search …")
        self.search_edit.setClearButtonEnabled(True)
        controls_layout.addWidget(self.search_edit, 1)

        self.filter_button = QtWidgets.QToolButton()
        self.filter_button.setObjectName("codexFilterButton")
        self.filter_button.setText("No filter")
        self.filter_button.setCheckable(True)
        self.filter_button.setFixedHeight(26)
        self.filter_button.setMinimumWidth(120)
        self.filter_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.filter_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        controls_layout.addWidget(self.filter_button, 0)
        left_layout.addWidget(controls)

        self.filter_popup = CodexFilterPopup(self)
        self.filter_popup.hide()

        self.grid_scroll = QtWidgets.QScrollArea()
        self.grid_scroll.setObjectName("codexTileGridScroll")
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.grid_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.grid_host = QtWidgets.QWidget()
        self.grid_host.setObjectName("codexTileGridHost")
        self.grid_layout = QtWidgets.QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(4, 4, 4, 4)
        self.grid_layout.setHorizontalSpacing(TILE_SPACING)
        self.grid_layout.setVerticalSpacing(TILE_SPACING)
        self.grid_layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.grid_scroll.setWidget(self.grid_host)
        left_layout.addWidget(self.grid_scroll, 1)

        self.detail = CodexDetailPanel()
        # Fixed ~2:1 split (grid : detail).
        root.addWidget(left, GRID_SPLIT_LEFT)
        root.addWidget(self.detail, GRID_SPLIT_RIGHT)

        self.search_edit.textChanged.connect(self._refilter)
        self.filter_button.clicked.connect(self._toggle_filter_popup)
        self.filter_popup.changed.connect(self._filters_changed)
        self._wrap_timer = QtCore.QTimer(self)
        self._wrap_timer.setSingleShot(True)
        self._wrap_timer.timeout.connect(self._reflow_if_needed)

    @property
    def selected_id(self) -> str | None:
        return self._selected_id

    def set_entries(
        self,
        entries: list[CodexEntry],
        *,
        type_ids: list[str] | None = None,
        select_id: str | None = None,
    ) -> None:
        self._entries = list(entries)
        if type_ids is None:
            present = {entry.type_id for entry in self._entries if entry.type_id}
            type_ids = ordered_type_ids(present)
        self.filter_popup.set_available_types(type_ids)
        self._sync_filter_button_label()
        keep = select_id if select_id is not None else self._selected_id
        self._rebuild_grid(preferred_id=keep)
        self._wrap_timer.start(0)

    def select_entry(self, entry_id: str | None) -> None:
        self._selected_id = entry_id
        for tile_id, tile in self._tiles.items():
            tile.setChecked(tile_id == entry_id)
        if not entry_id:
            self.detail.clear()

    def _toggle_filter_popup(self, *_args) -> None:
        if self.filter_popup.isVisible():
            self.filter_popup.hide()
            self.filter_button.setChecked(False)
            return
        self.filter_popup.adjustSize()
        button_rect = self.filter_button.rect()
        global_pos = self.filter_button.mapToGlobal(
            QtCore.QPoint(
                button_rect.right() - self.filter_popup.sizeHint().width(),
                button_rect.bottom() + 2,
            )
        )
        self.filter_popup.move(global_pos)
        self.filter_popup.show()
        self.filter_button.setChecked(True)

    def _filters_changed(self) -> None:
        self._sync_filter_button_label()
        self._refilter()

    def _sync_filter_button_label(self) -> None:
        types = self.filter_popup.selected_types()
        statuses = self.filter_popup.selected_statuses()
        total = len(types) + len(statuses)
        if total == 0:
            self.filter_button.setText("No filter")
        elif total == 1:
            if types:
                self.filter_button.setText(unit_type_label(next(iter(types))))
            else:
                label = next(
                    label
                    for status_id, label in CODEX_STATUS_FILTERS
                    if status_id in statuses
                )
                self.filter_button.setText(label)
        else:
            self.filter_button.setText(f"{total} filters")

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self.filter_popup.hide()
        self.filter_button.setChecked(False)
        super().hideEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._wrap_timer.start(0)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._wrap_timer.start(0)

    def _refilter(self, *_args) -> None:
        self._rebuild_grid(preferred_id=self._selected_id)

    def _reflow_if_needed(self) -> None:
        if not self._entries:
            return
        columns = self._column_count()
        if columns != self._columns:
            self._rebuild_grid(preferred_id=self._selected_id)

    def _column_count(self) -> int:
        """How many fixed-size cells fit across the grid viewport."""
        width = self.grid_scroll.viewport().width()
        if width <= 1:
            width = self.grid_scroll.width()
        margins = self.grid_layout.contentsMargins()
        usable = width - margins.left() - margins.right() - 4
        if usable < TILE_SIZE:
            return 1
        return max(1, (usable + TILE_SPACING) // (TILE_SIZE + TILE_SPACING))

    def _filtered_entries(self) -> list[CodexEntry]:
        query = self.search_edit.text().strip().lower()
        types = self.filter_popup.selected_types()
        statuses = self.filter_popup.selected_statuses()
        out: list[CodexEntry] = []
        for entry in self._entries:
            if types and entry.type_id not in types:
                continue
            if statuses and entry.status not in statuses:
                continue
            if query and query not in entry.title.lower() and query not in entry.id.lower():
                continue
            out.append(entry)
        return out

    def _clear_grid_widgets(self) -> None:
        """Detach tiles before deleteLater so queued paints skip dying widgets."""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            widget.hide()
            widget.blockSignals(True)
            widget.setParent(None)
            widget.deleteLater()
        self._tiles.clear()

    def _rebuild_grid(self, *, preferred_id: str | None) -> None:
        self._clear_grid_widgets()

        filtered = self._filtered_entries()
        columns = self._column_count()
        self._columns = columns
        for index, entry in enumerate(filtered):
            tile = CodexTile(
                entry.id,
                entry.title,
                entry.progress,
                complete=entry.complete,
                revealed=entry.revealed,
            )
            tile.clicked.connect(
                lambda _checked=False, eid=entry.id: self._tile_clicked(eid)
            )
            self.grid_layout.addWidget(tile, index // columns, index % columns)
            self._tiles[entry.id] = tile

        if not filtered:
            empty = QtWidgets.QLabel("No entries match")
            empty.setObjectName("codexPlaceholder")
            empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.grid_layout.addWidget(empty, 0, 0, 1, columns)

        if preferred_id and preferred_id in self._tiles:
            self.select_entry(preferred_id)
            self.entrySelected.emit(preferred_id)
        elif filtered:
            self.select_entry(filtered[0].id)
            self.entrySelected.emit(filtered[0].id)
        else:
            self.select_entry(None)

    def _tile_clicked(self, entry_id: str) -> None:
        self.select_entry(entry_id)
        self.entrySelected.emit(entry_id)
