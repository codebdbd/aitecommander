import logging
import signal
import sqlite3
import sys
import os

from PyQt6.QtCore import QTimer

from app.config_data import app_config
from app.controllers.system.bootstrap import create_main_window
from app.controllers.system.db_init import DatabaseInitializer
from app.controllers.ui.theme_controller import ThemeController
from app.models.db import Database
from app.settings import AppSettings
from app.startup.app_factory import create_application
from i18n.language_service import LanguageService
from app.startup.argument_parser import determine_log_level, parse_arguments

# Register Qt resources for translations (:/i18n/app_*.qm) if available
try:  # noqa: SIM105 - best-effort import, optional in dev mode
    from i18n import resources_rc  # type: ignore  # noqa: F401
except Exception:
    # Fallback: LanguageService will try filesystem i18n/app_*.qm
    pass
from app.startup.browser_profiles_loader import BrowserProfilesLoader
from app.startup.logging_setup import log_shutdown, log_system_info, setup_logging

# Module logger
logger = logging.getLogger(__name__)


class ApplicationInitializer:
    """Initializer for application components."""

    def __init__(self, settings=None):
        self.settings = settings
        self.database = None
        self.theme_controller = None
        self.main_window = None

    def cleanup(self, async_cleanup=True):
        """Clean up application resources."""
        if async_cleanup:
            # Schedule cleanup in GUI thread to avoid blocking
            QTimer.singleShot(0, lambda: self._cleanup_sync())
        else:
            # Direct cleanup for non-GUI contexts
            self._cleanup_sync()

    def _cleanup_sync(self):
        """Synchronous cleanup implementation."""
        try:
            # Close DB connection if available
            if self.database and hasattr(self.database, "close"):
                self.database.close()
        except (sqlite3.Error, AttributeError) as e:
            # Log expected connection/attribute errors
            logger.error("Error while closing DB connection: %s", e)

        # Wait for background DB tasks to finish (run_db)
        try:
            from app.utils.db.executors.pool import get_thread_pool

            pool = get_thread_pool()
            try:
                # Try waiting with timeout if supported
                if hasattr(pool, "waitForDone"):
                    try:
                        pool.waitForDone(5000)  # 5 seconds for graceful shutdown
                    except TypeError:
                        # Fallback: signature without args in some versions
                        pool.waitForDone()
            except AttributeError as e:
                # Pool has no expected method — not critical
                logger.debug("Exception while waiting for thread pool completion: %s", e)
        except AttributeError as e:
            # Pool object missing/without expected attributes — not critical
            logger.debug("Failed to get thread pool for DB tasks: %s", e)

    def initialize_settings(self) -> bool:
        """Initialize application settings."""
        try:
            if self.settings is None:
                self.settings = AppSettings()
            return True
        except (ValueError, OSError, RuntimeError) as e:
            # Expected environment/settings configuration errors
            logger.error("Error loading settings: %s", e, exc_info=True)
            return False
        except Exception as e:
            # Unexpected error — mark CRITICAL for quick diagnostics
            logger.critical("Unexpected error initializing settings: %s", e, exc_info=True)
            return False

    def initialize_database(self) -> bool:
        """Initialize database connection."""
        try:
            self.database = Database()
            return True
        except (sqlite3.Error, OSError, RuntimeError) as e:
            logger.error("Error connecting to database: %s", e, exc_info=True)
            return False
        except Exception as e:
            logger.critical("Unexpected error initializing database: %s", e, exc_info=True)
            return False

    def initialize_theme_controller(self) -> bool:
        """Initialize theme controller."""
        try:
            self.theme_controller = ThemeController(
                self.settings,
                top_panels_controller=None,
            )
            return True
        except (ValueError, TypeError, RuntimeError) as e:
            logger.error("Error creating ThemeController: %s", e, exc_info=True)
            return False
        except Exception as e:
            logger.critical("Unexpected error creating ThemeController: %s", e, exc_info=True)
            return False

    def initialize_main_window(self) -> bool:
        """Initialize the main application window."""
        try:
            # Create window via bootstrap (window doesn't take Database in constructor)
            self.main_window = create_main_window(
                self.settings, self.theme_controller, self.database
            )
            if hasattr(self.theme_controller, "set_main_window"):
                self.theme_controller.set_main_window(self.main_window)
            else:
                self.theme_controller.main_window = self.main_window

            # Show the main window - critical for desktop GUI applications
            self.main_window.show()

            return True
        except (RuntimeError, TypeError, ValueError) as e:
            logger.error("Error creating main window: %s", e, exc_info=True)
            return False
        except Exception as e:
            logger.critical("Unexpected error creating main window: %s", e, exc_info=True)
            return False

    def apply_initial_theme(self) -> bool:
        """Apply the initial theme."""
        try:
            theme_name = self.settings.get_theme()
            self.theme_controller.apply(theme_name)
            return True
        except (ValueError, RuntimeError, TypeError) as e:
            logger.error("Error applying theme: %s", e, exc_info=True)
            return False
        except Exception as e:
            logger.critical("Unexpected error applying theme: %s", e, exc_info=True)
            return False

    def initialize_all(self) -> bool:
        """Perform full initialization of all components."""
        # Apply theme after creating main window to ensure styles are applied correctly
        initialization_steps = [
            ("settings", self.initialize_settings),
            ("database", self.initialize_database),
            ("theme controller", self.initialize_theme_controller),
            ("main window", self.initialize_main_window),
            ("theme", self.apply_initial_theme),
        ]
        for step_name, step_func in initialization_steps:
            if not step_func():
                logger.critical("Critical error during initialization of %s", step_name)
                return False
        return True


