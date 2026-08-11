"""Standalone always-on-top map overlay window (headless mirror)."""

from __future__ import annotations

import ctypes
import sys

from PySide6 import QtCore, QtGui, QtWidgets

from .config import safe_int
from .pages.map.data import MapTexture, Snapshot
from .pages.map.radar import RadarWidget
from .pages.map.widgets import WindowResizeGrip
from .platform_window import ensure_no_activate_hint, set_overlay_hit_testing
from .window_base import PersistentWindow, apply_always_on_top

# Same ladder as the main map; overlay zoom is independent.
_OVERLAY_ZOOM_LEVELS = (
    (25, "8x"),
    (50, "4x"),
    (100, "2x"),
    (200, "1x"),
    (300, "0.7x"),
    (450, "0.5x"),
    (650, "0.35x"),
    (900, "0.25x"),
    (1250, "0.2x"),
    (1600, "0.15x"),
    (2000, "0.1x"),
)

_ZOOM_BTN_STYLE = """
QToolButton#overlayZoomButton {
    background: rgba(18, 24, 32, 210);
    color: #e6edf3;
    border: 1px solid #4a5a6a;
    border-radius: 3px;
    font-weight: 700;
    font-size: 14px;
    padding: 0;
}
QToolButton#overlayZoomButton:hover {
    background: rgba(40, 56, 72, 230);
    border-color: #7a90a4;
}
QToolButton#overlayZoomButton:pressed {
    background: rgba(52, 120, 183, 220);
}
QToolButton#overlayZoomButton:disabled {
    color: #6a7682;
    border-color: #2d3b48;
}
"""


