# app/views/main_components/init_diagnostics.py
from __future__ import annotations

import logging
from typing import Callable

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class DiagnosticsInstaller:
    """Install diagnostic filters and observers for the UI.

    Usage:
        DiagnosticsInstaller(window, dump_top_levels_cb).install_all()
    """

    def __init__(
        self,
        window: QObject,
        dump_top_levels_cb: Callable[[str], None] | None = None,
    ) -> None:
        self._window = window
        self._dump_top_levels = dump_top_levels_cb

    def install_all(self) -> None:
        try:
            self._install_qt_message_filter()
        except Exception:
            logger.warning(
                "DiagnosticsInstaller: _install_qt_message_filter failed", exc_info=True
            )

        try:
            self._install_top_level_watcher()
        except Exception:
            logger.warning(
                "DiagnosticsInstaller: _install_top_level_watcher failed", exc_info=True
            )

        try:
            self._install_window_resize_logger()
        except Exception:
            logger.warning(
                "DiagnosticsInstaller: _install_window_resize_logger failed",
                exc_info=True,
            )

    # === Qt message handler ===
    def _install_qt_message_filter(self) -> None:
        try:
            from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
        except Exception as e:
            raise RuntimeError("qInstallMessageHandler import failed") from e

        def _qt_msg_handler(msg_type, context, message):  # noqa: ARG001 - Qt signature
            try:
                msg: str = str(message)
            except Exception:
                msg = ""
            if msg.startswith("QPainter::") or "Painter not active" in msg:
                try:
                    logger.debug("[QtMsgSuppressed] %s", msg)
                except Exception:
                    logger.debug(
                        "DiagnosticsInstaller: failed to log suppressed Qt message",
                        exc_info=True,
                    )
                return
            try:
                if msg_type in (QtMsgType.QtWarningMsg, QtMsgType.QtInfoMsg):
                    logger.warning("[Qt] %s", msg)
                elif msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                    logger.error("[Qt] %s", msg)
                else:
                    logger.info("[Qt] %s", msg)
            except Exception:
                logger.debug(
                    "DiagnosticsInstaller: failed to log Qt message", exc_info=True
                )

        try:
            qInstallMessageHandler(_qt_msg_handler)
        except Exception as e:
            raise RuntimeError("qInstallMessageHandler failed") from e

    # (Removed) Global QWidget.show/setVisible hooks are no longer used.

    def _get_resize_logger_limits(self):
        """Get resize and move logging limits from config."""
        try:
            from app.config_data import app_config as _cfg

            max_resizes = int(
                getattr(_cfg, "get", lambda *_: 5)("diag.resize_log.max_resizes", 5)
            )
            max_moves = int(
                getattr(_cfg, "get", lambda *_: 5)("diag.resize_log.max_moves", 5)
            )
            return max_resizes, max_moves
        except Exception:
            return 5, 5

    def _create_resize_logger_class(self):
        """Create ResizeLogger class."""

        class _ResizeLogger(QObject):
            def __init__(self, parent, max_resizes, max_moves):
                super().__init__(parent)
                self._resizes = 0
                self._moves = 0
                self._max_resizes = max_resizes
                self._max_moves = max_moves
                self._owner = parent

            def _should_uninstall(self):
                """Check if logger should be uninstalled."""
                return (
                    self._resizes >= self._max_resizes
                    and self._moves >= self._max_moves
                )

            def _uninstall_from_owner(self, obj):
                """Uninstall event filter and reset flags."""
                try:
                    obj.removeEventFilter(self)
                except Exception:
                    logger.debug(
                        "DiagnosticsInstaller: removeEventFilter failed in _ResizeLogger",
                        exc_info=True,
                    )
                try:
                    if (
                        hasattr(self._owner, "_diag_resize_logger")
                        and getattr(self._owner, "_diag_resize_logger", None) is self
                    ):
                        self._owner._diag_resize_logger = None  # type: ignore[attr-defined]
                        self._owner._diag_resize_logger_installed = False  # type: ignore[attr-defined]
                except Exception:
                    logger.debug(
                        "DiagnosticsInstaller: failed to reset _diag_resize_logger flags",
                        exc_info=True,
                    )

            def _handle_resize(self, obj):
                """Handle resize event."""
                if self._resizes >= self._max_resizes:
                    return
                self._resizes += 1
                try:
                    sz = getattr(obj, "size", lambda: None)()
                    size_s = f"{sz.width()}x{sz.height()}" if sz is not None else "?"
                except Exception:
                    size_s = "?"
                logger.info("DiagTopLevels: Resize #%s -> %s", self._resizes, size_s)

            def _handle_move(self, obj):
                """Handle move event."""
                if self._moves >= self._max_moves:
                    return
                self._moves += 1
                try:
                    pos = getattr(obj, "pos", lambda: None)()
                    pos_s = f"({pos.x()},{pos.y()})" if pos is not None else "?"
                except Exception:
                    pos_s = "?"
                logger.info("DiagTopLevels: Move #%s -> %s", self._moves, pos_s)

            def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
                """Filter and log resize/move events."""
                try:
                    et = event.type()
                    if et == QEvent.Type.Resize:
                        self._handle_resize(obj)
                    elif et == QEvent.Type.Move:
                        self._handle_move(obj)

                    if self._should_uninstall():
                        self._uninstall_from_owner(obj)
                except Exception:
                    logger.debug(
                        "DiagnosticsInstaller: _ResizeLogger.eventFilter failed",
                        exc_info=True,
                    )
                return QObject.eventFilter(self, obj, event)

        return _ResizeLogger

    def _install_window_resize_logger(self) -> None:
        win = self._window
        if not isinstance(win, QObject):
            raise RuntimeError("window is not QObject")
        if getattr(win, "_diag_resize_logger_installed", False):
            return

        max_resizes, max_moves = self._get_resize_logger_limits()
        _ResizeLogger = self._create_resize_logger_class()
        rl = _ResizeLogger(win, max_resizes, max_moves)
        win.installEventFilter(rl)
        win._diag_resize_logger = rl  # type: ignore[attr-defined]
        win._diag_resize_logger_installed = True  # type: ignore[attr-defined]

    def _install_top_level_watcher(self) -> None:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("No QApplication instance")
        if getattr(app, "_diag_top_levels_installed", False):
            return

        # Capture the dump callback inside the closure so the watcher can access it
        # without relying on a missing attribute on the inner class instance.
        dump_cb = self._dump_top_levels

        class _TopLevelWatcher(QObject):
            def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
                try:
                    et = event.type()
                    if et in (
                        QEvent.Type.Show,
                        QEvent.Type.ShowToParent,
                        QEvent.Type.WindowActivate,
                    ):
                        try:
                            is_window = bool(getattr(obj, "isWindow", lambda: False)())
                        except Exception:
                            is_window = False
                        parent_none = getattr(obj, "parent", lambda: None)() is None
                        if is_window or parent_none:
                            name = (
                                getattr(obj, "objectName", lambda: "")() or "<noname>"
                            )
                            cls = type(obj).__name__
                            try:
                                sz = getattr(obj, "size", lambda: None)()
                                w_ = sz.width() if sz is not None else -1
                                h_ = sz.height() if sz is not None else -1
                                size_s = f"{w_}x{h_}" if sz is not None else "?"
                            except Exception:
                                w_, h_, size_s = -1, -1, "?"
                            try:
                                pos = getattr(obj, "pos", lambda: None)()
                                pos_s = (
                                    f"({pos.x()},{pos.y()})" if pos is not None else "?"
                                )
                            except Exception:
                                pos_s = "?"
                            logger.info(
                                "DiagTopLevels: %s event for %s name=%s isWindow=%s parentNone=%s size=%s pos=%s",
                                et.name if hasattr(et, "name") else str(int(et)),
                                cls,
                                name,
                                is_window,
                                parent_none,
                                size_s,
                                pos_s,
                            )

                            if dump_cb:
                                try:
                                    dump_cb("watcher installed")
                                except Exception:
                                    logger.debug(
                                        "DiagnosticsInstaller: dump_top_levels callback failed",
                                        exc_info=True,
                                    )
                except Exception:
                    logger.debug(
                        "DiagnosticsInstaller: _TopLevelWatcher.eventFilter failed",
                        exc_info=True,
                    )
                return QObject.eventFilter(self, obj, event)

        watcher = _TopLevelWatcher(app)
        app.installEventFilter(watcher)
        app._diag_top_levels_watcher = watcher  # type: ignore[attr-defined]
        app._diag_top_levels_installed = True  # type: ignore[attr-defined]
