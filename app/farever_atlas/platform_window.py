"""Native helpers for overlay hit-testing and no-activate windows.

Linux always-on-top and input shaping are reliable under the xcb/XWayland
path the app already prefers. Pure Wayland remains best-effort.

Important: Qt 6's xcb platform must be shaped via libxcb-shape against Qt's
``connection()``, not via Xlib ``Display*`` + ``XFlush``. Mixing Xlib Shape
calls with Qt's xcb event loop has SIGSEGV'd in ``XSync``/``XFlush``.
"""

from __future__ import annotations

import ctypes
import sys
from typing import Sequence

from PySide6 import QtCore, QtWidgets


def ensure_no_activate_hint(widget: QtWidgets.QWidget) -> None:
    """Keep WindowDoesNotAcceptFocus set (safe to call repeatedly)."""
    flag = QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
    if not (widget.windowFlags() & flag):
        was_visible = widget.isVisible()
        widget.setWindowFlag(flag, True)
        handle = widget.windowHandle()
        if handle is not None:
            handle.setFlag(flag, True)
        if was_visible:
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            widget.show()
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, False)


def set_overlay_hit_testing(
    widget: QtWidgets.QWidget,
    *,
    interactive: bool,
    control_rects: Sequence[QtCore.QRect] = (),
) -> None:
    """Configure which parts of the overlay accept mouse input.

    interactive=True  → whole window (unlocked move/resize).
    interactive=False → only ``control_rects`` (widget-local), so the map stays
    click-through to the game while zoom buttons remain usable.
    """
    # Never use WindowTransparentForInput here — it would eat the controls too.
    transparent = QtCore.Qt.WindowType.WindowTransparentForInput
    if widget.windowFlags() & transparent:
        was_visible = widget.isVisible()
        widget.setWindowFlag(transparent, False)
        handle = widget.windowHandle()
        if handle is not None:
            handle.setFlag(transparent, False)
        if was_visible:
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            widget.show()
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, False)

    if sys.platform == "win32":
        _apply_windows_noactivate(widget)
        # Hit-testing is handled in MapOverlayWindow.nativeEvent (HTTRANSPARENT).
        return
    if sys.platform.startswith("linux"):
        if interactive:
            _xcb_set_input_from_bounding(widget)
        else:
            _xcb_set_input_rects(widget, control_rects)


def _hwnd(widget: QtWidgets.QWidget) -> int | None:
    handle = widget.windowHandle()
    if handle is None:
        return None
    try:
        wid = int(handle.winId())
    except (TypeError, ValueError, RuntimeError):
        return None
    return wid or None


def _apply_windows_noactivate(widget: QtWidgets.QWidget) -> None:
    hwnd = _hwnd(widget)
    if hwnd is None:
        return
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    gwl_exstyle = -20
    ws_ex_noactivate = 0x08000000
    ws_ex_transparent = 0x00000020
    get_long = user32.GetWindowLongW
    set_long = user32.SetWindowLongW
    get_long.restype = ctypes.c_long
    set_long.restype = ctypes.c_long
    ex_style = int(get_long(ctypes.c_void_p(hwnd), gwl_exstyle))
    # Keep NOACTIVATE; never use WS_EX_TRANSPARENT (blocks control clicks).
    ex_style |= ws_ex_noactivate
    ex_style &= ~ws_ex_transparent
    set_long(ctypes.c_void_p(hwnd), gwl_exstyle, ex_style)


class _XcbRectangle(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int16),
        ("y", ctypes.c_int16),
        ("width", ctypes.c_uint16),
        ("height", ctypes.c_uint16),
    ]


# xcb_shape_op_t / xcb_shape_kind_t
_XCB_SHAPE_SO_SET = 0
_XCB_SHAPE_SK_BOUNDING = 0
_XCB_SHAPE_SK_INPUT = 2
_XCB_SHAPE_YX_BANDED = 1


