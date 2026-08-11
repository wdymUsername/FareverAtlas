"""OS-level hotkeys that work even when another app (the game) has focus."""

from __future__ import annotations

import ctypes
import sys
from typing import Callable

from PySide6 import QtCore, QtGui


def _flag_int(value: object) -> int:
    """Convert Qt enums/flags to int (PySide6 + Python 3.14 safe)."""
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    raw = getattr(value, "value", None)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return int(raw)
    try:
        return int(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"cannot convert {type(value).__name__} to int") from exc


# int() / Flag mixing is broken on Python 3.14; keep mask constants as ints.
_MOD_SHIFT = _flag_int(QtCore.Qt.KeyboardModifier.ShiftModifier)
_MOD_CTRL = _flag_int(QtCore.Qt.KeyboardModifier.ControlModifier)
_MOD_ALT = _flag_int(QtCore.Qt.KeyboardModifier.AltModifier)
_MOD_META = _flag_int(QtCore.Qt.KeyboardModifier.MetaModifier)


def _combo_from_sequence(sequence: QtGui.QKeySequence) -> tuple[int, int] | None:
    """Return (qt_key, qt_modifiers) for the first chord, or None if empty."""
    if sequence.isEmpty():
        return None
    try:
        combo = sequence[0]
    except (IndexError, TypeError):
        key = sequence[0] if sequence.count() else 0
        if not key:
            return None
        # Older Qt: sequence[0] may already be an int key+mods encoding.
        if isinstance(key, int):
            return int(key) & 0x01FFFFFF, int(key) & ~0x01FFFFFF
        return None
    if hasattr(combo, "key"):
        # KeyboardModifier is a Flag; int(flag) raises TypeError on Py 3.14.
        return _flag_int(combo.key()), _flag_int(combo.keyboardModifiers())
    # Fallback: parse toString
    text = sequence.toString(QtGui.QKeySequence.SequenceFormat.PortableText)
    parsed = QtGui.QKeySequence(text)
    if parsed.isEmpty():
        return None
    combo = parsed[0]
    return _flag_int(combo.key()), _flag_int(combo.keyboardModifiers())


class GlobalHotkey(QtCore.QObject):
    """Register one global key sequence; emit ``activated`` when pressed."""

    activated = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._sequence = QtGui.QKeySequence()
        self._impl: _HotkeyBackend | None = None

    def key_sequence(self) -> QtGui.QKeySequence:
        return QtGui.QKeySequence(self._sequence)

    def set_key_sequence(self, sequence: QtGui.QKeySequence | str) -> bool:
        """Bind ``sequence`` globally. Empty sequence clears the binding."""
        self.clear()
        seq = QtGui.QKeySequence(sequence)
        self._sequence = seq
        if seq.isEmpty():
            return True
        combo = _combo_from_sequence(seq)
        if combo is None:
            return False
        key, mods = combo
        if sys.platform == "win32":
            self._impl = _WindowsHotkey(self, key, mods, self.activated.emit)
        elif sys.platform.startswith("linux"):
            self._impl = _X11Hotkey(self, key, mods, self.activated.emit)
        else:
            return False
        return self._impl.start()

    def clear(self) -> None:
        if self._impl is not None:
            self._impl.stop()
            self._impl = None


class _HotkeyBackend:
    def start(self) -> bool:  # noqa: D401
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class _WindowsHotkey(_HotkeyBackend):
    _HOTKEY_ID = 0xFA01

    def __init__(
        self,
        owner: GlobalHotkey,
        qt_key: int,
        qt_mods: int,
        callback: Callable[[], None],
    ) -> None:
        self._owner = owner
        self._qt_key = qt_key
        self._qt_mods = qt_mods
        self._callback = callback
        self._filter: _WindowsHotkeyFilter | None = None

    def start(self) -> bool:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        vk = _qt_key_to_vk(self._qt_key)
        if vk is None:
            return False
        mods = 0
        if self._qt_mods & _MOD_SHIFT:
            mods |= 0x0004  # MOD_SHIFT
        if self._qt_mods & _MOD_CTRL:
            mods |= 0x0002  # MOD_CONTROL
        if self._qt_mods & _MOD_ALT:
            mods |= 0x0001  # MOD_ALT
        if self._qt_mods & _MOD_META:
            mods |= 0x0008  # MOD_WIN
        mods |= 0x4000  # MOD_NOREPEAT
        if not user32.RegisterHotKey(None, self._HOTKEY_ID, mods, vk):
            return False
        app = QtCore.QCoreApplication.instance()
        if app is None:
            user32.UnregisterHotKey(None, self._HOTKEY_ID)
            return False
        self._filter = _WindowsHotkeyFilter(self._HOTKEY_ID, self._callback)
        app.installNativeEventFilter(self._filter)
        return True

    def stop(self) -> None:
        app = QtCore.QCoreApplication.instance()
        if self._filter is not None and app is not None:
            app.removeNativeEventFilter(self._filter)
        self._filter = None
        try:
            ctypes.windll.user32.UnregisterHotKey(None, self._HOTKEY_ID)  # type: ignore[attr-defined]
        except Exception:
            pass


