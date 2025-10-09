"""
Main application module for Aite Commander.

This module serves as the primary entry point and initialization hub for the application.
It handles application lifecycle management, component initialization, graceful shutdown,
and signal handling for both GUI and console modes.

Key Components:
    - ApplicationInitializer: Orchestrates the initialization of all application components
    - Signal handlers: Manage graceful shutdown on system signals
    - Main function: Entry point that coordinates startup, execution, and cleanup

The module follows a robust initialization pattern with proper error handling,
resource cleanup, and support for both interactive and headless execution modes.
"""

from __future__ import annotations

import logging
import signal
import sqlite3
import sys
import os
import functools
import platform
import threading
import time
from contextlib import contextmanager
from enum import IntEnum
from typing import Any, Callable, Optional, Tuple, Type, Protocol, runtime_checkable, TypeVar, Generator, List
from PyQt6.QtCore import QTimer, QThreadPool, QCoreApplication, QSocketNotifier, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow
from app.config_data import app_config
from app.controllers.system.bootstrap import create_main_window
from app.controllers.system.db_init import DatabaseInitializer
from app.controllers.ui.theme_controller import ThemeController
from app.models.db import Database
from app.settings import AppSettings
from app.startup.app_factory import create_application
from i18n.language_service import LanguageService
from app.startup.argument_parser import determine_log_level, parse_arguments
try:
    from i18n import resources_rc
    # Initialize resources explicitly for PyQt6
    resources_rc.qInitResources()
except Exception as e:
    logger.warning("Failed to load i18n resources: %s", e)
from app.startup.browser_profiles_loader import BrowserProfilesLoader
from app.startup.logging_setup import log_shutdown, log_system_info, setup_logging
from app.views.main_components.resource_manager import ResourceManager
from app.controllers.system.app_shutdown_controller import AppShutdownController, ShutdownPriority

logger = logging.getLogger(__name__)

# Для безопасной обработки сигналов ОС в стиле Qt
unix_signal_pipe_read, unix_signal_pipe_write = -1, -1


# Constants for signal handling
SIGNAL_EXIT_CODE_BASE = 128

# Timeouts
THREAD_POOL_SHUTDOWN_TIMEOUT_MS = 1000

# Exit codes
class ExitCode(IntEnum):
    """Application exit codes following Unix conventions."""
    SUCCESS = 0
    INITIALIZATION_FAILURE = 1
    RUNTIME_ERROR = 2
    SIGNAL_BASE = 128


# Retry configuration
T = TypeVar('T')


def retry_on_failure(
    func: Callable[[], T],
    max_attempts: int = 3,
    delay: float = 0.5,
    exponential_backoff: bool = True,
    on_retry: Optional[Callable[[int, Exception], None]] = None
) -> Optional[T]:
    """Retry function on failure with optional exponential backoff and metrics.
    
    Args:
        func: Function to retry
        max_attempts: Maximum number of retry attempts
        delay: Base delay between attempts in seconds
        exponential_backoff: Whether to use exponential backoff
        on_retry: Optional callback for retry metrics/monitoring
        
    Returns:
        Function result on success, None on failure
        
    Raises:
        Last exception if all attempts fail
    """
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            if attempt == max_attempts - 1:
                logger.error("All retry attempts failed: %s", e)
                raise
            
            # Call callback for metrics/monitoring
            if on_retry:
                try:
                    on_retry(attempt, e)
                except Exception as callback_error:
                    logger.warning("Retry callback failed: %s", callback_error)
            
            wait_time = delay * (2 ** attempt if exponential_backoff else 1)
            logger.warning(
                "Attempt %d/%d failed, retrying in %.2fs: %s",
                attempt + 1, max_attempts, wait_time, e
            )
            time.sleep(wait_time)
    return None


@runtime_checkable
class Cleanable(Protocol):
    """Protocol for objects that can be cleaned up."""
    
    def close(self) -> None:
        """Close/cleanup the resource."""
        ...


@runtime_checkable
class Shutdownable(Protocol):
    """Protocol for objects that can be shut down."""
    
    def shutdown(self) -> None:
        """Shutdown the component."""
        ...