class MapOverlayWindow(PersistentWindow):
    """Frameless square map-only window. Map is click-through until unlocked."""

    closedByUser = QtCore.Signal()
    # Small enough for a HUD corner; radar scales content to the viewport so
    # markers and chrome stay inside the frame.
    MIN_SIZE = 120
    _ZOOM_BTN = 24
    _ZOOM_MARGIN = 6

    def __init__(
        self,
        settings: QtCore.QSettings,
        map_texture: MapTexture | None,
    ):
        super().__init__(settings, "map_overlay")
        self._unlocked = False
        self._closing_quietly = False
        self.setWindowTitle("Farever Atlas — Map Overlay")
        self.resize(280, 280)
        self.setMinimumSize(self.MIN_SIZE, self.MIN_SIZE)

        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
            | QtCore.Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

        self.radar = RadarWidget(map_texture)
        self.radar.interaction_enabled = False
        self.radar.scale_to_viewport = True
        self.radar.rounded = False
        self.radar.setMinimumSize(self.MIN_SIZE, self.MIN_SIZE)
        self.radar.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.radar.setObjectName("mapOverlayCanvas")
        self.radar.installEventFilter(self)
        self.setCentralWidget(self.radar)

        saved_radius = safe_int(settings.value("map/overlay_zoom_radius", 200), 200)
        self._zoom_index = min(
            range(len(_OVERLAY_ZOOM_LEVELS)),
            key=lambda index: abs(_OVERLAY_ZOOM_LEVELS[index][0] - saved_radius),
        )
        radius, _label = _OVERLAY_ZOOM_LEVELS[self._zoom_index]
        self.radar.set_zoom_radius(float(radius), immediate=True)

        self._build_zoom_buttons()
        self._build_resize_grips()
        self._set_grips_visible(False)
        apply_always_on_top(self, True, activate=False)

        opacity = safe_int(settings.value("map/overlay_opacity", 100), 100)
        self.set_opacity_percent(opacity)

    def attach_source_radar(self, source: RadarWidget) -> None:
        """Share map assets / FOW with the main radar for a strict visual mirror."""
        self.radar.map_texture = source.map_texture
        self.radar.fog = source.fog

    def sync_from(self, source: RadarWidget) -> None:
        self.radar.sync_view_from(source)
        # Overlay keeps its own zoom; re-assert after mirror sync.
        radius, _label = _OVERLAY_ZOOM_LEVELS[self._zoom_index]
        self.radar.set_zoom_radius(float(radius), immediate=True)
        self.radar.rounded = False
        self.radar.scale_to_viewport = True
        self.radar.update()
        self._sync_zoom_buttons()

    def update_snapshot(self, snapshot: Snapshot) -> None:
        if not self.isVisible():
            return
        self.radar.set_snapshot(snapshot)

    def set_opacity_percent(self, percent: int) -> None:
        value = max(5, min(100, int(percent)))
        self.setWindowOpacity(value / 100.0)
        self._settings.setValue("map/overlay_opacity", value)

    def set_overlay_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if visible:
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.show()
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            ensure_no_activate_hint(self)
            apply_always_on_top(self, True, activate=False)
            # Position controls before shaping input; empty rect lists are unsafe
            # on some X11 Shape implementations.
            self._position_zoom_buttons()
            self._apply_input_mode()
            QtCore.QTimer.singleShot(0, self._apply_input_mode)
        else:
            self.hide()

    def set_unlocked(self, unlocked: bool) -> None:
        self._unlocked = bool(unlocked)
        self._set_grips_visible(self._unlocked and self.isVisible())
        if self.isVisible():
            self._apply_input_mode()

    def _control_hit_rects(self) -> list[QtCore.QRect]:
        return [
            btn.geometry()
            for btn in (self.zoom_in_button, self.zoom_out_button)
            if btn.isVisible()
        ]

    def _apply_input_mode(self) -> None:
        ensure_no_activate_hint(self)
        set_overlay_hit_testing(
            self,
            interactive=self._unlocked,
            control_rects=self._control_hit_rects(),
        )

    def _build_zoom_buttons(self) -> None:
        self.zoom_in_button = QtWidgets.QToolButton(self)
        self.zoom_in_button.setObjectName("overlayZoomButton")
        self.zoom_in_button.setText("+")
        self.zoom_in_button.setToolTip("Zoom in")
        self.zoom_in_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoom_in_button.setFixedSize(self._ZOOM_BTN, self._ZOOM_BTN)
        self.zoom_in_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.zoom_in_button.clicked.connect(lambda: self._step_zoom(1))

        self.zoom_out_button = QtWidgets.QToolButton(self)
        self.zoom_out_button.setObjectName("overlayZoomButton")
        self.zoom_out_button.setText("−")
        self.zoom_out_button.setToolTip("Zoom out")
        self.zoom_out_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoom_out_button.setFixedSize(self._ZOOM_BTN, self._ZOOM_BTN)
        self.zoom_out_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.zoom_out_button.clicked.connect(lambda: self._step_zoom(-1))

        self.setStyleSheet(self.styleSheet() + _ZOOM_BTN_STYLE)
        self._position_zoom_buttons()
        self._sync_zoom_buttons()

    def _position_zoom_buttons(self) -> None:
        if not hasattr(self, "zoom_in_button"):
            return
        margin = self._ZOOM_MARGIN
        size = self._ZOOM_BTN
        gap = 4
        x = max(margin, self.width() - margin - size)
        y_out = max(margin, self.height() - margin - size)
        y_in = max(margin, y_out - gap - size)
        self.zoom_in_button.setGeometry(x, y_in, size, size)
        self.zoom_out_button.setGeometry(x, y_out, size, size)
        self.zoom_in_button.raise_()
        self.zoom_out_button.raise_()

    def _sync_zoom_buttons(self) -> None:
        if not hasattr(self, "zoom_in_button"):
            return
        self.zoom_in_button.setEnabled(self._zoom_index > 0)
        self.zoom_out_button.setEnabled(
            self._zoom_index < len(_OVERLAY_ZOOM_LEVELS) - 1
        )

    def _step_zoom(self, direction: int) -> None:
        # Same convention as the main map: positive = zoom in (smaller radius).
        new_index = max(
            0, min(len(_OVERLAY_ZOOM_LEVELS) - 1, self._zoom_index - int(direction))
        )
        if new_index == self._zoom_index:
            return
        self._zoom_index = new_index
        radius, _label = _OVERLAY_ZOOM_LEVELS[self._zoom_index]
        self.radar.set_zoom_radius(float(radius))
        self._settings.setValue("map/overlay_zoom_radius", int(radius))
        self._sync_zoom_buttons()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if (
            watched is self.radar
            and self._unlocked
            and event.type() == QtCore.QEvent.Type.MouseButtonPress
        ):
            mouse = event
            if (
                isinstance(mouse, QtGui.QMouseEvent)
                and mouse.button() == QtCore.Qt.MouseButton.LeftButton
            ):
                handle = self.windowHandle()
                if handle is not None and handle.startSystemMove():
                    return True
        return super().eventFilter(watched, event)

    def nativeEvent(self, eventType, message):  # noqa: N802
        # Windows: map area returns HTTRANSPARENT so clicks reach the game;
        # zoom buttons stay HTCLIENT.
        if sys.platform == "win32" and not self._unlocked:
            try:
                et = bytes(eventType)
            except TypeError:
                et = bytes(str(eventType), "utf-8")
            if et.startswith(b"windows_generic_MSG"):
                from ctypes import wintypes

                try:
                    msg = wintypes.MSG.from_address(int(message))
                except (TypeError, ValueError, OverflowError):
                    return super().nativeEvent(eventType, message)
                wm_nchittest = 0x0084
                ht_client = 1
                ht_transparent = -1
                if int(msg.message) == wm_nchittest:
                    packed = int(msg.lParam) & 0xFFFFFFFF
                    screen_x = ctypes.c_short(packed & 0xFFFF).value
                    screen_y = ctypes.c_short((packed >> 16) & 0xFFFF).value
                    local = self.mapFromGlobal(QtCore.QPoint(screen_x, screen_y))
                    for rect in self._control_hit_rects():
                        if rect.contains(local):
                            return True, ht_client
                    return True, ht_transparent
        return super().nativeEvent(eventType, message)

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        ensure_no_activate_hint(self)
        apply_always_on_top(self, True, activate=False)
        self._set_grips_visible(self._unlocked)
        self._position_zoom_buttons()
        QtCore.QTimer.singleShot(0, self._apply_input_mode)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if self._closing_quietly:
            super().closeEvent(event)
            return
        app = QtWidgets.QApplication.instance()
        if app is not None and app.closingDown():
            super().closeEvent(event)
            return
        if self._unlocked:
            event.ignore()
            self.hide()
            self.closedByUser.emit()
            return
        super().closeEvent(event)

    def force_close(self) -> None:
        self._closing_quietly = True
        try:
            self.close()
        finally:
            self._closing_quietly = False

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_resize_grips()
        self._position_zoom_buttons()
        if self.isVisible():
            self._apply_input_mode()

    def _build_resize_grips(self) -> None:
        edge = QtCore.Qt.Edge
        cursor = QtCore.Qt.CursorShape
        definitions = {
            "top": (edge.TopEdge, cursor.SizeVerCursor),
            "bottom": (edge.BottomEdge, cursor.SizeVerCursor),
            "left": (edge.LeftEdge, cursor.SizeHorCursor),
            "right": (edge.RightEdge, cursor.SizeHorCursor),
            "top_left": (edge.TopEdge | edge.LeftEdge, cursor.SizeFDiagCursor),
            "top_right": (edge.TopEdge | edge.RightEdge, cursor.SizeBDiagCursor),
            "bottom_left": (edge.BottomEdge | edge.LeftEdge, cursor.SizeBDiagCursor),
            "bottom_right": (
                edge.BottomEdge | edge.RightEdge,
                cursor.SizeFDiagCursor,
            ),
        }
        self._resize_grips = {
            name: WindowResizeGrip(self, edges, shape)
            for name, (edges, shape) in definitions.items()
        }
        self._position_resize_grips()

    def _position_resize_grips(self) -> None:
        if not hasattr(self, "_resize_grips"):
            return
        edge_width = 6
        corner_size = 12
        width = self.width()
        height = self.height()
        geometries = {
            "top": (corner_size, 0, max(0, width - 2 * corner_size), edge_width),
            "bottom": (
                corner_size,
                height - edge_width,
                max(0, width - 2 * corner_size),
                edge_width,
            ),
            "left": (0, corner_size, edge_width, max(0, height - 2 * corner_size)),
            "right": (
                width - edge_width,
                corner_size,
                edge_width,
                max(0, height - 2 * corner_size),
            ),
            "top_left": (0, 0, corner_size, corner_size),
            "top_right": (width - corner_size, 0, corner_size, corner_size),
            "bottom_left": (0, height - corner_size, corner_size, corner_size),
            "bottom_right": (
                width - corner_size,
                height - corner_size,
                corner_size,
                corner_size,
            ),
        }
        for name, geometry in geometries.items():
            grip = self._resize_grips[name]
            grip.setGeometry(*geometry)
            grip.raise_()
        if hasattr(self, "zoom_in_button"):
            self.zoom_in_button.raise_()
            self.zoom_out_button.raise_()

    def _set_grips_visible(self, visible: bool) -> None:
        if not hasattr(self, "_resize_grips"):
            return
        for grip in self._resize_grips.values():
            grip.setVisible(bool(visible))
