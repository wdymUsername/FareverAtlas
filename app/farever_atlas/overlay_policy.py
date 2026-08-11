"""Overlay window-manager / Plasma policy (flags, settle, attention, square).

Kept separate from zoom/grip chrome so X11 regressions stay easy to isolate.
"""

from __future__ import annotations

import sys

from PySide6 import QtCore, QtGui, QtWidgets

from .platform_window import clear_window_attention, window_demands_attention


class OverlayPlatformPolicy:
    """Mixin for :class:`~farever_atlas.map_overlay_window.MapOverlayWindow`."""

    MIN_SIZE: int
    _enforcing_square: bool
    _settle_attention_ms: int
    _settle_timer: QtCore.QTimer
    _delayed_attention_timer: QtCore.QTimer
    _attention_watch_timer: QtCore.QTimer
    _geometry_restored: bool

    def _init_overlay_policy_timers(self) -> None:
        self._settle_attention_ms = 100
        self._settle_timer = QtCore.QTimer(self)  # type: ignore[arg-type]
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(0)
        self._settle_timer.timeout.connect(self._run_overlay_settle)
        self._delayed_attention_timer = QtCore.QTimer(self)  # type: ignore[arg-type]
        self._delayed_attention_timer.setSingleShot(True)
        self._delayed_attention_timer.timeout.connect(self._clear_attention_if_visible)
        self._attention_watch_timer = QtCore.QTimer(self)  # type: ignore[arg-type]
        self._attention_watch_timer.setInterval(500)
        self._attention_watch_timer.timeout.connect(self._poll_window_attention)

    def _overlay_window_flags(self) -> QtCore.Qt.WindowType:
        # Normal top-level Window — never Tool/Utility. Qt.Tool maps to
        # _NET_WM_WINDOW_TYPE_UTILITY (KWin type 8), which breaks Plasma panel
        # autohide while the overlay stays above the game.
        return (
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
        )

    def _clear_x11_utility_types(self) -> None:
        """Force KWin away from Utility/Dock/etc. even after flag tweaks."""
        if not sys.platform.startswith("linux"):
            return
        attr = QtCore.Qt.WidgetAttribute
        for name in (
            "WA_X11NetWmWindowTypeUtility",
            "WA_X11NetWmWindowTypeDock",
            "WA_X11NetWmWindowTypeNotification",
            "WA_X11NetWmWindowTypeToolBar",
            "WA_X11NetWmWindowTypeToolTip",
            "WA_X11NetWmWindowTypeSplash",
            "WA_X11NetWmWindowTypeDialog",
        ):
            value = getattr(attr, name, None)
            if value is not None:
                self.setAttribute(value, False)  # type: ignore[attr-defined]

    def _apply_overlay_window_flags(self) -> None:
        """Re-assert normal Window flags; preserve geometry across recreates."""
        wanted = self._overlay_window_flags()
        current = self.windowFlags()  # type: ignore[attr-defined]
        type_mask = QtCore.Qt.WindowType.WindowType_Mask
        window_type = current & type_mask
        hint_bits = current & ~type_mask
        wanted_hints = wanted & ~type_mask
        needs_rewrite = (
            window_type != QtCore.Qt.WindowType.Window or hint_bits != wanted_hints
        )
        if not needs_rewrite:
            self._clear_x11_utility_types()
            return
        was_visible = self.isVisible()  # type: ignore[attr-defined]
        geometry = (
            self.saveGeometry()  # type: ignore[attr-defined]
            if (was_visible or self._geometry_restored)
            else None
        )
        self.setWindowFlags(wanted)  # type: ignore[attr-defined]
        self._clear_x11_utility_types()
        if was_visible:
            self.show()  # type: ignore[attr-defined]
        if geometry is not None:
            self.restoreGeometry(geometry)  # type: ignore[attr-defined]

    def _schedule_overlay_settle(self, *, delayed_attention_ms: int = 100) -> None:
        """Coalesce post-show Plasma/geometry/input fixes onto one timer tick."""
        self._settle_attention_ms = max(0, int(delayed_attention_ms))
        self._delayed_attention_timer.stop()
        self._settle_timer.start()

    def _run_overlay_settle(self) -> None:
        if not self.isVisible():  # type: ignore[attr-defined]
            self._stop_overlay_timers()
            return
        self._clear_x11_utility_types()
        clear_window_attention(self)  # type: ignore[arg-type]
        self._enforce_square()
        self._position_zoom_buttons()  # type: ignore[attr-defined]
        self._apply_input_mode()  # type: ignore[attr-defined]
        self._start_attention_watch()
        if self._settle_attention_ms > 0:
            self._delayed_attention_timer.start(self._settle_attention_ms)

    def _clear_attention_if_visible(self) -> None:
        if self.isVisible():  # type: ignore[attr-defined]
            clear_window_attention(self)  # type: ignore[arg-type]

    def _start_attention_watch(self) -> None:
        if not self.isVisible():  # type: ignore[attr-defined]
            self._attention_watch_timer.stop()
            return
        if not self._attention_watch_timer.isActive():
            self._attention_watch_timer.start()

    def _poll_window_attention(self) -> None:
        if not self.isVisible():  # type: ignore[attr-defined]
            self._attention_watch_timer.stop()
            return
        if window_demands_attention(self):  # type: ignore[arg-type]
            clear_window_attention(self)  # type: ignore[arg-type]

    def _stop_overlay_timers(self) -> None:
        self._settle_timer.stop()
        self._delayed_attention_timer.stop()
        self._attention_watch_timer.stop()

    def _square_side(
        self, width: int, height: int, old: QtCore.QSize | None = None
    ) -> int:
        """Pick the side length for a 1:1 frame from a proposed size."""
        if old is not None and old.isValid():
            dw = abs(int(width) - old.width())
            dh = abs(int(height) - old.height())
            side = int(width) if dw >= dh else int(height)
            return max(self.MIN_SIZE, side)
        return max(self.MIN_SIZE, min(int(width), int(height)))

    def _enforce_square(self, old: QtCore.QSize | None = None) -> None:
        """Keep width == height (radar overlay is always square)."""
        if self._enforcing_square:
            return
        width = self.width()  # type: ignore[attr-defined]
        height = self.height()  # type: ignore[attr-defined]
        if width == height and width >= self.MIN_SIZE:
            return
        side = self._square_side(width, height, old)
        self._enforcing_square = True
        try:
            # setGeometry (not resize) so KWin cannot leave a stale tall frame.
            self.setGeometry(self.x(), self.y(), side, side)  # type: ignore[attr-defined]
        finally:
            self._enforcing_square = False
        # Persist immediately after a real correction so the next restore is
        # already square (avoids a tall flash before snap on restart).
        # Only runs when we changed size — no-ops above never touch settings.
        # Uses PersistentWindow._persist_geometry when mixed in; respects
        # app/restore_window_positions and does not alter follow offset keys.
        persist = getattr(self, "_persist_geometry", None)
        if callable(persist):
            persist()

    def _apply_non_activating_attributes(self) -> None:
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False)  # type: ignore[attr-defined]
        self.setAutoFillBackground(False)  # type: ignore[attr-defined]
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)  # type: ignore[attr-defined]
        if sys.platform.startswith("linux"):
            x11_nofocus = getattr(
                QtCore.Qt.WidgetAttribute, "WA_X11DoNotAcceptFocus", None
            )
            if x11_nofocus is not None:
                self.setAttribute(x11_nofocus, True)  # type: ignore[attr-defined]