@runtime_checkable
class Stoppable(Protocol):
    """Protocol for objects that can be stopped."""
    
    def stop(self) -> None:
        """Stop the component."""
        ...

def initialization_method(
    expected_errors: Tuple[Type[Exception], ...],
    error_message: str,
    critical_message: Optional[str] = None,
) -> Callable[[Callable[..., bool]], Callable[..., bool]]:
    """Decorator for initialization methods with error handling.

    Args:
        expected_errors: Tuple of expected exception types
        error_message: Error message for expected exceptions
        critical_message: Optional message for unexpected exceptions

    Returns:
        Decorated function that returns bool (True=success, False=failure)
    """
    def decorator(func: Callable[..., bool]) -> Callable[..., bool]:
        @functools.wraps(func)
        def wrapper(self: ApplicationInitializer) -> bool:
            try:
                return func(self)
            except expected_errors as e:
                logger.error(f"{error_message}: %s", e, exc_info=True)
                return False
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                message = critical_message or f"Unexpected error in {func.__name__}: %s"
                logger.critical(message, e, exc_info=True)
                return False
        return wrapper
    return decorator

def _create_component(component_class: Type[Any], *args: Any, **kwargs: Any) -> Any:
    """Factory function for creating components."""
    return component_class(*args, **kwargs)


def _setup_main_window_post_creation(main_window: QMainWindow, theme_controller: Any) -> QMainWindow:
    """Configure main window after creation."""
    if hasattr(theme_controller, "set_main_window"):
        theme_controller.set_main_window(main_window)
    else:
        theme_controller.main_window = main_window
    main_window.show()
    return main_window

def _apply_theme_post_creation(theme_controller: Any, settings: AppSettings) -> bool:
    """Apply theme after window creation."""
    theme_name = settings.get_theme()
    theme_controller.apply(theme_name)
    return True

