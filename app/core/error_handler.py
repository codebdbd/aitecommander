"""Global exception handler with logging and GUI notification."""

from __future__ import annotations

import logging
import sys
import traceback
from types import TracebackType

from app.controllers.ui.dialogs.dialog_manager import DialogManager
from app.core.log_manager import LogManager
from app.core.paths.path_manager import PathManager


class GlobalErrorHandler:
    """Installable handler for uncaught exceptions."""

    _installed = False
    _handling = False
    _prev_hook = None

    @staticmethod
    def install() -> None:
        """Install the global exception hook."""
        if GlobalErrorHandler._installed:
            return
        GlobalErrorHandler._prev_hook = sys.excepthook
        sys.excepthook = GlobalErrorHandler._handle_exception
        GlobalErrorHandler._installed = True

    @staticmethod
    def _handle_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        if GlobalErrorHandler._handling:
            return
        if issubclass(exc_type, KeyboardInterrupt):
            prev = GlobalErrorHandler._prev_hook or sys.__excepthook__
            prev(exc_type, exc_value, exc_traceback)
            return

        GlobalErrorHandler._handling = True
        try:
            tb_text = "".join(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            )
            GlobalErrorHandler._safe_log(tb_text)
            GlobalErrorHandler._safe_show_dialog(exc_value, tb_text)
        except Exception:
            try:
                fallback_logger = logging.getLogger("global_error_handler")
                fallback_logger.exception("Unhandled exception handler failed")
            except Exception:
                pass
        finally:
            GlobalErrorHandler._handling = False

    @staticmethod
    def _safe_log(tb_text: str) -> None:
        try:
            logger = LogManager.get_logger("app.global_error_handler")
            logger.error("Unhandled exception:\n%s", tb_text)
        except Exception:
            pass

    @staticmethod
    def _safe_show_dialog(exc_value: BaseException, tb_text: str) -> None:
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception:
            return

        app = QApplication.instance()
        if app is None:
            return

        try:
            _ = PathManager.app_root()
        except Exception:
            pass

        try:
            DialogManager.show_error(
                None,
                f"An unexpected error occurred:\n{exc_value!s}",
                "Unexpected Error",
                details=tb_text,
            )
        except Exception:
            pass
