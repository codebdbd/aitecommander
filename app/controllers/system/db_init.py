"""Module for initializing database in background."""

import logging
from typing import Callable

from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.controllers.ui.dialogs.dialog_manager import DialogManager
from app.core.database_manager import DatabaseManager
from app.models.base.db_base import db_lock
from app.models.db import Database
from app.utils.db.api import run_db
from app.views.widgets.status_bar import set_status_message

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
        self._warmup_handle = None

    def initialize_async(
        self,
        on_success: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """
        Starts asynchronous database initialization.

        Args:
            on_success: Callback on successful initialization
            on_error: Callback on initialization error
        """
        # Show status in status bar (if available)
        self._set_locked_db_warmup_ready(False)
        self._update_status_message(
            QCoreApplication.translate(
                "DatabaseInitializer", "Database initialization…"
            )
        )

        # Keep the shell interactive while disabling only DB-dependent controls.
        self._set_data_widgets_enabled(False)

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
        DatabaseManager.ensure_schema()
        try:
            if getattr(self.database, "_is_sphere_empty", None):
                if self.database._is_sphere_empty():
                    with db_lock:
                        self.database.spheres.initialize_default_spheres()
        except Exception as exc:
            logger.warning("Failed to initialize default spheres: %s", exc)
        return True

    def _on_db_init_finished(
        self, result: bool, on_success: Callable[[], None] | None = None
    ) -> None:
        """
        Handler for DB initialization completion.

        Args:
            result: Initialization result
            on_success: Success callback
        """
        if not result:
            # Re-enable DB-dependent controls on error
            self._set_data_widgets_enabled(True)

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
        self._set_data_widgets_enabled(True)
        self._schedule_locked_db_warmup()

        # Call success callback
        if on_success:
            try:
                on_success()
            except Exception as e:
                logger.error(
                    "Error in DB initialization success callback: %s", e, exc_info=True
                )

    def _schedule_locked_db_warmup(self) -> None:
        """Warm the dedicated locked DB worker to avoid first-user-action cold connect."""
        try:
            QTimer.singleShot(0, self._start_locked_db_warmup)
        except Exception:
            logger.debug("Failed to schedule locked DB warmup", exc_info=True)

    def _start_locked_db_warmup(self) -> None:
        """Create the first locked worker connection eagerly after db_init."""
        try:
            self._warmup_handle = run_db(
                self._do_locked_db_warmup,
                use_lock=True,
                description="db_warmup",
                on_finished=lambda _result: self._set_locked_db_warmup_ready(True),
                on_error=lambda e: (
                    logger.debug("Locked DB warmup failed: %s", e, exc_info=True),
                    self._set_locked_db_warmup_ready(True),
                ),
            )
        except Exception:
            logger.debug("Failed to start locked DB warmup", exc_info=True)
            self._set_locked_db_warmup_ready(True)

    def _do_locked_db_warmup(self) -> bool:
        """Touch the DB from the locked worker so the first UI query reuses the connection."""
        _ = self.database.connection
        return True

    def _set_locked_db_warmup_ready(self, ready: bool) -> None:
        """Expose locked DB warmup readiness via app property for startup-sensitive UI paths."""
        try:
            app = QCoreApplication.instance()
            if app is not None:
                app.setProperty("locked_db_warmup_ready", bool(ready))
        except Exception:
            logger.debug("Failed to set locked_db_warmup_ready property", exc_info=True)

    def _on_db_init_error(
        self, error: Exception, on_error: Callable[[Exception], None] | None = None
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
        self._set_data_widgets_enabled(True)

        user_message = (
            f"{detailed_message}\n\n{error}" if str(error).strip() else detailed_message
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
        if self.main_window and set_status_message(self.main_window, message):
            return
        logger.debug(
            "[DatabaseInitializer] Status bar unavailable for message '%s'",
            message,
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

    def _set_data_widgets_enabled(self, enabled: bool) -> None:
        """Enable or disable only controls that depend on initialized DB data."""
        try:
            if not self.main_window:
                return

            widget_names = (
                "tree",
                "table",
                "tiles",
                "tiles_scroll",
                "spheres_bar",
                "bottom_bar_container",
                "top_bar_toolbar",
            )
            for name in widget_names:
                widget = getattr(self.main_window, name, None)
                if widget is not None and hasattr(widget, "setEnabled"):
                    widget.setEnabled(enabled)

            action_names = (
                "undo_action",
                "redo_action",
                "cut_action",
                "copy_action",
                "paste_action",
                "delete_action",
                "select_all_action",
            )
            for name in action_names:
                action = getattr(self.main_window, name, None)
                if action is not None and hasattr(action, "setEnabled"):
                    action.setEnabled(enabled)
        except Exception as e:
            logger.warning(
                "[DatabaseInitializer] Failed to %sable DB-dependent controls: %s",
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

            DialogManager.show_error(
                self.main_window if self.main_window is not None else None,
                message,
                title,
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