class ApplicationInitializer:
    """Orchestrates application component initialization and cleanup.
    
    Uses ResourceManager for proper resource lifecycle management
    and follows PyQt6 2025 best practices.
    """

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        thread_pool: Optional[QThreadPool] = None,
    ) -> None:
        self.settings = settings
        self.database: Optional[Database] = None
        self.theme_controller: Optional[ThemeController] = None
        self.main_window: Optional[QMainWindow] = None
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        
        # Use ResourceManager for proper cleanup
        self._resource_manager = ResourceManager("ApplicationInitializer")
        self._cleanup_done = False
        self._cleanup_lock = threading.Lock()
        self._shutdown_controller: Optional[AppShutdownController] = None
        # Store signal notifiers for proper shutdown
        self._signal_notifiers: List[QSocketNotifier] = []
    
    def __enter__(self) -> ApplicationInitializer:
        """Context manager entry - initialize application.
        
        Returns:
            Self for use in with statement
            
        Raises:
            RuntimeError: If initialization fails
        """
        if not self.initialize_all():
            raise RuntimeError("Failed to initialize application")
        return self
    
    def __exit__(self, exc_type: Optional[Type[BaseException]], 
                 exc_val: Optional[BaseException], 
                 exc_tb: Optional[Any]) -> bool:
        """Context manager exit - cleanup application.
        
        Args:
            exc_type: Exception type if any
            exc_val: Exception value if any
            exc_tb: Exception traceback if any
            
        Returns:
            False to not suppress exceptions
        """
        self.cleanup(async_cleanup=False)
        return False  # Don't suppress exceptions
    
    def is_healthy(self) -> bool:
        """Check if all critical components are initialized and ready.
        
        Performs both basic and deep health checks for comprehensive validation.
        
        Returns:
            True if all components are properly initialized and functional, False otherwise
        """
        try:
            # Basic checks
            if self._cleanup_done:
                return False
            
            basic_checks = all([
                self.settings is not None,
                self.database is not None,
                self.theme_controller is not None,
                self.main_window is not None,
            ])
            
            if not basic_checks:
                return False
            
            # Deep health checks
            if self.database and hasattr(self.database, 'is_connected'):
                try:
                    if not self.database.is_connected():
                        logger.warning("Database connection is not healthy")
                        return False
                except Exception as e:
                    logger.warning("Database health check failed: %s", e)
                    return False
            
            if self.main_window and hasattr(self.main_window, 'isVisible'):
                try:
                    if not self.main_window.isVisible():
                        logger.debug("Main window is not visible (may be normal during startup)")
                        # Don't fail health check for invisible window - it may be intentional
                except Exception as e:
                    logger.warning("Main window visibility check failed: %s", e)
            
            # Check ResourceManager health
            if hasattr(self._resource_manager, 'is_healthy'):
                try:
                    if not self._resource_manager.is_healthy():
                        logger.warning("ResourceManager is not healthy")
                        return False
                except Exception as e:
                    logger.warning("ResourceManager health check failed: %s", e)
            
            return True
            
        except Exception as e:
            logger.error("Health check failed with exception: %s", e, exc_info=True)
            return False
    
    def get_status(self) -> dict[str, Any]:
        """Get detailed initialization status for debugging and monitoring.
        
        Returns:
            Dictionary with component status and overall health
        """
        return {
            "settings_initialized": self.settings is not None,
            "database_connected": self.database is not None,
            "theme_loaded": self.theme_controller is not None,
            "window_created": self.main_window is not None,
            "cleanup_done": self._cleanup_done,
            "healthy": self.is_healthy()
        }

    def cleanup(self, async_cleanup: bool = False, timeout: float = 5.0) -> bool:
        """Cleanup resources using ResourceManager with optional timeout.
        
        Note: If shutdown controller is available, cleanup is handled there.
        This method is kept for backward compatibility and emergency cleanup.

        Args:
            async_cleanup: If True, schedule cleanup via QTimer (unsafe during shutdown)
            timeout: Maximum time to wait for cleanup completion (0 = no timeout)
            
        Returns:
            True if cleanup completed successfully, False if timed out or failed
        """
        # Quick check without lock for performance
        if self._cleanup_done:
            return True
        
        # If shutdown controller exists and handles cleanup, delegate to it
        if self._shutdown_controller and not async_cleanup:
            logger.debug("Delegating cleanup to AppShutdownController")
            return True

        # Default to synchronous cleanup (safer)
        if not async_cleanup:
            if timeout > 0:
                # Use threading for timeout control
                cleanup_done = threading.Event()
                cleanup_success = [False]  # Mutable container for thread communication
                
                def timed_cleanup() -> None:
                    try:
                        self._cleanup_sync()
                        cleanup_success[0] = True
                    except Exception as e:
                        logger.error("Cleanup failed in timeout thread: %s", e)
                        cleanup_success[0] = False
                    finally:
                        cleanup_done.set()
                
                cleanup_thread = threading.Thread(target=timed_cleanup, daemon=True)
                cleanup_thread.start()
                
                if cleanup_done.wait(timeout):
                    return cleanup_success[0]
                else:
                    logger.error("Cleanup timed out after %.2fs", timeout)
                    return False
            else:
                try:
                    self._cleanup_sync()
                    return True
                except Exception as e:
                    logger.error("Cleanup failed: %s", e)
                    return False
        else:
            # Verify event loop is still running
            app = QCoreApplication.instance()
            if app and not app.closingDown():
                QTimer.singleShot(0, self._cleanup_sync)
                return True  # Assume success for async
            else:
                logger.warning("Event loop not running, forcing sync cleanup")
                try:
                    self._cleanup_sync()
                    return True
                except Exception as e:
                    logger.error("Forced sync cleanup failed: %s", e)
                    return False

    def _cleanup_sync(self) -> None:
        """Synchronous cleanup implementation using ResourceManager.
        
        This method can be called directly or through AppShutdownController.
        """
        # Check and set cleanup flag atomically
        with self._cleanup_lock:
            if self._cleanup_done:
                logger.debug("Cleanup already performed, skipping")
                return
            self._cleanup_done = True
            
        # Perform cleanup without holding lock
        start_time = time.perf_counter()
        try:
            logger.debug("Starting ApplicationInitializer cleanup")
            
            # Disconnect signal notifiers to prevent memory leaks
            for notifier in self._signal_notifiers:
                try:
                    if hasattr(notifier, 'activated'):
                        notifier.activated.disconnect()
                    notifier.setEnabled(False)
                except Exception as e:
                    logger.warning("Failed to disconnect signal notifier: %s", e)
            
            # Use ResourceManager for proper cleanup
            self._resource_manager.cleanup_all()
            
            # Additional thread pool cleanup (if not handled by shutdown controller)
            if self.thread_pool and hasattr(self.thread_pool, "waitForDone"):
                active_count = getattr(self.thread_pool, 'activeThreadCount', lambda: 0)()
                if active_count > 0:
                    logger.debug("Waiting for %d threads to complete", active_count)
                    self.thread_pool.waitForDone(THREAD_POOL_SHUTDOWN_TIMEOUT_MS)
                
        except Exception as e:
            logger.error("Error during ApplicationInitializer cleanup: %s", e, exc_info=True)
        finally:
            duration = time.perf_counter() - start_time
            logger.debug("ApplicationInitializer cleanup completed in %.2fms", duration * 1000)

    def _register_if_cleanable(self, resource: Any, name: str) -> None:
        """Helper to safely register cleanable resources using duck typing."""
        if resource is not None:
            try:
                # Check if it has close method (duck typing)
                if hasattr(resource, 'close') and callable(resource.close):
                    self._resource_manager.register_resource(resource, name=name)
                # Also check for shutdown
                elif hasattr(resource, 'shutdown') and callable(resource.shutdown):
                    self._resource_manager.register_resource(resource, name=name)
                # Check for stop method
                elif hasattr(resource, 'stop') and callable(resource.stop):
                    self._resource_manager.register_resource(resource, name=name)
            except Exception as e:
                logger.warning("Failed to register resource %s: %s", name, e)

    @initialization_method(
        expected_errors=(ValueError, OSError, RuntimeError),
        error_message="Error loading settings",
        critical_message="Unexpected error initializing settings"
    )
    def initialize_settings(self) -> bool:
        self.settings = _create_component(AppSettings) if self.settings is None else self.settings
        self._register_if_cleanable(self.settings, "settings")
        return True

    @initialization_method(
        expected_errors=(sqlite3.Error, OSError, RuntimeError),
        error_message="Error connecting to database",
        critical_message="Unexpected error initializing database"
    )
    def initialize_database(self) -> bool:
        # Type narrowing for better IDE support and type safety with retry mechanism
        retry_count = [0]  # Mutable container for callback
        
        def on_db_retry(attempt: int, error: Exception) -> None:
            retry_count[0] = attempt + 1
            logger.info("Database initialization retry %d: %s", attempt + 1, error)
        
        db = retry_on_failure(
            lambda: _create_component(Database),
            max_attempts=3,
            delay=0.5,
            on_retry=on_db_retry
        )
        
        if retry_count[0] > 0:
            logger.info("Database initialized successfully after %d retries", retry_count[0])
        
        if db is None or not isinstance(db, Database):
            logger.error("Database component creation failed or returned unexpected type: %s", type(db))
            return False
        
        self.database = db
        self._register_if_cleanable(self.database, "database")
        return True

    @initialization_method(
        expected_errors=(ValueError, TypeError, RuntimeError),
        error_message="Error creating ThemeController",
        critical_message="Unexpected error creating ThemeController"
    )
    def initialize_theme_controller(self) -> bool:
        self.theme_controller = _create_component(
            ThemeController,
            self.settings,
            top_panels_controller=None,
        )
        self._register_if_cleanable(self.theme_controller, "theme_controller")
        return True

    @initialization_method(
        expected_errors=(RuntimeError, TypeError, ValueError),
        error_message="Error creating main window",
        critical_message="Unexpected error creating main window"
    )
    def initialize_main_window(self) -> bool:
        self.main_window = _create_component(
            create_main_window,
            self.settings, self.theme_controller, self.database
        )
        _setup_main_window_post_creation(self.main_window, self.theme_controller)
        self._register_if_cleanable(self.main_window, "main_window")
        
        # Initialize shutdown controller after main window is created
        if self.main_window:
            self._shutdown_controller = AppShutdownController(self.main_window)
            # Register ApplicationInitializer cleanup with shutdown controller
            self._shutdown_controller.add_shutdown_handler(
                "application_initializer_cleanup",
                self._cleanup_sync,
                priority=ShutdownPriority.HIGH,
                timeout=3000,
                critical=True
            )
        return True

    @initialization_method(
        expected_errors=(ValueError, RuntimeError, TypeError),
        error_message="Error applying theme",
        critical_message="Unexpected error applying theme"
    )
    def apply_initial_theme(self) -> bool:
        return _apply_theme_post_creation(self.theme_controller, self.settings)

    def initialize_all(self) -> bool:
        """Initialize all components in correct order.

        Returns:
            True if all initialization steps succeeded, False otherwise
        """
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
                # ResourceManager автоматически очистит уже созданные ресурсы
                # при выходе из контекста ApplicationInitializer
                return False
        return True

