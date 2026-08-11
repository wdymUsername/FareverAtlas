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
        geometry = widget.saveGeometry() if was_visible else None
        widget.setWindowFlag(flag, True)
        handle = widget.windowHandle()
        if handle is not None:
            handle.setFlag(flag, True)
        if was_visible:
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            widget.show()
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            if geometry is not None:
                widget.restoreGeometry(geometry)


def clear_window_attention(widget: QtWidgets.QWidget) -> None:
    """Drop urgency / DEMANDS_ATTENTION so Plasma panels can auto-hide.

    Live overlay windows were observed with::

        _NET_WM_STATE = DEMANDS_ATTENTION, ABOVE, STAYS_ON_TOP

    Plasma keeps auto-hide panels visible while any window demands attention
    (Task Manager "Unhide when a window wants attention"). Always-on-top alone
    is fine; urgency is not.
    """
    app = QtWidgets.QApplication.instance()
    if app is not None:
        try:
            # msec=0 cancels any current attention indication.
            app.alert(widget, 0)
        except Exception:
            pass
    handle = widget.windowHandle()
    if handle is not None:
        try:
            # Qt 6: clears the platform urgency hint when supported.
            handle.setFlag(QtCore.Qt.WindowType.WindowDoesNotAcceptFocus, True)
        except Exception:
            pass
    if sys.platform.startswith("linux"):
        _xcb_net_wm_state(widget, add=False, atom_name="_NET_WM_STATE_DEMANDS_ATTENTION")
        # Keep the overlay out of the task manager attention path entirely.
        _xcb_net_wm_state(widget, add=True, atom_name="_NET_WM_STATE_SKIP_TASKBAR")
        _xcb_net_wm_state(widget, add=True, atom_name="_NET_WM_STATE_SKIP_PAGER")
        _xcb_force_normal_window_type(widget)


def window_demands_attention(widget: QtWidgets.QWidget) -> bool:
    """True if the window currently has ``_NET_WM_STATE_DEMANDS_ATTENTION``."""
    if not sys.platform.startswith("linux"):
        return False
    xid = _hwnd(widget)
    conn = _qt_xcb_connection()
    xcb, _shape = _xcb_libs()
    if xid is None or conn is None or xcb is None:
        return False

    conn_p = ctypes.c_void_p(conn)

    class _AtomReply(ctypes.Structure):
        _fields_ = [
            ("response_type", ctypes.c_uint8),
            ("pad0", ctypes.c_uint8),
            ("sequence", ctypes.c_uint16),
            ("length", ctypes.c_uint32),
            ("atom", ctypes.c_uint32),
        ]

    class _PropReply(ctypes.Structure):
        _fields_ = [
            ("response_type", ctypes.c_uint8),
            ("format", ctypes.c_uint8),
            ("sequence", ctypes.c_uint16),
            ("length", ctypes.c_uint32),
            ("type", ctypes.c_uint32),
            ("bytes_after", ctypes.c_uint32),
            ("value_len", ctypes.c_uint32),
            ("pad1", ctypes.c_uint8 * 12),
        ]

    try:
        xcb.xcb_intern_atom.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint8,
            ctypes.c_uint16,
            ctypes.c_char_p,
        ]
        xcb.xcb_intern_atom.restype = ctypes.c_uint32
        xcb.xcb_intern_atom_reply.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        xcb.xcb_intern_atom_reply.restype = ctypes.POINTER(_AtomReply)

        def intern(name: str) -> int | None:
            raw = name.encode("ascii")
            cookie = xcb.xcb_intern_atom(conn_p, 0, len(raw), raw)
            reply = xcb.xcb_intern_atom_reply(conn_p, cookie, None)
            if not reply:
                return None
            atom = int(reply.contents.atom)
            try:
                ctypes.CDLL("libc.so.6").free(reply)
            except Exception:
                pass
            return atom or None

        state_atom = intern("_NET_WM_STATE")
        demands_atom = intern("_NET_WM_STATE_DEMANDS_ATTENTION")
        if state_atom is None or demands_atom is None:
            return False

        XCB_ATOM_ATOM = 4
        xcb.xcb_get_property.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint8,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
        ]
        xcb.xcb_get_property.restype = ctypes.c_uint32
        xcb.xcb_get_property_reply.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        xcb.xcb_get_property_reply.restype = ctypes.POINTER(_PropReply)
        xcb.xcb_get_property_value.argtypes = [ctypes.POINTER(_PropReply)]
        xcb.xcb_get_property_value.restype = ctypes.c_void_p

        cookie = xcb.xcb_get_property(
            conn_p,
            0,
            ctypes.c_uint32(xid),
            ctypes.c_uint32(state_atom),
            XCB_ATOM_ATOM,
            0,
            64,
        )
        reply = xcb.xcb_get_property_reply(conn_p, cookie, None)
        if not reply:
            return False
        try:
            length = int(reply.contents.value_len)
            if length <= 0 or int(reply.contents.format) != 32:
                return False
            value_ptr = xcb.xcb_get_property_value(reply)
            if not value_ptr:
                return False
            atoms = (ctypes.c_uint32 * length).from_address(int(value_ptr))
            target = ctypes.c_uint32(demands_atom).value
            return any(int(atoms[i]) == target for i in range(length))
        finally:
            try:
                ctypes.CDLL("libc.so.6").free(reply)
            except Exception:
                pass
    except Exception:
        return False