class _WindowsHotkeyFilter(QtCore.QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self._hotkey_id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        try:
            et = bytes(eventType)
        except TypeError:
            et = bytes(str(eventType), "utf-8")
        if not et.startswith(b"windows_generic_MSG"):
            return False, 0
        from ctypes import wintypes

        try:
            msg = wintypes.MSG.from_address(int(message))
        except (TypeError, ValueError, OverflowError):
            return False, 0
        wm_hotkey = 0x0312
        if int(msg.message) == wm_hotkey and int(msg.wParam) == self._hotkey_id:
            self._callback()
            return True, 1
        return False, 0


def _qt_key_to_vk(qt_key: int) -> int | None:
    mapping = {
        int(QtCore.Qt.Key.Key_Insert): 0x2D,
        int(QtCore.Qt.Key.Key_Delete): 0x2E,
        int(QtCore.Qt.Key.Key_Home): 0x24,
        int(QtCore.Qt.Key.Key_End): 0x23,
        int(QtCore.Qt.Key.Key_PageUp): 0x21,
        int(QtCore.Qt.Key.Key_PageDown): 0x22,
        int(QtCore.Qt.Key.Key_Escape): 0x1B,
        int(QtCore.Qt.Key.Key_Space): 0x20,
        int(QtCore.Qt.Key.Key_Return): 0x0D,
        int(QtCore.Qt.Key.Key_Enter): 0x0D,
        int(QtCore.Qt.Key.Key_Tab): 0x09,
        int(QtCore.Qt.Key.Key_Backspace): 0x08,
        int(QtCore.Qt.Key.Key_F1): 0x70,
        int(QtCore.Qt.Key.Key_F2): 0x71,
        int(QtCore.Qt.Key.Key_F3): 0x72,
        int(QtCore.Qt.Key.Key_F4): 0x73,
        int(QtCore.Qt.Key.Key_F5): 0x74,
        int(QtCore.Qt.Key.Key_F6): 0x75,
        int(QtCore.Qt.Key.Key_F7): 0x76,
        int(QtCore.Qt.Key.Key_F8): 0x77,
        int(QtCore.Qt.Key.Key_F9): 0x78,
        int(QtCore.Qt.Key.Key_F10): 0x79,
        int(QtCore.Qt.Key.Key_F11): 0x7A,
        int(QtCore.Qt.Key.Key_F12): 0x7B,
    }
    if qt_key in mapping:
        return mapping[qt_key]
    if int(QtCore.Qt.Key.Key_A) <= qt_key <= int(QtCore.Qt.Key.Key_Z):
        return ord("A") + (qt_key - int(QtCore.Qt.Key.Key_A))
    if int(QtCore.Qt.Key.Key_0) <= qt_key <= int(QtCore.Qt.Key.Key_9):
        return ord("0") + (qt_key - int(QtCore.Qt.Key.Key_0))
    return None


class _X11Hotkey(_HotkeyBackend):
    def __init__(
        self,
        owner: GlobalHotkey,
        qt_key: int,
        qt_mods: int,
        callback: Callable[[], None],
    ) -> None:
        self._owner = owner
        self._qt_key = qt_key
        self._qt_mods = qt_mods
        self._callback = callback
        self._dpy = None
        self._root = 0
        self._keycode = 0
        self._x_mods = 0
        self._notifier: QtCore.QSocketNotifier | None = None
        self._xlib = None

    def start(self) -> bool:
        try:
            xlib = ctypes.CDLL("libX11.so.6")
        except OSError:
            return False
        self._xlib = xlib
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.restype = ctypes.c_ulong
        xlib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        xlib.XKeysymToKeycode.restype = ctypes.c_uint8
        xlib.XGrabKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        xlib.XGrabKey.restype = ctypes.c_int
        xlib.XUngrabKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_ulong,
        ]
        xlib.XConnectionNumber.argtypes = [ctypes.c_void_p]
        xlib.XConnectionNumber.restype = ctypes.c_int
        xlib.XPending.argtypes = [ctypes.c_void_p]
        xlib.XPending.restype = ctypes.c_int
        xlib.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        xlib.XNextEvent.restype = ctypes.c_int
        xlib.XFlush.argtypes = [ctypes.c_void_p]

        keysym = _qt_key_to_xkeysym(self._qt_key)
        if keysym is None:
            return False
        dpy = xlib.XOpenDisplay(None)
        if not dpy:
            return False
        root = int(xlib.XDefaultRootWindow(dpy))
        keycode = int(xlib.XKeysymToKeycode(dpy, keysym))
        if keycode == 0:
            xlib.XCloseDisplay(dpy)
            return False
        x_mods = 0
        if self._qt_mods & _MOD_SHIFT:
            x_mods |= 1 << 0  # ShiftMask
        if self._qt_mods & _MOD_CTRL:
            x_mods |= 1 << 2  # ControlMask
        if self._qt_mods & _MOD_ALT:
            x_mods |= 1 << 3  # Mod1Mask
        if self._qt_mods & _MOD_META:
            x_mods |= 1 << 6  # Mod4Mask
        GrabModeAsync = 1
        # Grab with and without NumLock/CapsLock (Mod2/Lock) so Insert still fires.
        lock_masks = (0, 1 << 1, 1 << 4, (1 << 1) | (1 << 4))
        for extra in lock_masks:
            xlib.XGrabKey(
                dpy,
                keycode,
                x_mods | extra,
                root,
                1,
                GrabModeAsync,
                GrabModeAsync,
            )
        xlib.XFlush(dpy)
        fd = int(xlib.XConnectionNumber(dpy))
        self._dpy = dpy
        self._root = root
        self._keycode = keycode
        self._x_mods = x_mods
        self._notifier = QtCore.QSocketNotifier(
            fd, QtCore.QSocketNotifier.Type.Read, self._owner
        )
        self._notifier.activated.connect(self._on_x_readable)
        return True

    def stop(self) -> None:
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier.deleteLater()
            self._notifier = None
        xlib = self._xlib
        dpy = self._dpy
        if xlib is not None and dpy:
            lock_masks = (0, 1 << 1, 1 << 4, (1 << 1) | (1 << 4))
            for extra in lock_masks:
                try:
                    xlib.XUngrabKey(
                        dpy, self._keycode, self._x_mods | extra, self._root
                    )
                except Exception:
                    pass
            try:
                xlib.XCloseDisplay(dpy)
            except Exception:
                pass
        self._dpy = None

    def _on_x_readable(self, *_args: object) -> None:
        xlib = self._xlib
        dpy = self._dpy
        if xlib is None or not dpy:
            return

        class _XEvent(ctypes.Structure):
            _fields_ = [("type", ctypes.c_int), ("pad", ctypes.c_long * 24)]

        class _XKeyEvent(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_int),
                ("serial", ctypes.c_ulong),
                ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong),
                ("root", ctypes.c_ulong),
                ("subwindow", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("x", ctypes.c_int),
                ("y", ctypes.c_int),
                ("x_root", ctypes.c_int),
                ("y_root", ctypes.c_int),
                ("state", ctypes.c_uint),
                ("keycode", ctypes.c_uint),
                ("same_screen", ctypes.c_int),
            ]

        KeyPress = 2
        event = _XEvent()
        while xlib.XPending(dpy):
            xlib.XNextEvent(dpy, ctypes.byref(event))
            if int(event.type) != KeyPress:
                continue
            key = ctypes.cast(ctypes.byref(event), ctypes.POINTER(_XKeyEvent)).contents
            if int(key.keycode) != self._keycode:
                continue
            # Ignore lock modifiers when matching.
            relevant = int(key.state) & ~( (1 << 1) | (1 << 4) )
            if relevant != self._x_mods:
                continue
            self._callback()


