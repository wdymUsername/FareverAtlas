"""Standalone always-on-top map overlay window (headless mirror)."""

from __future__ import annotations

import ctypes
import sys

from PySide6 import QtCore, QtGui, QtWidgets

from .config import (
    ASSET_ROOT,
    UI_LEVEL_MINUS_RELATIVE_PATH,
    UI_LEVEL_PLUS_RELATIVE_PATH,
    safe_int,
)
from .overlay_chrome import (
    OVERLAY_ZOOM_LEVELS,
    ZOOM_PANEL_STYLE,
    SquareResizeGrip,
)
from .overlay_policy import OverlayPlatformPolicy
from .pages.map.data import MapTexture, Snapshot
from .pages.map.radar import RadarWidget
from .platform_window import set_overlay_hit_testing
from .window_base import PersistentWindow


class MapOverlayWindow(OverlayPlatformPolicy, PersistentWindow):
    """Frameless square map-only window. Map is click-through until unlocked."""

    closedByUser = QtCore.Signal()
    # Small enough for a HUD corner; radar scales content to the viewport so
    # markers and chrome stay inside the frame.
    MIN_SIZE = 120
    _ZOOM_BTN = 28
    _ZOOM_MARGIN = 8

    def __init__(
        self,
        settings: QtCore.QSettings,
        map_texture: MapTexture | None,
    ):
        super().__init__(settings, "map_overlay")
        self._unlocked = False
        self._closing_quietly = False
        self._enforcing_square = False
        self._follow_enabled = False
        self._follow_drag_active = False
        self._last_game_rect: QtCore.QRect | None = None
        self._follow_offset = self._load_follow_offset()
        self._init_overlay_policy_timers()
        self.setWindowTitle("Farever Atlas — Map Overlay")
        self.setMinimumSize(self.MIN_SIZE, self.MIN_SIZE)
        # Flags + X11 type must be applied before geometry restore/show so KWin
        # never sees Utility (Qt.Tool). Geometry helpers must not undo this.
        self._apply_overlay_window_flags()
        self._apply_non_activating_attributes()
        self.finish_geometry(default_width=280, default_height=280)
        self._enforce_square()

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
            range(len(OVERLAY_ZOOM_LEVELS)),
            key=lambda index: abs(OVERLAY_ZOOM_LEVELS[index][0] - saved_radius),
        )
        radius, _label = OVERLAY_ZOOM_LEVELS[self._zoom_index]
        self.radar.set_zoom_radius(float(radius), immediate=True)

        self._build_zoom_buttons()
        self._build_resize_grips()
        self._set_grips_visible(False)

        opacity = safe_int(settings.value("map/overlay_opacity", 100), 100)
        self.set_opacity_percent(opacity)

    def attach_source_radar(self, source: RadarWidget) -> None:
        """Share map assets / FOW with the main radar for a strict visual mirror."""
        self.radar.map_texture = source.map_texture
        self.radar.fog = source.fog

    def sync_from(self, source: RadarWidget) -> None:
        self.radar.sync_view_from(source)
        # Overlay keeps its own zoom; re-assert after mirror sync.
        radius, _label = OVERLAY_ZOOM_LEVELS[self._zoom_index]
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
            self._apply_overlay_window_flags()
            self.show()
            # Do not call setWindowFlag helpers here — they recreate the native
            # window and have re-introduced Utility on Plasma. Flags are already
            # StaysOnTop + DoesNotAcceptFocus from _apply_overlay_window_flags.
            self.reapply_saved_geometry()
            self._enforce_square()
            self._position_zoom_buttons()
            self._schedule_overlay_settle()
        else:
            self._stop_overlay_timers()
            self.hide()

    def set_unlocked(self, unlocked: bool) -> None:
        was_unlocked = self._unlocked
        self._unlocked = bool(unlocked)
        if was_unlocked and not self._unlocked:
            self._follow_drag_active = False
            self._capture_follow_offset_from_geometry()
        self._set_grips_visible(self._unlocked and self.isVisible())
        self._sync_zoom_visibility()
        if self.isVisible():
            self._apply_input_mode()

    def set_follow_enabled(self, enabled: bool) -> None:
        self._follow_enabled = bool(enabled)

    def _load_follow_offset(self) -> QtCore.QPoint:
        raw = self._settings.value("map/overlay_follow_offset", "")
        text = str(raw or "").strip()
        if "," in text:
            try:
                left, right = text.split(",", 1)
                return QtCore.QPoint(int(left.strip()), int(right.strip()))
            except ValueError:
                pass
        return QtCore.QPoint(24, 24)

    def _save_follow_offset(self) -> None:
        self._settings.setValue(
            "map/overlay_follow_offset",
            f"{int(self._follow_offset.x())},{int(self._follow_offset.y())}",
        )

    def _set_follow_drag_active(self, active: bool) -> None:
        self._follow_drag_active = bool(active)

    def _capture_follow_offset_from_geometry(self) -> None:
        game = self._last_game_rect
        if game is None or not game.isValid():
            return
        self._follow_offset = QtCore.QPoint(
            self.x() - game.x(), self.y() - game.y()
        )
        self._save_follow_offset()

    def follow_game_rect(self, game: QtCore.QRect) -> None:
        """Keep the overlay at the stored offset inside ``game`` (global pixels)."""
        if not self._follow_enabled or not self.isVisible():
            return
        if self._unlocked or self._follow_drag_active:
            self._last_game_rect = QtCore.QRect(game) if game.isValid() else None
            return
        if not game.isValid() or game.width() < 64 or game.height() < 64:
            return
        self._last_game_rect = QtCore.QRect(game)
        side = max(self.MIN_SIZE, min(self.width(), self.height()))
        max_x = max(game.x(), game.right() - side + 1)
        max_y = max(game.y(), game.bottom() - side + 1)
        x = min(max(game.x() + self._follow_offset.x(), game.x()), max_x)
        y = min(max(game.y() + self._follow_offset.y(), game.y()), max_y)
        if (
            self.x() == x
            and self.y() == y
            and self.width() == side
            and self.height() == side
        ):
            return
        self._enforcing_square = True
        try:
            self.setGeometry(x, y, side, side)
        finally:
            self._enforcing_square = False

    def _control_hit_rects(self) -> list[QtCore.QRect]:
        if (
            not hasattr(self, "map_controls_overlay")
            or not self.map_controls_overlay.isVisible()
        ):
            return []
        return [self.map_controls_overlay.geometry()]

    def _apply_input_mode(self) -> None:
        # Avoid ensure_no_activate_hint/setWindowFlag here — recreating the
        # native window on Plasma can tag it Utility again. Flags are owned by
        # _apply_overlay_window_flags.
        self._clear_x11_utility_types()
        set_overlay_hit_testing(
            self,
            interactive=self._unlocked,
            control_rects=self._control_hit_rects(),
        )

    def _build_zoom_buttons(self) -> None:
        # Match the main map zoom chrome: stacked +/- icons in a bordered panel.
        self.map_controls_overlay = QtWidgets.QWidget(self)
        self.map_controls_overlay.setObjectName("mapControlsOverlay")
        self.map_controls_overlay.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_NoMousePropagation, True
        )

        self.zoom_panel = QtWidgets.QWidget(self.map_controls_overlay)
        self.zoom_panel.setObjectName("zoomPanel")
        zoom_layout = QtWidgets.QVBoxLayout(self.zoom_panel)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(0)

        self.zoom_in_button = QtWidgets.QToolButton(self.zoom_panel)
        self.zoom_in_button.setObjectName("zoomButton")
        self.zoom_in_button.setText("")
        self.zoom_in_button.setToolTip("Zoom in")
        self.zoom_in_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoom_in_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self.zoom_in_button.setFixedSize(self._ZOOM_BTN, self._ZOOM_BTN)
        self.zoom_in_button.setIconSize(QtCore.QSize(14, 14))
        self.zoom_in_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        zoom_in_icon = QtGui.QIcon(str(ASSET_ROOT / UI_LEVEL_PLUS_RELATIVE_PATH))
        if not zoom_in_icon.isNull():
            self.zoom_in_button.setIcon(zoom_in_icon)
        self.zoom_in_button.clicked.connect(lambda: self._step_zoom(-1))

        self.zoom_divider = QtWidgets.QFrame(self.zoom_panel)
        self.zoom_divider.setObjectName("zoomDivider")
        self.zoom_divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.zoom_divider.setFixedHeight(1)

        self.zoom_out_button = QtWidgets.QToolButton(self.zoom_panel)
        self.zoom_out_button.setObjectName("zoomButton")
        self.zoom_out_button.setText("")
        self.zoom_out_button.setToolTip("Zoom out")
        self.zoom_out_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.zoom_out_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self.zoom_out_button.setFixedSize(self._ZOOM_BTN, self._ZOOM_BTN)
        self.zoom_out_button.setIconSize(QtCore.QSize(14, 14))
        self.zoom_out_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        zoom_out_icon = QtGui.QIcon(str(ASSET_ROOT / UI_LEVEL_MINUS_RELATIVE_PATH))
        if not zoom_out_icon.isNull():
            self.zoom_out_button.setIcon(zoom_out_icon)
        self.zoom_out_button.clicked.connect(lambda: self._step_zoom(1))

        zoom_layout.addWidget(self.zoom_in_button)
        zoom_layout.addWidget(self.zoom_divider)
        zoom_layout.addWidget(self.zoom_out_button)

        controls_layout = QtWidgets.QVBoxLayout(self.map_controls_overlay)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)
        controls_layout.addWidget(self.zoom_panel)

        self.setStyleSheet(self.styleSheet() + ZOOM_PANEL_STYLE)
        self._sync_zoom_visibility()
        self._position_zoom_buttons()
        self._sync_zoom_buttons()

    def _sync_zoom_visibility(self) -> None:
        if not hasattr(self, "map_controls_overlay"):
            return
        # Locked overlay is click-through HUD only — no zoom chrome.
        visible = bool(self._unlocked and self.isVisible())
        self.map_controls_overlay.setVisible(visible)

    def _position_zoom_buttons(self) -> None:
        if not hasattr(self, "map_controls_overlay"):
            return
        self.zoom_panel.adjustSize()
        self.map_controls_overlay.adjustSize()
        margin = self._ZOOM_MARGIN
        width = self.map_controls_overlay.width()
        height = self.map_controls_overlay.height()
        x = max(margin, self.width() - margin - width)
        y = max(margin, self.height() - margin - height)
        self.map_controls_overlay.setGeometry(x, y, width, height)
        self.map_controls_overlay.raise_()

    def _sync_zoom_buttons(self) -> None:
        if not hasattr(self, "zoom_in_button"):
            return
        self.zoom_in_button.setEnabled(self._zoom_index > 0)
        self.zoom_out_button.setEnabled(
            self._zoom_index < len(OVERLAY_ZOOM_LEVELS) - 1
        )

    def _step_zoom(self, delta: int) -> None:
        # Same convention as the main map: negative delta = zoom in.
        new_index = max(
            0, min(len(OVERLAY_ZOOM_LEVELS) - 1, self._zoom_index + int(delta))
        )
        if new_index == self._zoom_index:
            return
        self._zoom_index = new_index
        radius, _label = OVERLAY_ZOOM_LEVELS[self._zoom_index]
        self.radar.set_zoom_radius(float(radius))
        self._settings.setValue("map/overlay_zoom_radius", int(radius))
        self._sync_zoom_buttons()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if watched is self.radar and self._unlocked:
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                mouse = event
                if (
                    isinstance(mouse, QtGui.QMouseEvent)
                    and mouse.button() == QtCore.Qt.MouseButton.LeftButton
                ):
                    self._set_follow_drag_active(True)
                    handle = self.windowHandle()
                    if handle is not None and handle.startSystemMove():
                        return True
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                if self._follow_drag_active:
                    self._set_follow_drag_active(False)
                    self._capture_follow_offset_from_geometry()
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
        self._apply_overlay_window_flags()
        self._enforce_square()
        self._set_grips_visible(self._unlocked)
        self._sync_zoom_visibility()
        self._position_zoom_buttons()
        self._schedule_overlay_settle()

    def hideEvent(self, event: QtGui.QHideEvent) -> None:  # noqa: N802
        self._stop_overlay_timers()
        super().hideEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if self._closing_quietly:
            self._stop_overlay_timers()
            super().closeEvent(event)
            return
        app = QtWidgets.QApplication.instance()
        if app is not None and app.closingDown():
            self._stop_overlay_timers()
            super().closeEvent(event)
            return
        if self._unlocked:
            event.ignore()
            self._stop_overlay_timers()
            self.hide()
            self.closedByUser.emit()
            return
        self._stop_overlay_timers()
        super().closeEvent(event)

    def force_close(self) -> None:
        self._closing_quietly = True
        try:
            self._stop_overlay_timers()
            self.close()
        finally:
            self._closing_quietly = False

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._enforcing_square and self.width() != self.height():
            # Defer one tick so we win over native/system resize geometry.
            old = QtCore.QSize(event.oldSize())
            QtCore.QTimer.singleShot(0, lambda: self._enforce_square(old))
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
            name: SquareResizeGrip(self, edges, shape)
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
        if hasattr(self, "map_controls_overlay"):
            self.map_controls_overlay.raise_()

    def _set_grips_visible(self, visible: bool) -> None:
        if not hasattr(self, "_resize_grips"):
            return
        for grip in self._resize_grips.values():
            grip.setVisible(bool(visible))
