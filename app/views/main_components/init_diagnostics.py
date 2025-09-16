# app/views/main_components/init_diagnostics.py
from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class DiagnosticsInstaller:
    """Устанавливает диагностические фильтры и наблюдатели для UI.

    Использование:
        DiagnosticsInstaller(window, dump_top_levels_cb).install_all()
    """

    def __init__(
        self,
        window: QObject,
        dump_top_levels_cb: Optional[Callable[[str], None]] = None,
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

    # (Удалено) Глобальные хуки QWidget.show/setVisible больше не используются.

    def _install_window_resize_logger(self) -> None:
        win = self._window
        if not isinstance(win, QObject):
            raise RuntimeError("window is not QObject")
        if getattr(win, "_diag_resize_logger_installed", False):
            return

        # Используем выносной класс для логирования ресайзов/перемещений
        from .resize_logger import ResizeLogger

        rl = ResizeLogger(win)
        win.installEventFilter(rl)
        win._diag_resize_logger = rl  # type: ignore[attr-defined]
        win._diag_resize_logger_installed = True  # type: ignore[attr-defined]

    def _install_top_level_watcher(self) -> None:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("No QApplication instance")
        if getattr(app, "_diag_top_levels_installed", False):
            return

        # Захватываем колбэк дампа в замыкание, чтобы использовать его внутри watcher,
        # не обращаясь к несуществующему атрибуту экземпляра внутреннего класса.
        dump_cb = self._dump_top_levels

        class _TopLevelWatcher(QObject):
            def eventFilter(self, obj, event):
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
