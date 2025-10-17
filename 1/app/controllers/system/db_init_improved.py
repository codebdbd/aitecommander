"""Improved database initialization using standard QThread/QRunnable."""

import logging
from typing import Callable, Optional

from PyQt6.QtCore import (
    QCoreApplication,
    QMetaObject,
    QObject,
    QRunnable,
    Qt,
    QThread,
    QThreadPool,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.models.db import Database

logger = logging.getLogger(__name__)


class DatabaseInitSignals(QObject):
    """Signals for database initialization."""
    finished = pyqtSignal(bool)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)


class _DialogDispatcher(QObject):
    """Helpers to dispatch dialog display in the GUI thread."""

    def __init__(self, callback: Callable[[], None], parent: QObject | None = None):
        super().__init__(parent)
        self._callback = callback

    @pyqtSlot()
    def invoke(self) -> None:
        self._callback()


class DatabaseInitRunnable(QRunnable):
    """Runnable for database initialization."""

    def __init__(self, database: Database):
        super().__init__()
        self.database = database
        self.signals = DatabaseInitSignals()

    @pyqtSlot()
    def run(self):
        """Run database initialization in background thread."""
        try:
            self.signals.progress.emit("Preparing database directories...")
            self.database.prepare_dirs()

            self.signals.progress.emit("Initializing database...")
            self.database.initialize_or_migrate()

            self.signals.finished.emit(True)
        except Exception as e:
            logger.error("Database initialization error: %s", e)
            self.signals.error.emit(str(e))
            self.signals.finished.emit(False)


class DatabaseInitializer:
    """Improved database initializer using standard Qt threading."""

    def __init__(self, database: Database, main_window=None):
        self.database = database
        self.main_window = main_window
        self._thread_pool = QThreadPool.globalInstance()

    def initialize_async(
        self,
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """Start asynchronous database initialization."""
        # Show status in status bar (if available)
        self._update_status_message(
            QCoreApplication.translate(
                "DatabaseInitializer", "Database initialization…"
            )
        )

        # Block UI during initialization
        self._set_ui_enabled(False)

        # Create and start runnable
        runnable = DatabaseInitRunnable(self.database)

        # Connect signals
        if on_success:
            runnable.signals.finished.connect(lambda success: self._on_success(success, on_success))
        else:
            runnable.signals.finished.connect(self._on_finished)

        if on_error:
            runnable.signals.error.connect(lambda msg: self._on_error(msg, on_error))
        else:
            runnable.signals.error.connect(self._on_error_default)

        runnable.signals.progress.connect(self._on_progress)

        # Start in thread pool
        self._thread_pool.start(runnable)

    def _on_success(self, success: bool, callback: Callable):
        """Handle successful completion."""
        if success:
            callback()
        else:
            self._set_ui_enabled(True)

    @pyqtSlot(bool)
    def _on_finished(self, success: bool):
        """Handle completion in main thread."""
        if not success:
            self._set_ui_enabled(True)
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

        # Re-enable UI
        self._set_ui_enabled(True)

        # Update status
        self._update_status_message(
            QCoreApplication.translate(
                "DatabaseInitializer", "Database ready"
            )
        )

    @pyqtSlot(str)
    def _on_error_default(self, message: str):
        """Default error handler."""
        self._set_ui_enabled(True)
        self._show_critical_error(
            "Database initialization error",
            f"An error occurred during database initialization: {message}"
        )
        self._quit_application()

    def _on_error(self, message: str, callback: Callable[[Exception], None]):
        """Handle error with custom callback."""
        self._set_ui_enabled(True)
        callback(Exception(message))

    @pyqtSlot(str)
    def _on_progress(self, message: str):
        """Handle progress updates."""
        self._update_status_message(message)

    def _update_status_message(self, message: str):
        """Update status bar message if available."""
        if self.main_window and hasattr(self.main_window, 'statusBar'):
            QMetaObject.invokeMethod(
                self.main_window.statusBar(),
                "showMessage",
                Qt.ConnectionType.QueuedConnection,
                message
            )

    def _set_ui_enabled(self, enabled: bool):
        """Enable or disable UI interaction."""
        if self.main_window:
            QMetaObject.invokeMethod(
                self.main_window,
                "setEnabled",
                Qt.ConnectionType.QueuedConnection,
                enabled
            )

    def _show_critical_error(self, title: str, message: str):
        """Show critical error dialog."""
        def show_dialog():
            QMessageBox.critical(
                self.main_window,
                title,
                message
            )

        if self.main_window:
            app = QApplication.instance()
            if app is not None and QThread.currentThread() is not app.thread():
                dispatcher = _DialogDispatcher(show_dialog, parent=self.main_window)
                QMetaObject.invokeMethod(
                    dispatcher,
                    "invoke",
                    Qt.ConnectionType.QueuedConnection,
                )
            else:
                show_dialog()
        else:
            # Fallback for headless mode
            logger.critical("%s: %s", title, message)

    def _quit_application(self):
        """Quit the application."""
        QCoreApplication.quit()