def safe_signal_handler(
    signum: int, frame: Any, initializer: ApplicationInitializer
) -> None:
    """Wrapper for signal handler with exception protection."""
    try:
        signal_handler(signum, frame, initializer)
    except Exception as e:
        logger.error("Error in signal handler: %s", e, exc_info=True)
        sys.exit(1)


def signal_handler(
    signum: int, frame: Any, initializer: ApplicationInitializer
) -> None:
    """Handle SIGINT/SIGTERM signals.

    Args:
        signum: Signal number
        frame: Current stack frame
        initializer: Application initializer instance (unused, kept for compatibility)
    """
    signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
    logger.info("Received %s signal, initiating graceful shutdown...", signal_name)
    # Use constant for exit code calculation
    exit_code = (
        SIGNAL_EXIT_CODE_BASE + signum
        if signum in (signal.SIGINT, signal.SIGTERM)
        else 1
    )
    QCoreApplication.exit(exit_code)

def should_install_signal_handlers() -> bool:
    """Determine if signal handlers should be installed.

    Returns:
        True for console/headless mode, False for GUI mode
    """
    if platform.system() == "Windows":
        return not sys.stdin.isatty() or not sys.stdout.isatty()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return True
    display_empty = os.environ.get('DISPLAY') in (None, '')
    wayland_empty = os.environ.get('WAYLAND_DISPLAY') in (None, '')
    if display_empty and wayland_empty:
        return True
    return False


