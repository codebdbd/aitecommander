"""Application initialization helpers and lifecycle orchestration."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from enum import Enum
from typing import (
    Any,
    Callable,
    Protocol,
    TypeVar,
    runtime_checkable,
)

from PyQt6.QtCore import QCoreApplication, QSocketNotifier, QThreadPool, QTimer
from PyQt6.QtWidgets import QMainWindow

from app.controllers.system.app_shutdown_controller import (
    AppShutdownController,
    ShutdownPriority,
)
from app.controllers.system.bootstrap import create_main_window
from app.controllers.ui.theme_controller import ThemeController
from app.models.db import Database
from app.settings import AppSettings
from app.views.main_components.resource_manager import ResourceManager

logger = logging.getLogger(__name__)

THREAD_POOL_SHUTDOWN_TIMEOUT_MS = 1000

T = TypeVar("T")


class StartupMode(Enum):
    """Application startup modes."""

    GUI = "gui"
    HEADLESS = "headless"


def retry_on_failure(
    func: Callable[[], T],
    max_attempts: int = 3,
    delay: float = 0.5,
    exponential_backoff: bool = True,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T | None:
    """Retry callable on failure with optional exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - best effort logging
            if attempt == max_attempts - 1:
                logger.error("All retry attempts failed: %s", exc)
                raise

            if on_retry:
                try:
                    on_retry(attempt, exc)
                except Exception as callback_error:
                    logger.warning("Retry callback failed: %s", callback_error)

            wait_time = delay * (2 ** attempt if exponential_backoff else 1)
            logger.warning(
                "Attempt %d/%d failed, retrying in %.2fs: %s",
                attempt + 1,
                max_attempts,
                wait_time,
                exc,
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
    expected_errors: tuple[type[Exception], ...],
    error_message: str,
    critical_message: str | None = None,
) -> Callable[[Callable[..., bool]], Callable[..., bool]]:
    """Decorator for initialization methods with error handling."""

    def decorator(func: Callable[..., bool]) -> Callable[..., bool]:
        def wrapper(self: ApplicationInitializer) -> bool:
            try:
                return func(self)
            except expected_errors as exc:
                logger.error("%s: %s", error_message, exc, exc_info=True)
                return False
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                message = critical_message or f"Unexpected error in {func.__name__}: %s"
                logger.critical(message, exc, exc_info=True)
                return False

        return wrapper

    return decorator


def _create_component(component_class: type[Any], *args: Any, **kwargs: Any) -> Any:
    """Factory helper for creating components."""
    return component_class(*args, **kwargs)


def _setup_main_window_post_creation(
    main_window: QMainWindow, theme_controller: Any
) -> QMainWindow:
    """Configure main window after creation."""
    if hasattr(theme_controller, "set_main_window"):
        theme_controller.set_main_window(main_window)
    else:
        theme_controller.main_window = main_window
    main_window.show()
    return main_window


def _apply_theme_post_creation(
    theme_controller: Any, settings: AppSettings
) -> bool:
    """Apply theme after window creation."""
    theme_name = settings.get_theme()
    theme_controller.apply(theme_name)
    return True


