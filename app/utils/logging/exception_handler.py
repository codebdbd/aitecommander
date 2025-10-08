# app/utils/logging/exception_handler.py

import logging
import sys
import traceback

from PyQt6.QtWidgets import QApplication

from app.controllers.ui.dialogs import DialogManager

logger = logging.getLogger(__name__)


class ExceptionHandler:
    """Global exception handler."""

    def __init__(self):
        self.original_excepthook = sys.excepthook
        sys.excepthook = self.handle_exception

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Handles uncaught exceptions."""
        if issubclass(exc_type, KeyboardInterrupt):
            # Return standard behavior for interruption
            self.original_excepthook(exc_type, exc_value, exc_traceback)
            return

        # Log critical error
        logger.critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )

        # Show error information to user
        self._show_error_dialog(exc_type, exc_value, exc_traceback)

    def _show_error_dialog(self, exc_type, exc_value, exc_traceback):
        """Shows error information dialog."""
        try:
            # Check if QApplication exists
            if QApplication.instance() is None:
                error_text = f"Critical error occurred: {exc_type.__name__}"
                error_info = str(exc_value)
                error_details = "".join(
                    traceback.format_exception(exc_type, exc_value, exc_traceback)
                )
                logger.error("%s", error_text)
                logger.error("%s", error_info)
                logger.error("Details:")
                logger.error("%s", error_details)
                return

            error_text = f"Critical error occurred: {exc_type.__name__}"
            error_info = str(exc_value)
            error_details = "".join(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            )

            DialogManager.show_error(
                None,
                "Critical error",
                error_text,
                informative_text=f"{error_info}\n\nApplication will be closed.",
                details=error_details,
            )
        except Exception as e:
            # If even dialog cannot be shown
            logger.critical("Critical error: %s: %s", exc_type.__name__, exc_value)
            logger.critical("Error showing dialog: %s", e, exc_info=True)