def _xcb_net_wm_state(
    widget: QtWidgets.QWidget, *, add: bool, atom_name: str
) -> None:
    """Add/remove a _NET_WM_STATE atom via Qt's xcb connection (not Xlib)."""
    xid = _hwnd(widget)
    conn = _qt_xcb_connection()
    xcb, _shape = _xcb_libs()
    if xid is None or conn is None or xcb is None:
        return

    conn_p = ctypes.c_void_p(conn)

    # xcb_intern_atom(conn, only_if_exists, name_len, name) -> cookie
    xcb.xcb_intern_atom.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint8,
        ctypes.c_uint16,
        ctypes.c_char_p,
    ]
    xcb.xcb_intern_atom.restype = ctypes.c_uint32  # cookie (we use reply API)

    class _AtomReply(ctypes.Structure):
        _fields_ = [
            ("response_type", ctypes.c_uint8),
            ("pad0", ctypes.c_uint8),
            ("sequence", ctypes.c_uint16),
            ("length", ctypes.c_uint32),
            ("atom", ctypes.c_uint32),
        ]

    xcb.xcb_intern_atom_reply.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    xcb.xcb_intern_atom_reply.restype = ctypes.POINTER(_AtomReply)

    def intern(name: str) -> int | None:
        raw = name.encode("ascii")
        cookie = xcb.xcb_intern_atom(conn_p, 0, len(raw), raw)
        reply = xcb.xcb_intern_atom_reply(conn_p, cookie, None)
        if not reply:
            return None
        atom = int(reply.contents.atom)
        # xcb_intern_atom_reply allocates; free with libc free.
        try:
            ctypes.CDLL("libc.so.6").free(reply)
        except Exception:
            pass
        return atom or None

    try:
        state_atom = intern("_NET_WM_STATE")
        prop_atom = intern(atom_name)
        if state_atom is None or prop_atom is None:
            return

        # xcb_client_message_event_t
        class _ClientMessage(ctypes.Structure):
            _fields_ = [
                ("response_type", ctypes.c_uint8),
                ("format", ctypes.c_uint8),
                ("sequence", ctypes.c_uint16),
                ("window", ctypes.c_uint32),
                ("type", ctypes.c_uint32),
                ("data32", ctypes.c_uint32 * 5),
            ]

        XCB_CLIENT_MESSAGE = 33
        XCB_EVENT_MASK_SUBSTRUCTURE_REDIRECT = 1 << 20
        XCB_EVENT_MASK_SUBSTRUCTURE_NOTIFY = 1 << 19
        event_mask = (
            XCB_EVENT_MASK_SUBSTRUCTURE_REDIRECT | XCB_EVENT_MASK_SUBSTRUCTURE_NOTIFY
        )

        msg = _ClientMessage()
        msg.response_type = XCB_CLIENT_MESSAGE
        msg.format = 32
        msg.sequence = 0
        msg.window = ctypes.c_uint32(xid)
        msg.type = ctypes.c_uint32(state_atom)
        msg.data32[0] = 1 if add else 0
        msg.data32[1] = ctypes.c_uint32(prop_atom)
        msg.data32[2] = 0
        msg.data32[3] = 1  # source: application
        msg.data32[4] = 0

        # Root window: xcb_setup_roots_iterator is heavy; Qt's screen root via
        # xcb_get_setup is awkward in ctypes. Use xcb_change_property path on
        # the window itself as a fallback is wrong for STATE; send to root.
        # Query tree for parent=root.
        class _TreeReply(ctypes.Structure):
            _fields_ = [
                ("response_type", ctypes.c_uint8),
                ("pad0", ctypes.c_uint8),
                ("sequence", ctypes.c_uint16),
                ("length", ctypes.c_uint32),
                ("root", ctypes.c_uint32),
                ("parent", ctypes.c_uint32),
                ("children_len", ctypes.c_uint16),
                ("pad1", ctypes.c_uint16),
            ]

        xcb.xcb_query_tree.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        xcb.xcb_query_tree.restype = ctypes.c_uint32
        xcb.xcb_query_tree_reply.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        xcb.xcb_query_tree_reply.restype = ctypes.POINTER(_TreeReply)
        tree_cookie = xcb.xcb_query_tree(conn_p, ctypes.c_uint32(xid))
        tree = xcb.xcb_query_tree_reply(conn_p, tree_cookie, None)
        if not tree:
            return
        root = int(tree.contents.root)
        try:
            ctypes.CDLL("libc.so.6").free(tree)
        except Exception:
            pass

        xcb.xcb_send_event.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint8,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_char_p,
        ]
        xcb.xcb_send_event.restype = ctypes.c_uint32
        xcb.xcb_flush.argtypes = [ctypes.c_void_p]
        xcb.xcb_flush.restype = ctypes.c_int

        payload = ctypes.string_at(ctypes.byref(msg), ctypes.sizeof(msg))
        xcb.xcb_send_event(
            conn_p,
            0,
            ctypes.c_uint32(root),
            ctypes.c_uint32(event_mask),
            payload,
        )
        xcb.xcb_flush(conn_p)
    except Exception:
        return


