"""Codex browse layout: tile grid + detail panel (in-game structure)."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PySide6 import QtCore, QtGui, QtWidgets

from .catalog import (
    CODEX_STATUS_FILTERS,
    display_name_for,
    drop_item_meta,
    drop_rarity_rank,
    drop_sort_group_rank,
    format_drop_chance,
    item_portrait_path_for,
    ordered_type_ids,
    portrait_path_for,
    unit_type_label,
)

HEADER_HEIGHT = 120
COMPLETION_ICON_SIZE = 36

DROP_SLOT_SIZE = 40
RARITY_BORDER = {
    "Common": "#6a7a88",
    "Uncommon": "#3f9a5f",
    "Rare": "#3a7ec4",
    "Epic": "#9a4fd4",
    "Legendary": "#c9892e",
}

_PORTRAIT_CACHE: dict[tuple[str, str], QtGui.QPixmap] = {}

# Named tiles are the layout unit — browse pane is fixed to N columns;
# the detail pane absorbs all remaining width.
TILE_SIZE = 140
TILE_WIDTH_NAMED = 128
TILE_HEIGHT_NAMED = 156
PORTRAIT_SIZE = 96
PORTRAIT_SIZE_NAMED = 120
TILE_SPACING = 6
GRID_COLUMNS = 4
GRID_MARGIN_LEFT = 4
GRID_MARGIN_RIGHT = 8
# Room for the grid's vertical scrollbar so it doesn't cover the 4th column.
GRID_SCROLL_GUTTER = 10
DETAIL_MIN_WIDTH = 240
GRID_SPLIT_LEFT = 0
GRID_SPLIT_RIGHT = 1


def grid_pane_width(columns: int = GRID_COLUMNS) -> int:
    """Exact width for a fixed ``columns`` tile grid + margins + scrollbar."""
    cols = max(1, columns)
    tiles = cols * TILE_WIDTH_NAMED + (cols - 1) * TILE_SPACING
    return tiles + GRID_MARGIN_LEFT + GRID_MARGIN_RIGHT + GRID_SCROLL_GUTTER


def _completion_check_pixmap(*, complete: bool, size: int = COMPLETION_ICON_SIZE) -> QtGui.QPixmap:
    """Circle + checkmark; vivid when complete, muted when not."""
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    if complete:
        ring = QtGui.QColor("#4a9fd4")
        mark = QtGui.QColor("#5ec0ff")
    else:
        ring = QtGui.QColor("#3a4652")
        mark = QtGui.QColor("#5a6874")
    pen = QtGui.QPen(ring)
    pen.setWidthF(max(1.5, size * 0.09))
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    inset = pen.widthF() * 0.5 + 0.5
    painter.drawEllipse(QtCore.QRectF(inset, inset, size - 2 * inset, size - 2 * inset))
    check = QtGui.QPen(mark)
    check.setWidthF(max(1.8, size * 0.11))
    check.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    check.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(check)
    path = QtGui.QPainterPath()
    path.moveTo(size * 0.28, size * 0.52)
    path.lineTo(size * 0.44, size * 0.68)
    path.lineTo(size * 0.74, size * 0.34)
    painter.drawPath(path)
    painter.end()
    return pixmap


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
    # Extra lowercase haystack (e.g. dungeon drop item ids/names).
    search_text: str = ""


class CodexTile(QtWidgets.QFrame):
    """Clickable codex cell.

    QFrame (not QPushButton): PySide's QAbstractButton paint/teardown path
    corrupts the window surface when many tiles are destroyed on mode switch.
    """

    clicked = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry_id = ""
        self.title = ""
        self._checked = False
        self._portrait_size = PORTRAIT_SIZE_NAMED
        self.setObjectName("codexTile")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(TILE_WIDTH_NAMED, TILE_HEIGHT_NAMED)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setObjectName("codexTileIcon")
        self.icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedSize(self._portrait_size, self._portrait_size)
        self.icon_label.setScaledContents(False)
        self.icon_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        layout.addWidget(self.icon_label, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.title_label = QtWidgets.QLabel("")
        self.title_label.setObjectName("codexTileTitle")
        self.title_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.title_label.setFixedHeight(26)
        self.title_label.setWordWrap(True)
        self.title_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        layout.addWidget(self.title_label, 0)

        self.setChecked(False)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        self._checked = bool(checked)
        self.setProperty("selected", "true" if self._checked else "false")
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def bind(
        self,
        entry_id: str,
        title: str,
        *,
        complete: bool,
        revealed: bool,
    ) -> None:
        self.entry_id = entry_id
        self.title = title
        self.setToolTip(title)
        self.setProperty("complete", "true" if complete else "false")
        self.setProperty("revealed", "true" if revealed else "false")
        self.title_label.setText(title)
        self._apply_portrait(
            entry_id, complete=complete, revealed=revealed, title=title
        )
        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def _apply_portrait(
        self,
        entry_id: str,
        *,
        complete: bool,
        revealed: bool,
        title: str,
    ) -> None:
        size = self._portrait_size
        path = portrait_path_for(entry_id)
        if path is not None:
            mode = "color" if complete else "silhouette"
            pixmap = _load_portrait_pixmap(path, mode=mode)
            if pixmap is not None:
                if pixmap.width() != size or pixmap.height() != size:
                    pixmap = pixmap.scaled(
                        size,
                        size,
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

        self.header_label = QtWidgets.QLabel()
        self.header_label.setObjectName("codexDetailHeader")
        self.header_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.header_label.setFixedHeight(HEADER_HEIGHT)
        self.header_label.setScaledContents(False)
        self.header_label.setVisible(False)
        layout.addWidget(self.header_label)

        self.title_label = QtWidgets.QLabel("Select an entry")
        self.title_label.setObjectName("codexDetailTitle")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.flavor_label = QtWidgets.QLabel("")
        self.flavor_label.setObjectName("codexDetailFlavor")
        self.flavor_label.setWordWrap(True)
        self.flavor_label.setVisible(False)
        layout.addWidget(self.flavor_label)

        self.meta_stack = QtWidgets.QStackedWidget()
        self.meta_stack.setObjectName("codexDetailMetaStack")
        self.meta_stack.setFixedHeight(48)

        self.kills_label = QtWidgets.QLabel("")
        self.kills_label.setObjectName("codexDetailKills")
        self.kills_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.meta_stack.addWidget(self.kills_label)  # 0

        self.completion_row = QtWidgets.QWidget()
        self.completion_row.setObjectName("codexDetailCompletion")
        completion_layout = QtWidgets.QHBoxLayout(self.completion_row)
        completion_layout.setContentsMargins(0, 0, 0, 0)
        completion_layout.setSpacing(8)

        self.completion_icon = QtWidgets.QLabel()
        self.completion_icon.setObjectName("codexDetailCompletionIcon")
        self.completion_icon.setFixedSize(COMPLETION_ICON_SIZE, COMPLETION_ICON_SIZE)
        self.completion_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        completion_layout.addWidget(
            self.completion_icon, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        completion_text = QtWidgets.QWidget()
        completion_text_layout = QtWidgets.QVBoxLayout(completion_text)
        completion_text_layout.setContentsMargins(0, 0, 0, 0)
        completion_text_layout.setSpacing(1)

        self.completion_title = QtWidgets.QLabel("")
        self.completion_title.setObjectName("codexDetailCompletionTitle")
        completion_text_layout.addWidget(self.completion_title)

        self.completion_subtitle = QtWidgets.QLabel("")
        self.completion_subtitle.setObjectName("codexDetailCompletionSubtitle")
        self.completion_subtitle.setWordWrap(True)
        completion_text_layout.addWidget(self.completion_subtitle)

        completion_layout.addWidget(completion_text, 1)
        self.meta_stack.addWidget(self.completion_row)  # 1

        meta_empty = QtWidgets.QWidget()
        self.meta_stack.addWidget(meta_empty)  # 2
        self.meta_stack.setCurrentIndex(2)
        layout.addWidget(self.meta_stack)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setObjectName("codexDetailStatus")
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFixedHeight(28)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)
        self._header_path: Path | None = None
        self._header_pixmap: QtGui.QPixmap | None = None

        self.drops_scroll = QtWidgets.QScrollArea()
        self.drops_scroll.setObjectName("codexDropsScroll")
        self.drops_scroll.setWidgetResizable(True)
        self.drops_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.drops_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.drops_scroll.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self.drops_scroll.setMinimumHeight(120)
        self.drops_scroll.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        self.drops_host = QtWidgets.QWidget()
        self.drops_host.setObjectName("codexDropsHost")
        self.drops_layout = QtWidgets.QVBoxLayout(self.drops_host)
        self.drops_layout.setContentsMargins(0, 0, 0, 0)
        self.drops_layout.setSpacing(8)
        self.drops_scroll.setWidget(self.drops_host)
        layout.addWidget(self.drops_scroll, 1)

        self._drop_slots: list[QtWidgets.QWidget] = []
        self._drop_rows: list[dict] = []
        self._drop_sections: list[dict] | None = None
        self._drop_cols = 0
        self._empty_drops = QtWidgets.QLabel("—")
        self._empty_drops.setObjectName("codexDetailFlavor")
        self.drops_layout.addWidget(self._empty_drops)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_header_pixmap()
        if not self._drop_rows:
            return
        cols = max(1, (self.drops_scroll.viewport().width() or 200) // (DROP_SLOT_SIZE + 6))
        if cols != self._drop_cols:
            self._render_drops()

    def clear(self) -> None:
        self._set_header(None)
        self.title_label.setText("Select an entry")
        self.flavor_label.clear()
        self.flavor_label.setVisible(False)
        self.kills_label.clear()
        self._set_completion(None)
        self.meta_stack.setCurrentIndex(2)
        self.status_label.clear()
        self.status_label.setVisible(False)
        self.status_label.setProperty("mastered", "false")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.set_drops([])

    def show_entry(
        self,
        title: str,
        *,
        flavor: str = "",
        kills_text: str = "",
        status_text: str = "",
        mastered: bool = False,
        show_status: bool = True,
        completion: bool | None = None,
        header_path: Path | str | None = None,
        drop_ids: list[str] | None = None,
        drop_rows: list[dict] | None = None,
        drop_sections: list[dict] | None = None,
    ) -> None:
        path: Path | None = None
        if header_path:
            path = Path(header_path)
            if not path.is_file():
                path = None
        self._set_header(path)
        self.title_label.setText(title or "—")
        flavor = flavor.strip()
        self.flavor_label.setText(flavor)
        self.flavor_label.setVisible(bool(flavor))
        if completion is None:
            self._set_completion(None)
            self.kills_label.setText(kills_text)
            self.meta_stack.setCurrentIndex(0 if kills_text else 2)
        else:
            self.kills_label.clear()
            self._set_completion(bool(completion))
            self.meta_stack.setCurrentIndex(1)
        status = status_text if show_status else ""
        self.status_label.setText(status)
        self.status_label.setVisible(bool(status))
        self.status_label.setProperty("mastered", "true" if mastered else "false")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if drop_sections is not None:
            self.set_drops(drop_sections=drop_sections)
        elif drop_rows is not None:
            self.set_drops(drop_rows)
        else:
            self.set_drops([{"id": item_id} for item_id in (drop_ids or [])])

    def _set_completion(self, complete: bool | None) -> None:
        if complete is None:
            self.completion_title.clear()
            self.completion_subtitle.clear()
            self.completion_icon.clear()
            return
        self.completion_icon.setPixmap(_completion_check_pixmap(complete=complete))
        if complete:
            self.completion_title.setText("Completed")
            self.completion_subtitle.setText("You have cleared this dungeon.")
            state = "complete"
        else:
            self.completion_title.setText("Not completed")
            self.completion_subtitle.setText("Clear this dungeon to mark it done.")
            state = "incomplete"
        self.completion_row.setProperty("state", state)
        self.completion_title.setProperty("state", state)
        for widget in (self.completion_row, self.completion_title):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _set_header(self, path: Path | None) -> None:
        self._header_path = path
        self._header_pixmap = None
        if path is None:
            self.header_label.clear()
            self.header_label.setVisible(False)
            return
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            self.header_label.clear()
            self.header_label.setVisible(False)
            self._header_path = None
            return
        self._header_pixmap = pixmap
        self.header_label.setVisible(True)
        self._refresh_header_pixmap()

    def _refresh_header_pixmap(self) -> None:
        if self._header_pixmap is None or self._header_pixmap.isNull():
            return
        width = max(1, self.header_label.width() or (self.width() - 28))
        scaled = self._header_pixmap.scaled(
            width,
            HEADER_HEIGHT,
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() > width or scaled.height() > HEADER_HEIGHT:
            x = max(0, (scaled.width() - width) // 2)
            y = max(0, (scaled.height() - HEADER_HEIGHT) // 3)
            scaled = scaled.copy(x, y, min(width, scaled.width()), min(HEADER_HEIGHT, scaled.height()))
        self.header_label.setPixmap(scaled)

    def set_drops(
        self,
        drop_rows: list[dict] | list[str] | None = None,
        *,
        drop_sections: list[dict] | None = None,
    ) -> None:
        sections: list[dict] | None = None
        if drop_sections:
            sections = []
            flat: list[dict] = []
            for section in drop_sections:
                if not isinstance(section, dict):
                    continue
                items_raw = section.get("items") or []
                items: list[dict] = []
                for entry in items_raw:
                    if isinstance(entry, str) and entry:
                        items.append({"id": entry})
                    elif isinstance(entry, dict) and entry.get("id"):
                        items.append(entry)
                if not items:
                    continue
                out = dict(section)
                out["items"] = items
                sections.append(out)
                flat.extend(items)
            self._drop_sections = sections or None
            self._drop_rows = flat
        else:
            rows: list[dict] = []
            for entry in drop_rows or []:
                if isinstance(entry, str) and entry:
                    rows.append({"id": entry})
                elif isinstance(entry, dict) and entry.get("id"):
                    rows.append(entry)
            self._drop_sections = None
            self._drop_rows = rows
        self._render_drops()

    def _sort_drop_rows(self, rows: list[dict], *, group_first: bool) -> list[dict]:
        ordered = list(rows)

        def sort_key(drop: dict) -> tuple:
            item_id = str(drop.get("id") or "")
            meta = drop_item_meta(item_id)
            name = (meta.get("name") or display_name_for(item_id, kind="item")).lower()
            rarity = drop_rarity_rank(meta.get("rarity") or "")
            group = drop_sort_group_rank(meta.get("type") or "") if group_first else 0
            try:
                chance = float(drop["chance"]) if drop.get("chance") is not None else -1.0
            except (TypeError, ValueError):
                chance = -1.0
            return (group, rarity, -chance, name)

        ordered.sort(key=sort_key)
        return ordered

    def _make_drop_slot(self, drop: dict) -> QtWidgets.QLabel:
        item_id = str(drop.get("id") or "")
        slot = QtWidgets.QLabel()
        slot.setObjectName("codexDropSlot")
        slot.setFixedSize(DROP_SLOT_SIZE, DROP_SLOT_SIZE)
        slot.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        meta = drop_item_meta(item_id)
        rarity = meta.get("rarity") or "Common"
        border = RARITY_BORDER.get(rarity, RARITY_BORDER["Common"])
        slot.setStyleSheet(
            f"QLabel#codexDropSlot {{ border: 1px solid {border}; }}"
        )
        title = meta.get("name") or display_name_for(item_id, kind="item")
        chance = drop.get("chance")
        try:
            chance_f = float(chance) if chance is not None else None
        except (TypeError, ValueError):
            chance_f = None
        chance_text = format_drop_chance(chance_f)
        tip_bits = [title]
        slot_type = meta.get("type") or ""
        faction = meta.get("faction") or ""
        if slot_type or faction:
            tip_bits.append(
                " · ".join(part for part in (slot_type, faction) if part)
            )
        if rarity:
            tip_bits.append(rarity)
        tip_bits.append(
            f"Drop chance {chance_text}" if chance_text else "Drop chance unknown"
        )
        slot.setToolTip("\n".join(tip_bits))
        path = item_portrait_path_for(item_id)
        pixmap = _load_portrait_pixmap(path, mode="color") if path else None
        if pixmap is not None and not pixmap.isNull():
            slot.setPixmap(
                pixmap.scaled(
                    DROP_SLOT_SIZE - 4,
                    DROP_SLOT_SIZE - 4,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            slot.setText(title[:1].upper() if title else "?")
        return slot

    def _add_drop_grid(self, rows: list[dict], cols: int) -> QtWidgets.QWidget:
        host = QtWidgets.QWidget()
        host.setObjectName("codexDropsGrid")
        grid = QtWidgets.QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        for index, drop in enumerate(rows):
            slot = self._make_drop_slot(drop)
            row, col = divmod(index, cols)
            grid.addWidget(slot, row, col)
            self._drop_slots.append(slot)
        return host

    def _render_drops(self) -> None:
        while self.drops_layout.count():
            item = self.drops_layout.takeAt(0)
            widget = item.widget()
            if widget is None or widget is self._empty_drops:
                continue
            widget.hide()
            widget.deleteLater()
        self._drop_slots.clear()

        cols = max(1, (self.drops_scroll.viewport().width() or 200) // (DROP_SLOT_SIZE + 6))
        self._drop_cols = cols

        if self._drop_sections:
            visible_sections: list[tuple[dict, list[dict]]] = []
            for section in self._drop_sections:
                # Keep builder order (boss weapons → mount → shard, etc.).
                rows = list(section.get("items") or [])
                if rows:
                    visible_sections.append((section, rows))
            if not visible_sections:
                self._empty_drops.setVisible(True)
                self._empty_drops.setText("—")
                self.drops_layout.addWidget(self._empty_drops)
                return
            self._empty_drops.setVisible(False)
            for index, (section, rows) in enumerate(visible_sections):
                if index > 0:
                    rule = QtWidgets.QFrame()
                    rule.setObjectName("codexDropSectionRule")
                    rule.setFrameShape(QtWidgets.QFrame.Shape.HLine)
                    rule.setFixedHeight(1)
                    self.drops_layout.addWidget(rule)
                    self._drop_slots.append(rule)
                label_text = str(section.get("label") or "").strip()
                if label_text:
                    label = QtWidgets.QLabel(label_text)
                    label.setObjectName("codexDropSectionLabel")
                    self.drops_layout.addWidget(label)
                    self._drop_slots.append(label)
                note = str(section.get("note") or "").strip()
                if note:
                    note_label = QtWidgets.QLabel(note)
                    note_label.setObjectName("codexDropSectionNote")
                    note_label.setWordWrap(True)
                    self.drops_layout.addWidget(note_label)
                    self._drop_slots.append(note_label)
                self.drops_layout.addWidget(self._add_drop_grid(rows, cols))
            self.drops_layout.addStretch(1)
            return

        rows = self._sort_drop_rows(list(self._drop_rows), group_first=True)
        if not rows:
            self._empty_drops.setVisible(True)
            self._empty_drops.setText("—")
            self.drops_layout.addWidget(self._empty_drops)
            return
        self._empty_drops.setVisible(False)
        self.drops_layout.addWidget(self._add_drop_grid(rows, cols))
        self.drops_layout.addStretch(1)


class CodexFilterPopup(QtWidgets.QFrame):
    """Types + Status chip panel opened from the filter button.

    Child overlay (not a Qt.Popup window). A top-level Popup was resized via
    adjustSize() on every mode switch and looked like a separate window collapsing.
    """

    changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("codexFilterPopup")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.hide()
        self._type_buttons: dict[str, QtWidgets.QToolButton] = {}
        self._status_buttons: dict[str, QtWidgets.QToolButton] = {}
        self._selected_types: set[str] = set()
        self._selected_statuses: set[str] = set()
        self._available_type_ids: list[str] = []
        self._types_dirty = True

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

    def clear_filters(self) -> None:
        self._selected_types.clear()
        self._selected_statuses.clear()
        for button in self._type_buttons.values():
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)
        for button in self._status_buttons.values():
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)

    def set_available_types(self, type_ids: list[str]) -> None:
        # Defer widget rebuild until the panel is shown — never resize a
        # top-level/offscreen surface during Collection/Codex/Dungeons swaps.
        self._available_type_ids = list(type_ids)
        self._selected_types.intersection_update(set(type_ids))
        self._types_dirty = True
        if self.isVisible():
            self._rebuild_type_chips()

    def prepare_for_show(self) -> None:
        if self._types_dirty:
            self._rebuild_type_chips()
        self.adjustSize()

    def _rebuild_type_chips(self) -> None:
        while self.types_layout.count():
            item = self.types_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._type_buttons.clear()
        type_ids = self._available_type_ids
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
        self._types_dirty = False

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
        self._tile_pool: list[CodexTile] = []
        self._empty_label: QtWidgets.QLabel | None = None
        self._selected_id: str | None = None
        self._entries: list[CodexEntry] = []
        self._columns = 1
        self._fixed_columns: int | None = None
        self._show_titles = False

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        left = QtWidgets.QWidget()
        left.setObjectName("codexBrowseLeft")
        self._browse_left = left
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        controls = QtWidgets.QWidget()
        controls.setObjectName("codexBrowseControls")
        controls_layout = QtWidgets.QHBoxLayout(controls)
        # Same inset as the tile band (leave the scrollbar gutter empty).
        controls_layout.setContentsMargins(
            GRID_MARGIN_LEFT,
            0,
            GRID_MARGIN_RIGHT + GRID_SCROLL_GUTTER,
            0,
        )
        controls_layout.setSpacing(TILE_SPACING)

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
        self.filter_popup.raise_()

        self.grid_scroll = QtWidgets.QScrollArea()
        self.grid_scroll.setObjectName("codexTileGridScroll")
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.grid_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        # Never shrink the page to the tile-content height when modes change.
        self.grid_scroll.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self.grid_scroll.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        self.grid_host = QtWidgets.QWidget()
        self.grid_host.setObjectName("codexTileGridHost")
        self.grid_layout = QtWidgets.QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(
            GRID_MARGIN_LEFT, 4, GRID_MARGIN_RIGHT, 4
        )
        self.grid_layout.setHorizontalSpacing(TILE_SPACING)
        self.grid_layout.setVerticalSpacing(TILE_SPACING)
        self.grid_layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.grid_scroll.setWidget(self.grid_host)
        left_layout.addWidget(self.grid_scroll, 1)

        self.detail = CodexDetailPanel()
        self.detail.setMinimumWidth(DETAIL_MIN_WIDTH)
        self.detail.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        left.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._apply_grid_pane_width(GRID_COLUMNS)
        # Tile pane keeps a fixed 4-column footprint; detail stretches.
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
        columns: int | None = None,
        show_titles: bool = False,
    ) -> None:
        self._entries = list(entries)
        self._fixed_columns = columns if columns and columns > 0 else None
        self._show_titles = bool(show_titles)
        self._apply_grid_pane_width(self._fixed_columns or GRID_COLUMNS)
        if type_ids is None:
            present = {entry.type_id for entry in self._entries if entry.type_id}
            type_ids = ordered_type_ids(present)
        self.filter_popup.set_available_types(type_ids)
        self._sync_filter_button_label()
        keep = select_id if select_id is not None else self._selected_id
        self._rebuild_grid(preferred_id=keep)
        self._wrap_timer.start(0)

    def _apply_grid_pane_width(self, columns: int) -> None:
        width = grid_pane_width(columns)
        self._browse_left.setFixedWidth(width)
        self.setMinimumWidth(width + 8 + DETAIL_MIN_WIDTH)

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
        self.filter_popup.prepare_for_show()
        popup_w = max(self.filter_popup.sizeHint().width(), self.filter_popup.minimumWidth())
        popup_h = self.filter_popup.sizeHint().height()
        self.filter_popup.resize(popup_w, popup_h)
        # Position under the filter button inside this panel (not a WM popup).
        anchor = self.filter_button.mapTo(
            self,
            QtCore.QPoint(self.filter_button.width() - popup_w, self.filter_button.height() + 2),
        )
        x = max(0, min(anchor.x(), max(0, self.width() - popup_w)))
        y = max(0, min(anchor.y(), max(0, self.height() - popup_h)))
        self.filter_popup.move(x, y)
        self.filter_popup.raise_()
        self.filter_popup.show()
        self.filter_button.setChecked(True)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if (
            self.filter_popup.isVisible()
            and event.type() == QtCore.QEvent.Type.MouseButtonPress
            and isinstance(event, QtGui.QMouseEvent)
        ):
            global_pos = (
                event.globalPosition().toPoint()
                if hasattr(event, "globalPosition")
                else event.globalPos()
            )
            target = QtWidgets.QApplication.widgetAt(global_pos)
            if target is not None and (
                self.filter_popup.isAncestorOf(target) or target is self.filter_popup
                or self.filter_button.isAncestorOf(target) or target is self.filter_button
            ):
                return super().eventFilter(watched, event)
            # Outside overlay + button → dismiss (replaces Qt.Popup auto-close).
            if self.isAncestorOf(target) if target is not None else True:
                self.filter_popup.hide()
                self.filter_button.setChecked(False)
        return super().eventFilter(watched, event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.filter_popup.hide()
        self.filter_button.setChecked(False)
        super().hideEvent(event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._wrap_timer.start(0)

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

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._wrap_timer.start(0)

    def _refilter(self, *_args) -> None:
        self._rebuild_grid(preferred_id=self._selected_id)

    def _reflow_if_needed(self) -> None:
        if not self._entries or self._fixed_columns is not None:
            return
        columns = self._column_count()
        if columns != self._columns:
            self._rebuild_grid(preferred_id=self._selected_id)

    def _column_count(self) -> int:
        """Column count: fixed grid when set, otherwise fit to viewport."""
        if self._fixed_columns is not None:
            return self._fixed_columns
        width = self.grid_scroll.viewport().width()
        if width <= 1:
            width = self.grid_scroll.width()
        margins = self.grid_layout.contentsMargins()
        usable = (
            width
            - margins.left()
            - margins.right()
            - GRID_SCROLL_GUTTER
            - 4
        )
        cell = TILE_WIDTH_NAMED if self._show_titles else TILE_SIZE
        if usable < cell:
            return 1
        return max(1, (usable + TILE_SPACING) // (cell + TILE_SPACING))

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
            if query and (
                query not in entry.title.lower()
                and query not in entry.id.lower()
                and query not in entry.search_text
            ):
                continue
            out.append(entry)
        return out

    def _acquire_tile(self) -> CodexTile:
        if self._tile_pool:
            tile = self._tile_pool.pop()
            tile.show()
            return tile
        tile = CodexTile(self.grid_host)
        tile.clicked.connect(self._pooled_tile_clicked)
        return tile

    def _pooled_tile_clicked(self) -> None:
        sender = self.sender()
        if isinstance(sender, CodexTile) and sender.entry_id:
            self._tile_clicked(sender.entry_id)

    def _rebuild_grid(self, *, preferred_id: str | None) -> None:
        # Rebind in place — never destroy QWidget tiles on mode switch.
        # Destroying QAbstractButton/QPushButton tiles was corrupting the
        # window surface into thin horizontal strips (see prior paintEvent note).
        filtered = self._filtered_entries()
        columns = self._column_count()
        self._columns = columns

        self.grid_host.setUpdatesEnabled(False)
        try:
            if self._empty_label is not None:
                self.grid_layout.removeWidget(self._empty_label)
                self._empty_label.hide()

            # Park current tiles (still children; not windows).
            previous = list(self._tiles.values())
            self._tiles.clear()
            for tile in previous:
                self.grid_layout.removeWidget(tile)
                tile.hide()
                tile.setChecked(False)
                self._tile_pool.append(tile)

            for index, entry in enumerate(filtered):
                tile = self._acquire_tile()
                tile.bind(
                    entry.id,
                    entry.title,
                    complete=entry.complete,
                    revealed=entry.revealed,
                )
                self.grid_layout.addWidget(tile, index // columns, index % columns)
                self._tiles[entry.id] = tile

            if not filtered:
                if self._empty_label is None:
                    empty = QtWidgets.QLabel("No entries match")
                    empty.setObjectName("codexPlaceholder")
                    empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                    self._empty_label = empty
                self._empty_label.show()
                self.grid_layout.addWidget(self._empty_label, 0, 0, 1, columns)
        finally:
            self.grid_host.setUpdatesEnabled(True)

        if preferred_id and preferred_id in self._tiles:
            self.select_entry(preferred_id)
            self.entrySelected.emit(preferred_id)
        elif filtered:
            self.select_entry(filtered[0].id)
            self.entrySelected.emit(filtered[0].id)
        else:
            self.select_entry(None)
            self.detail.clear()

    def _tile_clicked(self, entry_id: str) -> None:
        self.select_entry(entry_id)
        self.entrySelected.emit(entry_id)