class ApplicationInitializer:
    """Orchestrates application component initialization and cleanup."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        thread_pool: QThreadPool | None = None,
        mode: StartupMode = StartupMode.GUI,
    ) -> None:
        self.settings = settings
        self.database: Database | None = None
        self.theme_controller: ThemeController | None = None
        self.main_window: QMainWindow | None = None
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        self.mode = mode

        self._resource_manager = ResourceManager("ApplicationInitializer")
        self._cleanup_done = False
        self._cleanup_lock = threading.Lock()
        self._shutdown_controller: AppShutdownController | None = None
        self._signal_notifiers: list[QSocketNotifier] = []

    def __enter__(self) -> ApplicationInitializer:
        if not self.initialize_all():
            raise RuntimeError("Failed to initialize application")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: Any | None,
    ) -> bool:
        self.cleanup(async_cleanup=False)
        return False

    def is_healthy(self) -> bool:
        """Check if all critical components are initialized and healthy."""
        try:
            if self._cleanup_done:
                return False

            basic_checks = all(
                [
                    self.settings is not None,
                    self.database is not None,
                    self.theme_controller is not None,
                    self.main_window is not None,
                ]
            )
            if not basic_checks:
                return False

            if self.database and hasattr(self.database, "is_connected"):
                try:
                    if not self.database.is_connected():
                        logger.warning("Database connection is not healthy")
                        return False
                except Exception as exc:
                    logger.warning("Database health check failed: %s", exc)
                    return False

            if self.main_window and hasattr(self.main_window, "isVisible"):
                try:
                    if not self.main_window.isVisible():
                        logger.debug(
                            "Main window is not visible (may be normal during startup)"
                        )
                except Exception as exc:
                    logger.warning("Main window visibility check failed: %s", exc)

            if hasattr(self._resource_manager, "is_healthy"):
                try:
                    if not self._resource_manager.is_healthy():
                        logger.warning("ResourceManager is not healthy")
                        return False
                except Exception as exc:
                    logger.warning("ResourceManager health check failed: %s", exc)

            return True

        except Exception as exc:
            logger.error("Health check failed with exception: %s", exc, exc_info=True)
            return False

    def get_status(self) -> dict[str, Any]:
        """Get detailed initialization status."""
        return {
            "mode": self.mode.value,
            "settings_initialized": self.settings is not None,
            "database_connected": self.database is not None,
            "theme_loaded": self.theme_controller is not None,
            "window_created": self.main_window is not None,
            "cleanup_done": self._cleanup_done,
            "healthy": self.is_healthy(),
        }

    def attach_signal_notifiers(self, notifiers: Sequence[QSocketNotifier]) -> None:
        """Attach signal notifiers for lifecycle management."""
        self._signal_notifiers = list(notifiers)

    def detach_signal_notifiers(self) -> None:
        """Clear attached signal notifiers."""
        for notifier in self._signal_notifiers:
            try:
                if hasattr(notifier, "activated"):
                    notifier.activated.disconnect()
                notifier.setEnabled(False)
            except Exception as exc:
                logger.debug("Failed to detach signal notifier: %s", exc)
        self._signal_notifiers.clear()

    def has_pending_cleanup(self) -> bool:
        """Return True if cleanup still needs to be executed."""
        with self._cleanup_lock:
            return not self._cleanup_done

    def ensure_emergency_cleanup(self) -> None:
        """Perform emergency cleanup if required."""
        if self.has_pending_cleanup():
            logger.info("Performing emergency cleanup for ApplicationInitializer")
            self.cleanup(async_cleanup=False)

    def cleanup(self, async_cleanup: bool = False, timeout: float = 5.0) -> bool:
        """Cleanup resources using ResourceManager."""
        if self._cleanup_done:
            return True

        if self._shutdown_controller and not async_cleanup:
            logger.debug("Delegating cleanup to AppShutdownController")
            return True

        if not async_cleanup:
            start_time = time.perf_counter()
            try:
                self._cleanup_sync()
            except Exception as exc:
                logger.error("Cleanup failed: %s", exc)
                return False

            duration = time.perf_counter() - start_time
            if timeout > 0 and duration > timeout:
                logger.warning(
                    "Cleanup exceeded timeout of %.2fs (took %.2fs)",
                    timeout,
                    duration,
                )
            return True
        else:
            app = QCoreApplication.instance()
            if app and not app.closingDown():
                QTimer.singleShot(0, self._cleanup_sync)
                return True

            logger.warning("Event loop not running, forcing sync cleanup")
            try:
                self._cleanup_sync()
                return True
            except Exception as exc:
                logger.error("Forced sync cleanup failed: %s", exc)
                return False

    def _cleanup_sync(self) -> None:
        """Synchronous cleanup implementation using ResourceManager."""
        with self._cleanup_lock:
            if self._cleanup_done:
                logger.debug("Cleanup already performed, skipping")
                return
            self._cleanup_done = True

        start_time = time.perf_counter()
        try:
            logger.debug("Starting ApplicationInitializer cleanup")

            self.detach_signal_notifiers()

            self._resource_manager.cleanup_all()

            if self.thread_pool and hasattr(self.thread_pool, "waitForDone"):
                active_count = getattr(
                    self.thread_pool, "activeThreadCount", lambda: 0
                )()
                if active_count > 0:
                    logger.debug("Waiting for %d threads to complete", active_count)
                    self.thread_pool.waitForDone(THREAD_POOL_SHUTDOWN_TIMEOUT_MS)

        except Exception as exc_type:
            _exc_val, _exc_tb = sys.exc_info()
            logger.error(
                "Error during ApplicationInitializer cleanup: %s", exc_type, exc_info=True
            )
        finally:
            duration = time.perf_counter() - start_time
            logger.debug(
                "ApplicationInitializer cleanup completed in %.2fms", duration * 1000
            )

    def _register_if_cleanable(self, resource: Any, name: str) -> None:
        """Helper to safely register cleanable resources using duck typing."""
        if resource is not None:
            try:
                if hasattr(resource, "close") and callable(resource.close):
                    self._resource_manager.register_resource(resource, name=name)
                elif hasattr(resource, "shutdown") and callable(resource.shutdown):
                    self._resource_manager.register_resource(resource, name=name)
                elif hasattr(resource, "stop") and callable(resource.stop):
                    self._resource_manager.register_resource(resource, name=name)
            except Exception as exc:
                logger.warning("Failed to register resource %s: %s", name, exc)

    @initialization_method(
        expected_errors=(ValueError, OSError, RuntimeError),
        error_message="Error loading settings",
        critical_message="Unexpected error initializing settings",
    )
    def initialize_settings(self) -> bool:
        self.settings = _create_component(AppSettings) if self.settings is None else self.settings
        self._register_if_cleanable(self.settings, "settings")
        return True

    @initialization_method(
        expected_errors=(sqlite3.Error, OSError, RuntimeError),
        error_message="Error connecting to database",
        critical_message="Unexpected error initializing database",
    )
    def initialize_database(self) -> bool:
        retry_count = [0]

        def on_db_retry(attempt: int, error: Exception) -> None:
            retry_count[0] = attempt + 1
            logger.info("Database initialization retry %d: %s", attempt + 1, error)

        db = retry_on_failure(
            lambda: _create_component(Database),
            max_attempts=3,
            delay=0.5,
            on_retry=on_db_retry,
        )

        if retry_count[0] > 0:
            logger.info(
                "Database initialized successfully after %d retries", retry_count[0]
            )

        if db is None or not isinstance(db, Database):
            logger.error(
                "Database component creation failed or returned unexpected type: %s",
                type(db),
            )
            return False

        self.database = db
        self._register_if_cleanable(self.database, "database")
        return True

    @initialization_method(
        expected_errors=(ValueError, TypeError, RuntimeError),
        error_message="Error creating ThemeController",
        critical_message="Unexpected error creating ThemeController",
    )
    def initialize_theme_controller(self) -> bool:
        if self.mode != StartupMode.GUI:
            self.theme_controller = None
            return True
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
        critical_message="Unexpected error creating main window",
    )
    def initialize_main_window(self) -> bool:
        if self.mode != StartupMode.GUI:
            self.main_window = None
            return True
        self.main_window = _create_component(
            create_main_window, self.settings, self.theme_controller, self.database
        )
        _setup_main_window_post_creation(self.main_window, self.theme_controller)
        self._register_if_cleanable(self.main_window, "main_window")

        if self.main_window:
            self._shutdown_controller = AppShutdownController(self.main_window)
            self._shutdown_controller.add_shutdown_handler(
                "application_initializer_cleanup",
                self._cleanup_sync,
                priority=ShutdownPriority.HIGH,
                timeout=3000,
                critical=True,
            )
        return True

    @initialization_method(
        expected_errors=(ValueError, RuntimeError, TypeError),
        error_message="Error applying theme",
        critical_message="Unexpected error applying theme",
    )
    def apply_initial_theme(self) -> bool:
        if self.mode != StartupMode.GUI or not self.theme_controller or not self.settings:
            return True
        return _apply_theme_post_creation(self.theme_controller, self.settings)

    def initialize_all(self) -> bool:
        """Initialize all components in the correct order."""
        initialization_steps = [
            ("settings", self.initialize_settings),
            ("database", self.initialize_database),
        ]

        if self.mode == StartupMode.GUI:
            initialization_steps.extend(
                [
                    ("theme controller", self.initialize_theme_controller),
                    ("main window", self.initialize_main_window),
                    ("theme", self.apply_initial_theme),
                ]
            )

        for step_name, step_func in initialization_steps:
            if not step_func():
                logger.critical(
                    "Critical error during initialization of %s", step_name
                )
                return False
        return True


@contextmanager
def application_context(
    mode: StartupMode = StartupMode.GUI,
) -> Generator[ApplicationInitializer, None, None]:
    """Context manager for application lifecycle (useful in tests)."""
    initializer = ApplicationInitializer(mode=mode)
    try:
        if not initializer.initialize_all():
            raise RuntimeError("Failed to initialize application")
        yield initializer
    finally:
        initializer.cleanup(async_cleanup=False)


__all__ = [
    "ApplicationInitializer",
    "THREAD_POOL_SHUTDOWN_TIMEOUT_MS",
    "StartupMode",
    "application_context",
    "retry_on_failure",
    "Cleanable",
    "Shutdownable",
    "Stoppable",
    "initialization_method",
]