def _xcb_force_normal_window_type(widget: QtWidgets.QWidget) -> None:
    """Drop KDE OVERRIDE from _NET_WM_WINDOW_TYPE; keep NORMAL only.

    Frameless Qt windows often advertise::

        _KDE_NET_WM_WINDOW_TYPE_OVERRIDE, _NET_WM_WINDOW_TYPE_NORMAL

    Keep a plain NORMAL type so Plasma treats the overlay like a regular
    top-level window (still frameless via Motif/Qt hints).
    """
    xid = _hwnd(widget)
    conn = _qt_xcb_connection()
    xcb, _shape = _xcb_libs()
    if xid is None or conn is None or xcb is None:
        return

    conn_p = ctypes.c_void_p(conn)

    class _AtomReply(ctypes.Structure):
        _fields_ = [
            ("response_type", ctypes.c_uint8),
            ("pad0", ctypes.c_uint8),
            ("sequence", ctypes.c_uint16),
            ("length", ctypes.c_uint32),
            ("atom", ctypes.c_uint32),
        ]

    xcb.xcb_intern_atom.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint8,
        ctypes.c_uint16,
        ctypes.c_char_p,
    ]
    xcb.xcb_intern_atom.restype = ctypes.c_uint32
    xcb.xcb_intern_atom_reply.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    xcb.xcb_intern_atom_reply.restype = ctypes.POINTER(_AtomReply)

    def intern(name: str) -> int | None:
        raw = name.encode("ascii")
        cookie = xcb.xcb_intern_atom(conn_p, 0, len(raw), raw)
        reply = xcb.xcb_intern_atom_reply(conn_p, cookie, None)
        if not reply:
            return None
        atom = int(reply.contents.atom)
        try:
            ctypes.CDLL("libc.so.6").free(reply)
        except Exception:
            pass
        return atom or None

    try:
        type_atom = intern("_NET_WM_WINDOW_TYPE")
        normal_atom = intern("_NET_WM_WINDOW_TYPE_NORMAL")
        if type_atom is None or normal_atom is None:
            return
        XCB_PROP_MODE_REPLACE = 0
        XCB_ATOM_ATOM = 4
        xcb.xcb_change_property.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint8,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint8,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        xcb.xcb_change_property.restype = ctypes.c_uint32
        xcb.xcb_flush.argtypes = [ctypes.c_void_p]
        xcb.xcb_flush.restype = ctypes.c_int
        value = ctypes.c_uint32(normal_atom)
        xcb.xcb_change_property(
            conn_p,
            XCB_PROP_MODE_REPLACE,
            ctypes.c_uint32(xid),
            ctypes.c_uint32(type_atom),
            XCB_ATOM_ATOM,
            32,
            1,
            ctypes.byref(value),
        )
        xcb.xcb_flush(conn_p)
    except Exception:
        return


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
        geometry = widget.saveGeometry() if was_visible else None
        widget.setWindowFlag(transparent, False)
        handle = widget.windowHandle()
        if handle is not None:
            handle.setFlag(transparent, False)
        if was_visible:
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            widget.show()
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            if geometry is not None:
                widget.restoreGeometry(geometry)

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
