"""Module for initializing database in background."""

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.models.db import Database
from app.utils.db.api import run_db

# Module logger
logger = logging.getLogger(__name__)


class DatabaseInitializer:
    """Class for managing database initialization."""

    def __init__(self, database: Database, main_window=None):
        """
        Initializes DatabaseInitializer.

        Args:
            database: Database instance
            main_window: Main application window (optional)
        """
        self.database = database
        self.main_window = main_window

    def initialize_async(
        self,
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        Starts asynchronous database initialization.

        Args:
            on_success: Callback on successful initialization
            on_error: Callback on initialization error
        """
        # Show status in status bar (if available)
        self._update_status_message(
            QCoreApplication.translate("DatabaseInitializer", "Database initialization…")
        )

        # Temporarily block UI interaction during DB initialization
        self._set_ui_enabled(False)

        # Run heavy initialization operations in thread pool
        run_db(
            self._do_db_init,
            use_lock=True,
            description="db_init",
            on_finished=lambda res: self._on_db_init_finished(res, on_success),
            on_error=lambda e: self._on_db_init_error(e, on_error),
        )

    def _do_db_init(self) -> bool:
        """
        Performs database initialization.

        Returns:
            bool: True on success, False on error
        """
        self.database.prepare_dirs()
        self.database.initialize_or_migrate()
        return True

    def _on_db_init_finished(
        self, result: bool, on_success: Optional[Callable] = None
    ) -> None:
        """
        Handler for DB initialization completion.

        Args:
            result: Initialization result
            on_success: Success callback
        """
        if not result:
            # Unlock UI on error
            self._set_ui_enabled(True)

            # Inform user and exit application
            self._show_critical_error(
                "Database initialization error",
                "An error occurred during database initialization. Application will be closed.",
            )
            self._quit_application()
            return

        # On success - complete standard actions
        try:
            # Create connection in main thread on demand
            _ = self.database.connection
        except Exception as e:
            logger.warning("Failed to open connection in main thread: %s", e)

        # Update status bar and unlock UI
        self._update_status_message(
            QCoreApplication.translate("DatabaseInitializer", "Database ready")
        )
        self._update_statusbar()
        self._set_ui_enabled(True)

        # Call success callback
        if on_success:
            try:
                on_success()
            except Exception as e:
                logger.error(
                    "Error in DB initialization success callback: %s", e, exc_info=True
                )

    def _on_db_init_error(
        self, error: Exception, on_error: Optional[Callable[[Exception], None]] = None
    ) -> None:
        """
        Handler for DB initialization error.

        Args:
            error: Exception
            on_error: Error callback
        """
        logger.error(
            "Database initialization error in background: %s",
            error,
            exc_info=True,
        )

        detailed_message = QCoreApplication.translate(
            "DatabaseInitializer",
            "Database initialization error",
        )
        self._update_status_message(detailed_message)
        self._update_statusbar()
        self._set_ui_enabled(True)

        user_message = (
            f"{detailed_message}\n\n{error}"
            if str(error).strip()
            else detailed_message
        )
        self._show_critical_error(
            QCoreApplication.translate(
                "DatabaseInitializer",
                "Database initialization error",
            ),
            user_message,
        )
        self._quit_application()

        # Call error callback
        if on_error:
            try:
                on_error(error)
            except Exception as e:
                logger.error(
                    "Error in DB initialization error callback: %s", e, exc_info=True
                )

    def _update_status_message(self, message: str) -> None:
        """Updates message in status bar."""
        try:
            if (
                self.main_window
                and hasattr(self.main_window, "message_label")
                and self.main_window.message_label
            ):
                self.main_window.message_label.setText(message)
        except Exception as e:
            logger.warning(
                "[DatabaseInitializer] Failed to update status message '%s': %s",
                message,
                e,
                exc_info=True,
            )

    def _update_statusbar(self) -> None:
        """Updates status bar."""
        try:
            if self.main_window and hasattr(self.main_window, "update_statusbar"):
                self.main_window.update_statusbar()
        except Exception as e:
            logger.warning(
                "[DatabaseInitializer] Failed to update status bar: %s",
                e,
                exc_info=True,
            )

    def _set_ui_enabled(self, enabled: bool) -> None:
        """Enables/disables UI."""
        try:
            if self.main_window:
                self.main_window.setEnabled(enabled)
        except Exception as e:
            logger.warning(
                "[DatabaseInitializer] Failed to %sable UI: %s",
                "en" if enabled else "dis",
                e,
                exc_info=True,
            )

    def _show_critical_error(self, title: str, message: str) -> None:
        """Shows critical error."""
        try:
            if self.main_window is None:
                logger.critical(
                    "Main window missing when showing DB initialization error; dialog will be shown without parent"
                )

            QMessageBox.critical(
                self.main_window if self.main_window is not None else None,
                title,
                message,
            )
        except Exception as e:
            logger.error(
                "[DatabaseInitializer] Failed to show critical dialog '%s': %s",
                title,
                e,
                exc_info=True,
            )

    def _quit_application(self) -> None:
        """Quits application."""
        try:
            app_inst = QApplication.instance()
            if app_inst is not None:
                app_inst.quit()
        except Exception as e:
            logger.error(
                "[DatabaseInitializer] Failed to quit application: %s",
                e,
                exc_info=True,
            )
