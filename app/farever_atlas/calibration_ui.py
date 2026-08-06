"""Interactive map-calibration widgets."""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .config import safe_float
from .pages.map.data import MapCalibration, MapTexture


class MapCalibrationCanvas(QtWidgets.QWidget):
    pixelPicked = QtCore.Signal(float, float)

    def __init__(self, image: QtGui.QImage, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.image = image
        self.anchors: list[tuple[float, float, float, float]] = []
        self.pending_pixel: tuple[float, float] | None = None
        self.setMinimumSize(560, 560)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)

    def _image_rect(self) -> QtCore.QRectF:
        if self.image.isNull():
            return QtCore.QRectF()
        available = QtCore.QRectF(self.rect()).adjusted(8, 8, -8, -8)
        scale = min(
            available.width() / self.image.width(),
            available.height() / self.image.height(),
        )
        width = self.image.width() * scale
        height = self.image.height() * scale
        return QtCore.QRectF(
            available.center().x() - width / 2.0,
            available.center().y() - height / 2.0,
            width,
            height,
        )

    def set_anchors(self, anchors: list[tuple[float, float, float, float]]) -> None:
        self.anchors = list(anchors)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QtGui.QColor("#0d1218"))
        target = self._image_rect()
        if target.isEmpty():
            painter.end()
            return
        painter.drawImage(target, self.image)
        painter.setPen(QtGui.QPen(QtGui.QColor("#d8e2eb"), 1.0))
        painter.drawRect(target)

        def screen_point(u: float, v: float) -> QtCore.QPointF:
            return QtCore.QPointF(
                target.left() + u / self.image.width() * target.width(),
                target.top() + v / self.image.height() * target.height(),
            )

        for index, (_x, _y, u, v) in enumerate(self.anchors, start=1):
            point = screen_point(u, v)
            painter.setPen(QtGui.QPen(QtGui.QColor("#70d6ff"), 2.0))
            painter.drawLine(point + QtCore.QPointF(-8, 0), point + QtCore.QPointF(8, 0))
            painter.drawLine(point + QtCore.QPointF(0, -8), point + QtCore.QPointF(0, 8))
            painter.drawText(point + QtCore.QPointF(10, -10), str(index))

        if self.pending_pixel is not None:
            point = screen_point(*self.pending_pixel)
            painter.setPen(QtGui.QPen(QtGui.QColor("#ffd166"), 2.0))
            painter.drawEllipse(point, 7.0, 7.0)
        painter.end()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        target = self._image_rect()
        point = event.position()
        if not target.contains(point) or self.image.isNull():
            return
        u = (point.x() - target.left()) / target.width() * self.image.width()
        v = (point.y() - target.top()) / target.height() * self.image.height()
        u = max(0.0, min(float(self.image.width()), u))
        v = max(0.0, min(float(self.image.height()), v))
        self.pending_pixel = (u, v)
        self.pixelPicked.emit(u, v)
        self.update()


class MapCalibrationDialog(QtWidgets.QDialog):
    def __init__(
        self,
        map_texture: MapTexture,
        player_provider: Any,
        initial_anchors: list[tuple[float, float, float, float]] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Calibrate Siagarta map")
        self.resize(760, 860)
        self.map_texture = map_texture
        self.player_provider = player_provider
        self.anchors: list[tuple[float, float, float, float]] = list(initial_anchors or [])
        self.result_calibration: MapCalibration | None = None
        self.pending_pixel: tuple[float, float] | None = None

        layout = QtWidgets.QVBoxLayout(self)
        instructions = QtWidgets.QLabel(
            "The texture is north-up. At an identifiable in-game location, click the same "
            "location on the full map, enter or capture its live X/Y, then add the anchor. "
            "Use at least two locations separated on both axes."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.canvas = MapCalibrationCanvas(map_texture.image)
        self.canvas.pixelPicked.connect(self._pixel_picked)
        layout.addWidget(self.canvas, 1)

        entry = QtWidgets.QHBoxLayout()
        self.world_x = QtWidgets.QDoubleSpinBox()
        self.world_y = QtWidgets.QDoubleSpinBox()
        for spin in (self.world_x, self.world_y):
            spin.setRange(-10_000_000.0, 10_000_000.0)
            spin.setDecimals(3)
            spin.setSingleStep(1.0)
        self.pixel_label = QtWidgets.QLabel("Pixel: click the map")
        self.use_live = QtWidgets.QPushButton("Use live X/Y")
        self.add_anchor = QtWidgets.QPushButton("Add anchor")
        entry.addWidget(QtWidgets.QLabel("World X"))
        entry.addWidget(self.world_x)
        entry.addWidget(QtWidgets.QLabel("World Y"))
        entry.addWidget(self.world_y)
        entry.addWidget(self.use_live)
        entry.addWidget(self.pixel_label)
        entry.addWidget(self.add_anchor)
        layout.addLayout(entry)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["World X", "World Y", "Texture U", "Texture V"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        footer = QtWidgets.QHBoxLayout()
        self.remove_anchor = QtWidgets.QPushButton("Remove selected")
        self.clear_anchors = QtWidgets.QPushButton("Clear")
        footer.addWidget(self.remove_anchor)
        footer.addWidget(self.clear_anchors)
        footer.addStretch(1)
        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Apply
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        footer.addWidget(self.buttons)
        layout.addLayout(footer)

        self.use_live.clicked.connect(self._use_live_position)
        self.add_anchor.clicked.connect(self._add_anchor)
        self.remove_anchor.clicked.connect(self._remove_selected)
        self.clear_anchors.clicked.connect(self._clear)
        apply_button = self.buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Apply
        )
        apply_button.clicked.connect(self._apply)
        self.buttons.rejected.connect(self.reject)
        self._use_live_position()
        self._refresh_table()

    def _use_live_position(self) -> None:
        try:
            player = self.player_provider()
        except Exception:  # A stale UI callback must not break calibration.
            player = {}
        if not isinstance(player, dict):
            player = {}
        self.world_x.setValue(safe_float(player.get("x")))
        self.world_y.setValue(safe_float(player.get("y")))

    def _pixel_picked(self, u: float, v: float) -> None:
        self.pending_pixel = (u, v)
        self.pixel_label.setText(f"Pixel U {u:.1f}, V {v:.1f}")

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.anchors))
        for row, anchor in enumerate(self.anchors):
            for column, value in enumerate(anchor):
                self.table.setItem(row, column, QtWidgets.QTableWidgetItem(f"{value:.3f}"))
        self.canvas.set_anchors(self.anchors)

    def _add_anchor(self) -> None:
        if self.pending_pixel is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Calibration",
                "Click the matching point on the map first.",
            )
            return
        self.anchors.append(
            (
                self.world_x.value(),
                self.world_y.value(),
                self.pending_pixel[0],
                self.pending_pixel[1],
            )
        )
        self.pending_pixel = None
        self.canvas.pending_pixel = None
        self.pixel_label.setText("Pixel: click the map")
        self._refresh_table()

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.anchors):
                del self.anchors[row]
        self._refresh_table()

    def _clear(self) -> None:
        self.anchors.clear()
        self.pending_pixel = None
        self.canvas.pending_pixel = None
        self.pixel_label.setText("Pixel: click the map")
        self._refresh_table()

    def _apply(self) -> None:
        calibration = MapCalibration.fit_anchors(self.anchors)
        if calibration is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Calibration",
                "At least two anchors are required, with different world X "
                "and different world Y values.",
            )
            return
        self.result_calibration = calibration
        self.accept()
