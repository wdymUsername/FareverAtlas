"""Locate the Farever game client window for overlay follow / focus."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

from PySide6 import QtCore

from .config import APP_ID

_STEAM_CLASS = f"steam_app_{APP_ID}"


@dataclass(frozen=True)
class GameWindowInfo:
    """Native game window identity + frame geometry in global pixels."""

    handle: int
    rect: QtCore.QRect
    is_active: bool


def find_farever_game_window() -> GameWindowInfo | None:
    """Return the Farever game window if it is mapped, else None."""
    if sys.platform == "win32":
        return _find_windows()
    if sys.platform.startswith("linux"):
        return _find_linux_xlib()
    return None


def _is_farever_title(title: str) -> bool:
    text = (title or "").strip()
    if not text:
        return False
    lower = text.lower()
    if lower.startswith("farever atlas"):
        return False
    return lower == "farever"


def _is_farever_class(class_name: str) -> bool:
    name = (class_name or "").strip().lower()
    if not name:
        return False
    if "farever atlas" in name:
        return False
    return name == _STEAM_CLASS.lower() or _STEAM_CLASS.lower() in name


def _find_windows() -> GameWindowInfo | None:
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]

    EnumWindowsProc = ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )

    class _Rect(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    GetWindowTextW = user32.GetWindowTextW
    GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    GetWindowTextW.restype = ctypes.c_int
    GetClassNameW = user32.GetClassNameW
    GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    GetClassNameW.restype = ctypes.c_int
    IsWindowVisible = user32.IsWindowVisible
    IsWindowVisible.argtypes = [ctypes.c_void_p]
    IsWindowVisible.restype = ctypes.c_bool
    GetWindowRect = user32.GetWindowRect
    GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]
    GetWindowRect.restype = ctypes.c_bool
    GetForegroundWindow = user32.GetForegroundWindow
    GetForegroundWindow.restype = ctypes.c_void_p

    foreground = int(GetForegroundWindow() or 0)
    matches: list[GameWindowInfo] = []

    def _callback(hwnd: int, _lparam: int) -> bool:
        if not IsWindowVisible(ctypes.c_void_p(hwnd)):
            return True
        title_buf = ctypes.create_unicode_buffer(512)
        class_buf = ctypes.create_unicode_buffer(256)
        GetWindowTextW(ctypes.c_void_p(hwnd), title_buf, 512)
        GetClassNameW(ctypes.c_void_p(hwnd), class_buf, 256)
        title = title_buf.value
        class_name = class_buf.value
        if not (_is_farever_class(class_name) or _is_farever_title(title)):
            return True
        rect = _Rect()
        if not GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
            return True
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width < 64 or height < 64:
            return True
        handle = int(hwnd)
        matches.append(
            GameWindowInfo(
                handle=handle,
                rect=QtCore.QRect(int(rect.left), int(rect.top), width, height),
                is_active=handle == foreground,
            )
        )
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    if not matches:
        return None
    active = [item for item in matches if item.is_active]
    if active:
        return max(active, key=lambda item: item.rect.width() * item.rect.height())
    return max(matches, key=lambda item: item.rect.width() * item.rect.height())


def _find_linux_xlib() -> GameWindowInfo | None:
    """Read-only Xlib probe on a private Display* (not Qt's connection)."""
    try:
        xlib = ctypes.CDLL("libX11.so.6")
    except OSError:
        return None

    class _XWindowAttributes(ctypes.Structure):
        _fields_ = [
            ("x", ctypes.c_int),
            ("y", ctypes.c_int),
            ("width", ctypes.c_int),
            ("height", ctypes.c_int),
            ("border_width", ctypes.c_int),
            ("depth", ctypes.c_int),
            ("visual", ctypes.c_void_p),
            ("root", ctypes.c_ulong),
            ("c_class", ctypes.c_int),
            ("bit_gravity", ctypes.c_int),
            ("win_gravity", ctypes.c_int),
            ("backing_store", ctypes.c_int),
            ("backing_planes", ctypes.c_ulong),
            ("backing_pixel", ctypes.c_ulong),
            ("save_under", ctypes.c_int),
            ("colormap", ctypes.c_ulong),
            ("map_installed", ctypes.c_int),
            ("map_state", ctypes.c_int),
            ("all_event_masks", ctypes.c_long),
            ("your_event_mask", ctypes.c_long),
            ("do_not_propagate_mask", ctypes.c_long),
            ("override_redirect", ctypes.c_int),
            ("screen", ctypes.c_void_p),
        ]

    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xlib.XCloseDisplay.restype = ctypes.c_int
    xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    xlib.XInternAtom.restype = ctypes.c_ulong
    xlib.XGetWindowProperty.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_long,
        ctypes.c_long,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    xlib.XGetWindowProperty.restype = ctypes.c_int
    xlib.XFree.argtypes = [ctypes.c_void_p]
    xlib.XFree.restype = ctypes.c_int
    xlib.XGetWindowAttributes.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(_XWindowAttributes),
    ]
    xlib.XGetWindowAttributes.restype = ctypes.c_int
    xlib.XTranslateCoordinates.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
    ]
    xlib.XTranslateCoordinates.restype = ctypes.c_int

    dpy = xlib.XOpenDisplay(None)
    if not dpy:
        return None

    result: GameWindowInfo | None = None
    try:
        root = int(xlib.XDefaultRootWindow(dpy))
        any_property = ctypes.c_ulong(0)
        client_atom = xlib.XInternAtom(dpy, b"_NET_CLIENT_LIST", 0)
        active_atom = xlib.XInternAtom(dpy, b"_NET_ACTIVE_WINDOW", 0)
        wm_class_atom = xlib.XInternAtom(dpy, b"WM_CLASS", 0)
        name_atom = xlib.XInternAtom(dpy, b"_NET_WM_NAME", 0)

        def window_ids(atom: int) -> list[int]:
            actual_type = ctypes.c_ulong()
            actual_format = ctypes.c_int()
            nitems = ctypes.c_ulong()
            bytes_after = ctypes.c_ulong()
            prop = ctypes.c_void_p()
            status = xlib.XGetWindowProperty(
                dpy,
                root,
                atom,
                0,
                4096,
                0,
                any_property,
                ctypes.byref(actual_type),
                ctypes.byref(actual_format),
                ctypes.byref(nitems),
                ctypes.byref(bytes_after),
                ctypes.byref(prop),
            )
            if status != 0 or not prop or int(nitems.value) <= 0:
                if prop:
                    xlib.XFree(prop)
                return []
            try:
                if int(actual_format.value) != 32:
                    return []
                count = int(nitems.value)
                values = (ctypes.c_ulong * count).from_address(int(prop.value))
                return [int(values[i]) for i in range(count)]
            finally:
                xlib.XFree(prop)

        def string_prop(window: int, atom: int) -> str:
            actual_type = ctypes.c_ulong()
            actual_format = ctypes.c_int()
            nitems = ctypes.c_ulong()
            bytes_after = ctypes.c_ulong()
            prop = ctypes.c_void_p()
            status = xlib.XGetWindowProperty(
                dpy,
                window,
                atom,
                0,
                1024,
                0,
                any_property,
                ctypes.byref(actual_type),
                ctypes.byref(actual_format),
                ctypes.byref(nitems),
                ctypes.byref(bytes_after),
                ctypes.byref(prop),
            )
            if status != 0 or not prop or int(nitems.value) <= 0:
                if prop:
                    xlib.XFree(prop)
                return ""
            try:
                fmt = int(actual_format.value)
                count = int(nitems.value)
                nbytes = count if fmt == 8 else count * max(1, fmt // 8)
                raw = ctypes.string_at(prop, nbytes)
                parts = [p.decode("utf-8", errors="replace") for p in raw.split(b"\x00") if p]
                return "\0".join(parts)
            finally:
                xlib.XFree(prop)

        def window_rect(xid: int) -> QtCore.QRect | None:
            attrs = _XWindowAttributes()
            if xlib.XGetWindowAttributes(dpy, xid, ctypes.byref(attrs)) == 0:
                return None
            if int(attrs.map_state) != 2:  # IsViewable
                return None
            width = int(attrs.width)
            height = int(attrs.height)
            if width < 64 or height < 64:
                return None
            dx = ctypes.c_int()
            dy = ctypes.c_int()
            child = ctypes.c_ulong()
            xlib.XTranslateCoordinates(
                dpy,
                xid,
                root,
                0,
                0,
                ctypes.byref(dx),
                ctypes.byref(dy),
                ctypes.byref(child),
            )
            return QtCore.QRect(int(dx.value), int(dy.value), width, height)

        clients = window_ids(client_atom)
        active_list = window_ids(active_atom)
        active = active_list[0] if active_list else 0
        matches: list[GameWindowInfo] = []
        for xid in clients:
            klass_raw = string_prop(xid, wm_class_atom)
            parts = klass_raw.split("\0") if klass_raw else []
            instance = parts[0] if parts else ""
            klass = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
            title = string_prop(xid, name_atom).split("\0")[0]
            if title.lower().startswith("farever atlas"):
                continue
            if not (
                _is_farever_class(klass)
                or _is_farever_class(instance)
                or _is_farever_title(title)
            ):
                continue
            rect = window_rect(xid)
            if rect is None:
                continue
            matches.append(
                GameWindowInfo(
                    handle=int(xid),
                    rect=rect,
                    is_active=int(xid) == int(active),
                )
            )
        if matches:
            pool = [item for item in matches if item.is_active] or matches
            result = max(
                pool, key=lambda item: item.rect.width() * item.rect.height()
            )
    except Exception:
        result = None
    finally:
        xlib.XCloseDisplay(dpy)
    return result