# Type alias for signal handler functions
SignalHandler = Callable[[int, Any], None]

def setup_signal_handling(app: QApplication, initializer: ApplicationInitializer) -> List[QSocketNotifier]:
    """Setup cross-platform signal handling compatible with Qt.
    
    Args:
        app: Экземпляр QApplication для привязки обработчиков.
        initializer: Application initializer instance for cleanup coordination
        
    Returns:
        Список созданных QSocketNotifier для предотвращения их удаления сборщиком мусора.
    """
    notifiers = []
    if platform.system() != "Windows":
        global unix_signal_pipe_read, unix_signal_pipe_write
        unix_signal_pipe_read, unix_signal_pipe_write = os.pipe()

        # Устанавливаем обработчик сигнала, который просто пишет в пайп
        def qt_safe_signal_handler(signum: int, frame: Any) -> None:
            try:
                os.write(unix_signal_pipe_write, bytes([signum]))
            except OSError as e:
                # Может произойти, если пайп уже закрыт во время завершения
                logger.warning("Could not write to signal pipe: %s", e)

        signal.signal(signal.SIGINT, qt_safe_signal_handler)
        signal.signal(signal.SIGTERM, qt_safe_signal_handler)

        # Создаем QSocketNotifier для чтения из пайпа в потоке Qt
        notifier = QSocketNotifier(unix_signal_pipe_read, QSocketNotifier.Type.Read, app)

        def handle_qt_signal(sock: int) -> None:
            signum = ord(os.read(sock, 1))
            signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
            logger.info("Received %s signal via QSocketNotifier, initiating graceful shutdown...", signal_name)
            QCoreApplication.exit(SIGNAL_EXIT_CODE_BASE + signum)

        notifier.activated.connect(handle_qt_signal)
        notifiers.append(notifier)
    else:
        # Windows: traditional approach with proper function reference
        def signal_wrapper(signum: int, frame: Any) -> None:
            safe_signal_handler(signum, frame, initializer)

        signal.signal(signal.SIGINT, signal_wrapper)
        signal.signal(signal.SIGTERM, signal_wrapper)

    return notifiers