def signal_handler(signum, frame, initializer):
    """Handle system signals (SIGINT, SIGTERM) for graceful shutdown."""
    signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
    logger.info("Received %s signal, initiating graceful shutdown...", signal_name)

    try:
        # Perform cleanup synchronously for immediate response to signals
        if initializer:
            initializer.cleanup(async_cleanup=False)
    except Exception as e:
        logger.error("Error during signal cleanup: %s", e)

    # Exit with appropriate code based on signal type
    exit_code = 128 + signum if signum in (signal.SIGINT, signal.SIGTERM) else 1
    sys.exit(exit_code)


def should_install_signal_handlers():
    """Determine if signal handlers should be installed.

    Returns False for GUI applications where Ctrl+C should work as copy,
    True for headless/console applications where Ctrl+C should interrupt.
    """
    # If stdin is not a terminal (piped input, redirected, etc.), install handlers
    if not sys.stdin.isatty():
        return True

    # If stdout is not a terminal (redirected output), install handlers
    if not sys.stdout.isatty():
        return True

    # Check if we're running in a headless mode (no display)
    if os.environ.get('DISPLAY') == '' or os.environ.get('WAYLAND_DISPLAY') == '':
        return True

    # For GUI applications with terminal input, don't install handlers
    # Let PyQt6 handle input naturally or ignore terminal signals
    return False


def main():
    """Main application entry point."""
    # Parse command line arguments
    args = parse_arguments()
    log_level = determine_log_level(args)

    # Initialize logging system
    setup_logging(log_level)

    # Create initializer early so cleanup() runs even on early failures
    initializer = ApplicationInitializer()

    # Install signal handlers only for appropriate contexts
    if should_install_signal_handlers():
        logger.info("Installing signal handlers for console/headless mode")
        signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, initializer))
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, initializer))
    else:
        logger.info("Running in GUI mode, signal handlers disabled for natural Ctrl+C behavior")

    try:
        app = create_application()
        LanguageService.instance().install_translator(app)
        log_system_info()

        # Connect cleanup to application's aboutToQuit signal for proper lifecycle management
        app.aboutToQuit.connect(lambda: initializer.cleanup() if initializer else None)

        if not initializer.initialize_all():
            logger.critical("Failed to initialize application")
            if app:
                app.quit()
            return 1

        # Initialize DB in background
        db_initializer = DatabaseInitializer(
            initializer.database, initializer.main_window
        )
        db_initializer.initialize_async()

        # Set up lazy loading of browser profiles
        profiles_loader = BrowserProfilesLoader(initializer.main_window)
        profiles_loader.setup_lazy_loading()

        startup_delay = app_config.get("startup.app_ready_delay_ms", 100)
        QTimer.singleShot(startup_delay, lambda: logger.info("Application started successfully"))
        exit_code = app.exec()
        return exit_code
    except Exception as e:
        logger.critical("Critical error in main(): %s", e, exc_info=True)
        return 1
    finally:
        # Emergency cleanup only - normal cleanup handled by aboutToQuit signal
        if initializer:
            try:
                initializer.cleanup(async_cleanup=False)
            except Exception as e:
                logger.error("Error in emergency cleanup: %s", e)
        log_shutdown()


if __name__ == "__main__":
    sys.exit(main())
