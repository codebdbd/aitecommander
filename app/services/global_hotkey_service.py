"""System-wide global hotkey registration and native event filtering (Windows)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import os
import sys
from typing import Any, Callable

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_SPACE = 0x20
VK_OEM_3 = 0xC0  # '`~' key on US/standard layouts (Ё on RU layout)

_SPECIAL_VK_MAP: dict[str, int] = {
    "`": VK_OEM_3,
    "~": VK_OEM_3,
    "quoteleft": VK_OEM_3,
    "asciitilde": VK_OEM_3,
    "ё": VK_OEM_3,
    "space": VK_SPACE,
    "tab": 0x09,
    "return": 0x0D,
    "enter": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "backslash": 0xDC,
    "\\": 0xDC,
    "/": 0xBF,
    "slash": 0xBF,
}


def parse_win32_hotkey(hotkey_str: str) -> tuple[int, int] | None:
    """Parse a hotkey string like 'Alt+`' or 'Alt+~' into (modifiers, vk_code).

    Returns None if the string cannot be mapped to a valid Win32 combination.
    """
    if not hotkey_str or not isinstance(hotkey_str, str):
        return None

    parts = [p.strip() for p in hotkey_str.split("+") if p.strip()]
    if not parts:
        return None

    modifiers = 0
    key_token = ""

    for part in parts:
        lower = part.lower()
        if lower == "alt":
            modifiers |= MOD_ALT
        elif lower in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif lower == "shift":
            modifiers |= MOD_SHIFT
        elif lower in ("win", "meta", "super"):
            modifiers |= MOD_WIN
        else:
            key_token = lower

    if not key_token or modifiers == 0:
        return None

    vk_code: int | None = None
    if key_token in _SPECIAL_VK_MAP:
        vk_code = _SPECIAL_VK_MAP[key_token]
    elif len(key_token) == 1 and "a" <= key_token <= "z":
        vk_code = ord(key_token.upper())
    elif len(key_token) == 1 and "0" <= key_token <= "9":
        vk_code = ord(key_token)
    elif key_token.startswith("f") and key_token[1:].isdigit():
        fn_num = int(key_token[1:])
        if 1 <= fn_num <= 24:
            vk_code = 0x70 + (fn_num - 1)

    if vk_code is None:
        return None

    return (modifiers | MOD_NOREPEAT, vk_code)


class _Win32HotkeyEventFilter(QAbstractNativeEventFilter):
    """Qt native event filter that intercepts WM_HOTKEY messages."""

    def __init__(self, hotkey_id: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self._hotkey_id = int(hotkey_id)
        self._callback = callback

    def nativeEventFilter(
        self, event_type: Any, message: Any
    ) -> tuple[bool, int]:
        try:
            evt_bytes = bytes(event_type) if event_type is not None else b""
            if evt_bytes in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                addr = int(message)
                if addr:
                    msg = ctypes.wintypes.MSG.from_address(addr)
                    if (
                        msg.message == WM_HOTKEY
                        and int(msg.wParam) == self._hotkey_id
                    ):
                        QTimer.singleShot(0, self._callback)
                        return True, 0
        except Exception:
            logger.debug(
                "Error inside _Win32HotkeyEventFilter.nativeEventFilter",
                exc_info=True,
            )
        return False, 0


class GlobalHotkeyService(QObject):
    """Manages registration and cleanup of a system-wide global hotkey."""

    activated = pyqtSignal()

    _HOTKEY_ID = 0xA17E
    HOTKEY_ID = _HOTKEY_ID

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        user32: Any = None,
        force_native: bool = False,
    ) -> None:
        super().__init__(parent)
        self._user32 = user32
        self._force_native = bool(force_native)
        self._registered = False
        self._filter_installed = False
        self._native_filter: _Win32HotkeyEventFilter | None = None
        self._hotkey_str = "Alt+`"

    @property
    def is_registered(self) -> bool:
        return self._registered

    @property
    def hotkey_string(self) -> str:
        return self._hotkey_str

    def _can_use_native_hotkey(self) -> bool:
        if self._force_native:
            return True
        if sys.platform != "win32":
            return False
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return False
        if os.environ.get("QT_QPA_PLATFORM", "").lower() in ("offscreen", "minimal"):
            return False
        return True

    def _get_user32(self) -> Any:
        if self._user32 is not None:
            return self._user32
        if sys.platform == "win32":
            return ctypes.windll.user32
        return None

    def register(self, hotkey_str: str = "Alt+`", *, force_native: bool = False) -> bool:
        """Register the system-wide hotkey on Windows."""
        if force_native:
            self._force_native = True
        self.unregister()
        self._hotkey_str = (hotkey_str or "Alt+`").strip() or "Alt+`"

        parsed = parse_win32_hotkey(self._hotkey_str)
        if parsed is None:
            logger.warning(
                "GlobalHotkeyService: invalid hotkey specification '%s'",
                self._hotkey_str,
            )
            return False

        if not self._can_use_native_hotkey():
            logger.debug(
                "GlobalHotkeyService: skipping OS RegisterHotKey in non-interactive/test environment"
            )
            return False

        user32 = self._get_user32()
        if user32 is None:
            return False

        modifiers, vk_code = parsed
        try:
            ok = bool(
                user32.RegisterHotKey(None, self._HOTKEY_ID, modifiers, vk_code)
            )
            if not ok:
                logger.warning(
                    "GlobalHotkeyService: RegisterHotKey failed for '%s' (already in use by another process)",
                    self._hotkey_str,
                )
                return False

            self._registered = True
            app = QApplication.instance()
            if app is not None:
                self._native_filter = _Win32HotkeyEventFilter(
                    self._HOTKEY_ID, self._emit_activated
                )
                app.installNativeEventFilter(self._native_filter)
                self._filter_installed = True
            logger.info(
                "GlobalHotkeyService: registered global hotkey '%s' (vk=0x%02X, mod=0x%04X)",
                self._hotkey_str,
                vk_code,
                modifiers,
            )
            return True
        except Exception as exc:
            logger.warning(
                "GlobalHotkeyService: exception registering hotkey '%s': %s",
                self._hotkey_str,
                exc,
            )
            return False

    def unregister(self) -> None:
        """Unregister the system-wide hotkey and remove the native event filter."""
        if self._filter_installed and self._native_filter is not None:
            try:
                app = QApplication.instance()
                if app is not None:
                    app.removeNativeEventFilter(self._native_filter)
            except Exception:
                logger.debug(
                    "GlobalHotkeyService: failed to remove native event filter",
                    exc_info=True,
                )
            finally:
                self._filter_installed = False
                self._native_filter = None

        if self._registered:
            try:
                user32 = self._get_user32()
                if user32 is not None:
                    user32.UnregisterHotKey(None, self._HOTKEY_ID)
            except Exception:
                logger.debug(
                    "GlobalHotkeyService: UnregisterHotKey failed",
                    exc_info=True,
                )
            finally:
                self._registered = False

    def _emit_activated(self) -> None:
        self.activated.emit()

    def register_hotkey(self, hotkey_str: str = "Alt+`", *, force_native: bool = False) -> bool:
        """Alias for register()."""
        return self.register(hotkey_str, force_native=force_native)

    def cleanup(self) -> None:
        """Alias for unregister()."""
        self.unregister()