def main() -> int:
    """Application entry point.

    Returns:
        Exit code (0=success, 1=initialization failure, 2=runtime error)
    """
    args = parse_arguments()
    log_level = determine_log_level(args)
    setup_logging(log_level)
    try:
        # Safer QApplication creation with HiDPI support
        app = QApplication.instance()
        if app is None:
            logger.info("Creating new QApplication instance")
            app = create_application()
            if app is not None:
                # Configure HiDPI support for PyQt6 2025 best practices
                app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
            if app is None:
                logger.critical("Failed to create QApplication instance")
                return 1
        else:
            logger.info("Using existing QApplication instance")

        initializer = ApplicationInitializer()
        # Храним нотификаторы, чтобы GC не удалил их
        signal_notifiers = []
        if should_install_signal_handlers():
            logger.info("Installing signal handlers for console/headless mode")
            signal_notifiers = setup_signal_handling(app, initializer)
            # Store signal notifiers in initializer for proper cleanup
            initializer._signal_notifiers = signal_notifiers
        else:
            logger.info("Running in GUI mode, signal handlers disabled for natural Ctrl+C behavior")
        quit_on_last_window = app_config.get("ui.quit_on_last_window_closed", True)
        app.setQuitOnLastWindowClosed(quit_on_last_window)
        logger.info("Set quit on last window closed: %s", quit_on_last_window)
        try:
            LanguageService.instance().install_translator(app)
        except Exception as e:
            logger.warning("Failed to install translator: %s", e)

        log_system_info()
        if not initializer.initialize_all():
            logger.critical("Failed to initialize application")
            if app:
                app.quit()
            return 1
        db_initializer = DatabaseInitializer(
            initializer.database, initializer.main_window
        )
        db_initializer.initialize_async()
        profiles_loader = BrowserProfilesLoader(initializer.main_window)
        profiles_loader.setup_lazy_loading()
        startup_delay = app_config.get("startup.app_ready_delay_ms", 100)
        QTimer.singleShot(
            startup_delay, lambda: logger.info("Application started successfully")
        )

        exit_code = app.exec()

        # Handle Qt-specific exit codes using enum
        if exit_code == -1:
            logger.critical("QApplication exec() failed with error code -1")
            return ExitCode.RUNTIME_ERROR
        elif exit_code < 0:
            logger.error("QApplication returned unexpected negative code: %d", exit_code)
            return ExitCode.RUNTIME_ERROR
        else:
            logger.info("Application exited with code: %d", exit_code)
            return ExitCode.SUCCESS if exit_code == 0 else ExitCode.INITIALIZATION_FAILURE

    except (KeyboardInterrupt, SystemExit):
        logger.info("Application interrupted by user")
        raise
    except Exception as e:
        logger.critical("Critical error in main(): %s", e, exc_info=True)
        return 2
    finally:
        # Emergency cleanup only if shutdown controller wasn't used
        if initializer:
            with initializer._cleanup_lock:
                cleanup_needed = not initializer._cleanup_done
            
            if cleanup_needed:
                try:
                    logger.info("Performing emergency cleanup in finally block")
                    # Always synchronous in finally
                    initializer.cleanup(async_cleanup=False)
                except Exception as e:
                    logger.error("Error in emergency cleanup: %s", e)
        
        # Restore default signal handlers if they were installed
        if signal_notifiers or platform.system() == "Windows":
            try:
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                logger.debug("Restored default signal handlers")
            except Exception as e:
                logger.warning("Failed to restore signal handlers: %s", e)

        global unix_signal_pipe_read, unix_signal_pipe_write
        if unix_signal_pipe_read != -1:
            os.close(unix_signal_pipe_read)
            os.close(unix_signal_pipe_write)
        
        log_shutdown()

@contextmanager
def application_context() -> Generator[ApplicationInitializer, None, None]:
    """Context manager for application lifecycle (useful in tests).
    
    Yields:
        Initialized ApplicationInitializer instance
        
    Raises:
        RuntimeError: If application initialization fails
    """
    initializer = ApplicationInitializer()
    try:
        if not initializer.initialize_all():
            raise RuntimeError("Failed to initialize application")
        yield initializer
    finally:
        initializer.cleanup(async_cleanup=False)


if __name__ == "__main__":
    sys.exit(main())