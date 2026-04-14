# app/views/main_components/init_diagnostics.py
from __future__ import annotations

import logging
import os
from typing import Callable

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)
_DIAG_ENABLED = os.getenv("AITE_DIAGNOSTICS", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


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

    def _log_diagnostics(self, message: str, *args) -> None:
        try:
            logger.info(message, *args)
        except Exception:
            logger.debug(
                "DiagnosticsInstaller: failed to log diagnostic message",
                exc_info=True,
            )

    def install_all(self) -> None:
        if not _DIAG_ENABLED:
            return
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
        fallback = (5, 5)
        try:
            from app.config_data.runtime_config import runtime_app_config as _cfg

            max_resizes = int(getattr(_cfg, "diag_resize_log_max_resizes", fallback[0]))
            max_moves = int(getattr(_cfg, "diag_resize_log_max_moves", fallback[1]))
            return max_resizes, max_moves
        except Exception:
            logger.debug("DiagnosticsInstaller: using fallback resize logger limits", exc_info=True)
            return fallback

    def _create_resize_logger_class(self):
        """Create ResizeLogger class."""
        from PyQt6.QtCore import QCoreApplication
        from PyQt6.QtWidgets import QPlainTextEdit

        manager = self

        def _init_logger(widget: QPlainTextEdit, message: str) -> None:
            widget.setPlainText(message)
            widget.setReadOnly(True)
            try:
                widget.document().setMaximumBlockCount(500)
            except Exception:
                pass

        def _log_resize(widget: QPlainTextEdit, event) -> None:
            manager._log_diagnostics(
                "[ResizeLogger] Widget resized to %sx%s",
                event.size().width(),
                event.size().height(),
            )
            manager._log_diagnostics(
                "[ResizeLogger] Document block count: %s",
                widget.document().blockCount(),
            )
            try:
                QCoreApplication.processEvents()
            except Exception as exc:
                manager._log_diagnostics(
                    "[ResizeLogger] Qt event processing failed: %s",
                    exc,
                )

        def _log_error(exc: Exception) -> None:
            manager._log_diagnostics(
                "[ResizeLogger] Error logging resize event: %s",
                exc,
            )

        class ResizeLogger(QPlainTextEdit):
            """Logs resize events for diagnostics."""

            def __init__(self, message: str, parent=None):
                super().__init__(parent)
                _init_logger(self, message)

            def resizeEvent(self, event):  # type: ignore[override]
                super().resizeEvent(event)
                try:
                    _log_resize(self, event)
                except Exception as exc:  # noqa: BLE001
                    _log_error(exc)

        return ResizeLogger

    def _install_window_resize_logger(self) -> None:
        win = self._window
        if not isinstance(win, QObject):
            raise RuntimeError("window is not QObject")
        if getattr(win, "_diag_resize_logger_installed", False):
            return

        max_resizes, max_moves = self._get_resize_logger_limits()
        _ResizeLogger = self._create_resize_logger_class()
        message = (
            "Resize diagnostics active "
            f"(max resizes={max_resizes}, max moves={max_moves})"
        )
        rl = _ResizeLogger(message, win)
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