def _qt_xcb_connection() -> int | None:
    """Return Qt's xcb_connection_t* as an int address."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    try:
        iface = app.nativeInterface()
    except Exception:
        return None
    if iface is None or not hasattr(iface, "connection"):
        return None
    try:
        raw = iface.connection()
    except Exception:
        return None
    if not raw:
        return None
    return int(raw)


def _xcb_libs():
    try:
        return ctypes.CDLL("libxcb.so.1"), ctypes.CDLL("libxcb-shape.so.0")
    except OSError:
        return None, None


def _xcb_shape_rectangles(
    widget: QtWidgets.QWidget,
    *,
    kind: int,
    rects: Sequence[QtCore.QRect],
) -> None:
    xid = _hwnd(widget)
    conn = _qt_xcb_connection()
    xcb, shape = _xcb_libs()
    if xid is None or conn is None or xcb is None or shape is None:
        return

    valid = [
        r
        for r in rects
        if isinstance(r, QtCore.QRect) and r.width() > 0 and r.height() > 0
    ]
    # Never pass rectangles_len=0 with a NULL pointer — use a 1x1 hole until
    # controls have laid out.
    if not valid:
        valid = [QtCore.QRect(0, 0, 1, 1)]

    array = (_XcbRectangle * len(valid))()
    for index, rect in enumerate(valid):
        array[index].x = int(rect.x())
        array[index].y = int(rect.y())
        array[index].width = max(1, int(rect.width()))
        array[index].height = max(1, int(rect.height()))

    shape.xcb_shape_rectangles.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint8,
        ctypes.c_uint8,
        ctypes.c_uint8,
        ctypes.c_uint32,
        ctypes.c_int16,
        ctypes.c_int16,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    shape.xcb_shape_rectangles.restype = ctypes.c_uint32
    xcb.xcb_flush.argtypes = [ctypes.c_void_p]
    xcb.xcb_flush.restype = ctypes.c_int

    try:
        shape.xcb_shape_rectangles(
            ctypes.c_void_p(conn),
            _XCB_SHAPE_SO_SET,
            kind,
            _XCB_SHAPE_YX_BANDED,
            ctypes.c_uint32(xid),
            0,
            0,
            len(valid),
            ctypes.byref(array),
        )
        xcb.xcb_flush(ctypes.c_void_p(conn))
    except Exception:
        # Shaping is best-effort; never take down the UI process.
        return


def _xcb_set_input_from_bounding(widget: QtWidgets.QWidget) -> None:
    """Restore full-window input by copying the bounding shape into input."""
    xid = _hwnd(widget)
    conn = _qt_xcb_connection()
    xcb, shape = _xcb_libs()
    if xid is None or conn is None or xcb is None or shape is None:
        return

    shape.xcb_shape_mask.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint8,
        ctypes.c_uint8,
        ctypes.c_uint32,
        ctypes.c_int16,
        ctypes.c_int16,
        ctypes.c_uint32,
    ]
    shape.xcb_shape_mask.restype = ctypes.c_uint32
    xcb.xcb_flush.argtypes = [ctypes.c_void_p]
    xcb.xcb_flush.restype = ctypes.c_int

    # XCB_SHAPE_SO_SET + source pixmap None (XCB_NONE=0) resets to default.
    # Copy bounding → input via xcb_shape_combine.
    shape.xcb_shape_combine.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint8,
        ctypes.c_uint8,
        ctypes.c_uint8,
        ctypes.c_uint32,
        ctypes.c_int16,
        ctypes.c_int16,
        ctypes.c_uint32,
    ]
    shape.xcb_shape_combine.restype = ctypes.c_uint32
    try:
        shape.xcb_shape_combine(
            ctypes.c_void_p(conn),
            _XCB_SHAPE_SO_SET,
            _XCB_SHAPE_SK_INPUT,
            _XCB_SHAPE_SK_BOUNDING,
            ctypes.c_uint32(xid),
            0,
            0,
            ctypes.c_uint32(xid),
        )
        xcb.xcb_flush(ctypes.c_void_p(conn))
    except Exception:
        return


def _xcb_set_input_rects(
    widget: QtWidgets.QWidget, rects: Sequence[QtCore.QRect]
) -> None:
    _xcb_shape_rectangles(widget, kind=_XCB_SHAPE_SK_INPUT, rects=rects)
