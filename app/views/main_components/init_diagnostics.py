# app/views/main_components/init_diagnostics.py
from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)


class DiagnosticsInstaller:
    """Устанавливает диагностические фильтры и наблюдатели для UI.

    Использование:
        DiagnosticsInstaller(window, dump_top_levels_cb).install_all()
    """

    def __init__(self, window: QObject, dump_top_levels_cb: Optional[Callable[[str], None]] = None) -> None:
        self._window = window
        self._dump_top_levels = dump_top_levels_cb

    def install_all(self) -> None:
        self._install_qt_message_filter()
        self._install_top_level_watcher()
        self._install_window_resize_logger()
        self._install_widget_show_hooks()

    # === Qt message handler ===
    def _install_qt_message_filter(self) -> None:
        try:
            from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
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
                    pass
                return
            try:
                if msg_type in (QtMsgType.QtWarningMsg, QtMsgType.QtInfoMsg):
                    logger.warning("[Qt] %s", msg)
                elif msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                    logger.error("[Qt] %s", msg)
                else:
                    logger.info("[Qt] %s", msg)
            except Exception:
                pass

        try:
            qInstallMessageHandler(_qt_msg_handler)
        except Exception as e:
            raise RuntimeError("qInstallMessageHandler failed") from e

    # === Перехват QWidget.show()/setVisible ===
    def _diagnostics_enabled(self) -> bool:
        try:
            import os
            if os.environ.get("OSTEEN_DIAG_TOPLEVEL") == "1":
                return True
        except Exception:
            pass
        try:
            return logger.isEnabledFor(logging.DEBUG)
        except Exception:
            return False

    def _install_widget_show_hooks(self) -> None:
        if not self._diagnostics_enabled():
            return
        if getattr(QApplication, "_diag_show_hooks_installed", False):
            return

        import traceback

        def _log_widget(w: QWidget, method: str) -> None:
            try:
                parent_none = (w.parent() is None)
            except Exception:
                parent_none = True
            try:
                is_window = bool(w.isWindow())
            except Exception:
                is_window = False
            try:
                sz = w.size()
                w_ = sz.width()
                h_ = sz.height()
            except Exception:
                w_, h_ = -1, -1
            if (parent_none or is_window):
                try:
                    name = w.objectName() or "<noname>"
                except Exception:
                    name = "<noname>"
                try:
                    title = w.windowTitle() or ""
                except Exception:
                    title = ""
                try:
                    flags = w.windowFlags()
                    flags_s = hex(int(flags))
                except Exception:
                    flags_s = "?"
                stack = "\n".join(traceback.format_stack(limit=25))
                logger.info(
                    "DiagTopLevels: QWidget.%s top-level show -> cls=%s name=%s title='%s' size=%sx%s flags=%s\n%s",
                    method, type(w).__name__, name, title, w_, h_, flags_s, stack,
                )

        if not hasattr(QWidget, "_orig_show_diag"):
            QWidget._orig_show_diag = QWidget.show  # type: ignore[attr-defined]

            def _diag_show(self: QWidget, *args, **kwargs):
                try:
                    _log_widget(self, "show")
                except Exception:
                    pass
                return QWidget._orig_show_diag(self, *args, **kwargs)  # type: ignore[attr-defined]

            QWidget.show = _diag_show  # type: ignore[assignment]

        if not hasattr(QWidget, "_orig_setVisible_diag"):
            QWidget._orig_setVisible_diag = QWidget.setVisible  # type: ignore[attr-defined]

            def _diag_setVisible(self: QWidget, vis: bool):
                try:
                    if bool(vis):
                        _log_widget(self, "setVisible(True)")
                except Exception:
                    pass
                return QWidget._orig_setVisible_diag(self, vis)  # type: ignore[attr-defined]

            QWidget.setVisible = _diag_setVisible  # type: ignore[assignment]

        QApplication._diag_show_hooks_installed = True  # type: ignore[attr-defined]

    def _install_window_resize_logger(self) -> None:
        win = self._window
        if not isinstance(win, QObject):
            raise RuntimeError("window is not QObject")
        if getattr(win, "_diag_resize_logger_installed", False):
            return

        class _ResizeLogger(QObject):
            def __init__(self, parent=None):
                super().__init__(parent)
                self._resizes = 0
                self._moves = 0
                try:
                    from app.config_data import app_config as _cfg
                    self._max_resizes = int(getattr(_cfg, "get", lambda *_: 5)("diag.resize_log.max_resizes", 5))
                    self._max_moves = int(getattr(_cfg, "get", lambda *_: 5)("diag.resize_log.max_moves", 5))
                except Exception:
                    self._max_resizes = 5
                    self._max_moves = 5
                self._owner = parent

            def _maybe_uninstall(self, obj):
                try:
                    if self._resizes >= self._max_resizes and self._moves >= self._max_moves:
                        try:
                            obj.removeEventFilter(self)
                        except Exception:
                            pass
                        try:
                            if hasattr(self._owner, "_diag_resize_logger") and getattr(self._owner, "_diag_resize_logger", None) is self:
                                setattr(self._owner, "_diag_resize_logger", None)  # type: ignore[attr-defined]
                                setattr(self._owner, "_diag_resize_logger_installed", False)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    pass

            def eventFilter(self, obj, event):
                et = event.type()
                try:
                    if et == QEvent.Type.Resize and self._resizes < self._max_resizes:
                        self._resizes += 1
                        try:
                            sz = getattr(obj, "size", lambda: None)()
                            size_s = f"{sz.width()}x{sz.height()}" if sz is not None else "?"
                        except Exception:
                            size_s = "?"
                        logger.info("DiagTopLevels: Resize #%s -> %s", self._resizes, size_s)
                        self._maybe_uninstall(obj)
                    elif et == QEvent.Type.Move and self._moves < self._max_moves:
                        self._moves += 1
                        try:
                            pos = getattr(obj, "pos", lambda: None)()
                            pos_s = f"({pos.x()},{pos.y()})" if pos is not None else "?"
                        except Exception:
                            pos_s = "?"
                        logger.info("DiagTopLevels: Move #%s -> %s", self._moves, pos_s)
                        self._maybe_uninstall(obj)
                except Exception:
                    pass
                return QObject.eventFilter(self, obj, event)

        rl = _ResizeLogger(win)
        win.installEventFilter(rl)
        win._diag_resize_logger = rl  # type: ignore[attr-defined]
        win._diag_resize_logger_installed = True  # type: ignore[attr-defined]

    def _install_top_level_watcher(self) -> None:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("No QApplication instance")
        if getattr(app, "_diag_top_levels_installed", False):
            return

        class _TopLevelWatcher(QObject):
            def eventFilter(self, obj, event):
                try:
                    et = event.type()
                    if et in (QEvent.Type.Show, QEvent.Type.ShowToParent, QEvent.Type.WindowActivate):
                        try:
                            is_window = bool(getattr(obj, "isWindow", lambda: False)())
                        except Exception:
                            is_window = False
                        parent_none = getattr(obj, "parent", lambda: None)() is None
                        if is_window or parent_none:
                            name = getattr(obj, "objectName", lambda: "")() or "<noname>"
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
                                pos_s = f"({pos.x()},{pos.y()})" if pos is not None else "?"
                            except Exception:
                                pos_s = "?"
                            logger.info(
                                "DiagTopLevels: %s event for %s name=%s isWindow=%s parentNone=%s size=%s pos=%s",
                                et.name if hasattr(et, "name") else str(int(et)), cls, name, is_window, parent_none, size_s, pos_s,
                            )

                            if self._dump_top_levels:
                                try:
                                    self._dump_top_levels("watcher installed")
                                except Exception:
                                    pass
                except Exception:
                    pass
                return QObject.eventFilter(self, obj, event)

        watcher = _TopLevelWatcher(app)
        app.installEventFilter(watcher)
        app._diag_top_levels_watcher = watcher  # type: ignore[attr-defined]
        app._diag_top_levels_installed = True   # type: ignore[attr-defined]