def _qt_key_to_xkeysym(qt_key: int) -> int | None:
    # X11 keysyms for common keys (from X11/keysymdef.h).
    mapping = {
        int(QtCore.Qt.Key.Key_Insert): 0xFF63,
        int(QtCore.Qt.Key.Key_Delete): 0xFFFF,
        int(QtCore.Qt.Key.Key_Home): 0xFF50,
        int(QtCore.Qt.Key.Key_End): 0xFF57,
        int(QtCore.Qt.Key.Key_PageUp): 0xFF55,
        int(QtCore.Qt.Key.Key_PageDown): 0xFF56,
        int(QtCore.Qt.Key.Key_Escape): 0xFF1B,
        int(QtCore.Qt.Key.Key_Space): 0x0020,
        int(QtCore.Qt.Key.Key_Return): 0xFF0D,
        int(QtCore.Qt.Key.Key_Enter): 0xFF0D,
        int(QtCore.Qt.Key.Key_Tab): 0xFF09,
        int(QtCore.Qt.Key.Key_Backspace): 0xFF08,
        int(QtCore.Qt.Key.Key_F1): 0xFFBE,
        int(QtCore.Qt.Key.Key_F2): 0xFFBF,
        int(QtCore.Qt.Key.Key_F3): 0xFFC0,
        int(QtCore.Qt.Key.Key_F4): 0xFFC1,
        int(QtCore.Qt.Key.Key_F5): 0xFFC2,
        int(QtCore.Qt.Key.Key_F6): 0xFFC3,
        int(QtCore.Qt.Key.Key_F7): 0xFFC4,
        int(QtCore.Qt.Key.Key_F8): 0xFFC5,
        int(QtCore.Qt.Key.Key_F9): 0xFFC6,
        int(QtCore.Qt.Key.Key_F10): 0xFFC7,
        int(QtCore.Qt.Key.Key_F11): 0xFFC8,
        int(QtCore.Qt.Key.Key_F12): 0xFFC9,
    }
    if qt_key in mapping:
        return mapping[qt_key]
    if int(QtCore.Qt.Key.Key_A) <= qt_key <= int(QtCore.Qt.Key.Key_Z):
        return ord("a") + (qt_key - int(QtCore.Qt.Key.Key_A))
    if int(QtCore.Qt.Key.Key_0) <= qt_key <= int(QtCore.Qt.Key.Key_9):
        return ord("0") + (qt_key - int(QtCore.Qt.Key.Key_0))
    return None
