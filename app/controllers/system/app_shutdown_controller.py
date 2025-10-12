# app/controllers/app_shutdown_controller.py

import inspect
import logging
import sys
import threading
import time
from contextlib import contextmanager
from enum import Enum
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow

from app.config_data import app_config

# Module logger
logger = logging.getLogger(__name__)

# Application shutdown policy:
# - UI layer does NOT directly call quit()/exit().
# - Shutdown is performed ONLY through AppShutdownController (perform_shutdown)
#   or indirectly through closing the main window (MainWindow.close()), which triggers the controller.
# - emergency_shutdown() function is exclusively for fatal emergency situations.


class ShutdownPriority(Enum):
    """Shutdown operation priorities."""

    CRITICAL = 1  # Сохранение данных, критичные операции
    HIGH = 2  # Остановка контроллеров
    NORMAL = 3  # Ожидание потоков
    LOW = 4  # Cleanup, бэкапы


class ShutdownTimeoutError(Exception):
    """Exception for shutdown operation timeouts."""

    pass


@runtime_checkable
class ShutdownCallable(Protocol):
    """Callable executed during shutdown."""

    def __call__(self, timeout_ms: int) -> bool: ...


def _normalize_shutdown_callable(handler: Callable, name: str) -> ShutdownCallable:
    """Wrap arbitrary callables into the shutdown protocol."""
    if isinstance(handler, ShutdownCallable):
        return handler

    sig = inspect.signature(handler)
    params = list(sig.parameters.values())
    if len(params) == 0:

        def wrapper(timeout_ms: int) -> bool:  # type: ignore[override]
            result = handler()  # type: ignore[misc]
            return bool(True if result is None else result)

        return wrapper

    if len(params) == 1:

        def wrapper(timeout_ms: int) -> bool:
            result = handler(timeout_ms)  # type: ignore[misc]
            return bool(True if result is None else result)

        return wrapper

    raise TypeError(f"Shutdown handler '{name}' must accept 0 or 1 arguments")


class ShutdownHandler:
    """Wrapper for shutdown operations with metadata."""

    def __init__(
        self,
        name: str,
        callback: ShutdownCallable,
        priority: ShutdownPriority,
        timeout: int | None = None,
        critical: bool = False,
    ):
        self.name = name
        self.callback = callback
        self.priority = priority
        self.timeout = timeout or app_config.get("shutdown.default_timeout", 2000)
        self.critical = critical  # If True, error will interrupt shutdown

    def run(self, timeout_ms: int) -> bool:
        result = self.callback(timeout_ms)
        return bool(True if result is None else result)


class AppShutdownController:
    """Enhanced application shutdown controller.

    ✅ FIX: Added strict typing and cleanup method.

    Features:
    - Operation priority support
    - Improved error handling with real timeouts
    - Configurable timeouts
    - Full backward compatibility with existing code
    - Safe shutdown in multithreaded environment
    """

    def __init__(self, main_window: "QMainWindow"):
        self.window = main_window
        self.shutdown_handlers: list[ShutdownHandler] = []
        self.shutdown_in_progress = False
        self._shutdown_lock: Optional[threading.RLock] = threading.RLock()
        self._shutdown_started_ts: float | None = None
        self._register_default_handlers()

        # Settings from configuration
        self.max_shutdown_time = app_config.get("shutdown.max_total_time", 10000)
        self.parallel_execution = app_config.get("shutdown.parallel_execution", False)

        # ✅ Flag for tracking cleanup
        self._cleaned_up = False

    def perform_shutdown(self, event: "QCloseEvent") -> None:
        """Main method - fully compatible with original interface.

        ✅ FIX: Added parameter typing.

            event: Window close event
        """
        if self._shutdown_lock is None:
            logger.error("Shutdown lock is None, cannot proceed safely")
            return
        
        with self._shutdown_lock:
            if self.shutdown_in_progress:
                logger.warning(
                    "Shutdown is already in progress, ignoring duplicate request"
                )
                return

            self.shutdown_in_progress = True
            self._shutdown_started_ts = time.monotonic()

        try:
            logger.info("Starting application shutdown sequence")
            self._execute_shutdown_sequence()
            logger.info("Application shutdown completed successfully")

        except Exception as exc:
            logger.error("Critical error during shutdown: %s", exc, exc_info=True)
        finally:
            # Safe call to parent closeEvent (backward compatibility)
            self._safe_close_event(event)
            # ✅ Resource cleanup
            self.cleanup()

    def _safe_close_event(self, event):
        """Safe call to parent closeEvent with fallback."""
        try:
            # Try to find parent class with closeEvent
            for base_class in self.window.__class__.__mro__[1:]:
                if hasattr(base_class, "closeEvent"):
                    base_class.closeEvent(self.window, event)
                    return

            # If not found, just accept the event
            event.accept()

        except Exception as exc:
            logger.error("Error in base closeEvent: %s", exc, exc_info=True)
            # In any case accept the event so the application can close
            try:
                event.accept()
            except Exception:
                pass

    def _execute_shutdown_sequence(self):
        """Execute shutdown operations sequence by priorities with global deadline consideration."""
        handlers_by_priority = self._group_handlers_by_priority()

        for priority in ShutdownPriority:
            if priority not in handlers_by_priority:
                continue

            # Check global deadline before priority level
            remaining = self._remaining_time_ms()
            if remaining is not None and remaining <= 0:
                logger.error(
                    "Global shutdown deadline exceeded before priority %s",
                    priority.name,
                )
                break

            handlers = handlers_by_priority[priority]
            logger.debug(
                "Executing shutdown priority %s with %s handlers (remaining ~%s ms)",
                priority.name,
                len(handlers),
                remaining,
            )

            try:
                if (
                    self.parallel_execution
                    and len(handlers) > 1
                    and priority != ShutdownPriority.CRITICAL
                ):
                    logger.warning(
                        "Parallel shutdown execution is deprecated; running sequentially for priority %s",
                        priority.name,
                    )
                self._execute_handlers_sequential(handlers, remaining_ms=remaining)
            except Exception as exc:
                logger.error(
                    "Error in priority %s: %s", priority.name, exc, exc_info=True
                )
                if priority == ShutdownPriority.CRITICAL:
                    raise

    def _group_handlers_by_priority(
        self,
    ) -> dict[ShutdownPriority, list[ShutdownHandler]]:
        """Group handlers by priorities."""
        groups: dict[ShutdownPriority, list[ShutdownHandler]] = {}
        for handler in self.shutdown_handlers:
            if handler.priority not in groups:
                groups[handler.priority] = []
            groups[handler.priority].append(handler)
        return groups

    def _execute_handlers_sequential(
        self, handlers: list[ShutdownHandler], remaining_ms: int | None = None
    ):
        """Sequential execution of handlers with global deadline consideration."""
        for handler in handlers:
            rem = self._remaining_time_ms() if remaining_ms is None else remaining_ms
            if rem is not None and rem <= 0:
                logger.error(
                    "Global shutdown deadline exceeded during sequential handlers"
                )
                break
            eff_timeout = (
                min(handler.timeout, rem) if rem is not None else handler.timeout
            )
            self._execute_single_handler(handler, override_timeout_ms=eff_timeout)

    def _execute_handlers_parallel(
        self, handlers: list[ShutdownHandler], remaining_ms: int | None = None
    ):
        """Deprecated parallel execution shim - falls back to sequential."""
        logger.warning(
            "Parallel handler execution is no longer supported; running sequentially"
        )
        self._execute_handlers_sequential(handlers, remaining_ms=remaining_ms)

    @contextmanager
    def _timeout_context(self, timeout_ms: int, handler_name: str):
        """Context manager for setting operation timeout."""
        timeout_seconds = timeout_ms / 1000.0
        timer = None
        timeout_occurred = False

        def timeout_handler():
            nonlocal timeout_occurred
            timeout_occurred = True

        # Use threading.Timer instead of signal (Windows and PyQt compatibility)
        timer = threading.Timer(timeout_seconds, timeout_handler)
        timer.start()

        try:
            yield
            if timeout_occurred:
                raise ShutdownTimeoutError(
                    f"Handler '{handler_name}' timed out after {timeout_seconds}s"
                )
        finally:
            if timer:
                timer.cancel()

    def _execute_single_handler(
        self, handler: ShutdownHandler, override_timeout_ms: int | None = None
    ):
        """Execute single handler with real timeout and extended logging.

        Execute handler in separate thread and wait for completion via Thread.join(timeout).
        In case of timeout — log and continue (or interrupt for critical) without creating ThreadPoolExecutor.
        """
        eff_timeout_ms = (
            override_timeout_ms if override_timeout_ms is not None else handler.timeout
        )
        eff_timeout_sec = (
            max(0.001, float(eff_timeout_ms) / 1000.0) if eff_timeout_ms else None
        )

        logger.debug(
            "Executing shutdown handler: %s (timeout=%sms, critical=%s)",
            handler.name,
            eff_timeout_ms,
            handler.critical,
        )

        err_holder: list[BaseException] = []
        result_holder: list[bool] = []

        def _runner():
            try:
                result_holder.append(handler.run(eff_timeout_ms or handler.timeout))
            except BaseException as e:  # noqa: BLE001
                err_holder.append(e)

        t = threading.Thread(
            name=f"shutdown:{handler.name}", target=_runner, daemon=True
        )

        try:
            t.start()
            if eff_timeout_sec is None:
                t.join()
            else:
                t.join(timeout=eff_timeout_sec)

            if t.is_alive():
                msg = f"Handler '{handler.name}' timed out after {eff_timeout_sec:.3f}s"
                if handler.critical:
                    logger.critical(msg)
                    raise ShutdownTimeoutError(msg)
                else:
                    logger.error(msg)
                    return

            if err_holder:
                exc = err_holder[0]
                if handler.critical:
                    logger.critical(
                        "Handler '%s' failed: %s", handler.name, exc, exc_info=True
                    )
                    raise exc
                else:
                    logger.error(
                        "Handler '%s' failed: %s", handler.name, exc, exc_info=True
                    )
                    return

            if result_holder and not result_holder[0]:
                msg = f"Handler '{handler.name}' reported failure"
                if handler.critical:
                    logger.critical(msg)
                    raise RuntimeError(msg)
                logger.error(msg)
                return

            logger.debug("Handler %s completed successfully", handler.name)
            return
        except ShutdownTimeoutError:
            # Уже залогировано выше, пробрасываем дальше для критичных кейсов
            raise
        except Exception as exc:
            # Непредвиденные ошибки инфраструктуры исполнения
            if handler.critical:
                logger.critical(
                    "Execution infrastructure failed for handler '%s': %s",
                    handler.name,
                    exc,
                    exc_info=True,
                )
                raise
            else:
                logger.error(
                    "Execution infrastructure failed for handler '%s': %s",
                    handler.name,
                    exc,
                    exc_info=True,
                )
                return

    def _register_default_handlers(self):
        """Register default handlers (compatibility with original code)."""
        # Order as before: controllers -> wait threads -> backup
        # 1) Controller shutdown (strict, critical)
        self.add_shutdown_handler(
            "controllers_shutdown",
            self._shutdown_controllers,
            ShutdownPriority.HIGH,
            timeout=3000,
            critical=True,
        )
        # 2) Thread pool waiting (strict, critical)
        # Align handler timeout with ui.thread_pool_shutdown_timeout config, adding buffer
        tp_timeout = app_config.ui.get_thread_pool_shutdown_timeout()
        handler_timeout = max(
            tp_timeout + 1000, 3000
        )  # small buffer to avoid false timeouts
        self.add_shutdown_handler(
            "thread_pools_wait",
            self._wait_for_thread_pools,
            ShutdownPriority.NORMAL,
            timeout=handler_timeout,
            critical=True,
        )
        # 3) Database backup (non-critical, last)
        self.add_shutdown_handler(
            "database_backup",
            self._backup_database,
            ShutdownPriority.LOW,
            timeout=5000,
            critical=False,
        )

    def _remaining_time_ms(self) -> int | None:
        """How many milliseconds remain until global deadline. None — if deadline not set."""
        if not self.max_shutdown_time:
            return None
        if self._shutdown_started_ts is None:
            return self.max_shutdown_time
        elapsed_ms = int((time.monotonic() - self._shutdown_started_ts) * 1000)
        remaining = self.max_shutdown_time - elapsed_ms
        return max(0, remaining)

    def add_shutdown_handler(
        self,
        name: str,
        handler: Callable,
        priority: ShutdownPriority = ShutdownPriority.NORMAL,
        timeout: Optional[int] = None,
        critical: bool = False,
    ):
        """Add custom shutdown handler."""
        self.remove_shutdown_handler(name)
        normalized = _normalize_shutdown_callable(handler, name)
        shutdown_handler = ShutdownHandler(
            name, normalized, priority, timeout, critical
        )
        self.shutdown_handlers.append(shutdown_handler)
        logger.debug(
            "Registered shutdown handler: %s (priority: %s)", name, priority.name
        )

    def remove_shutdown_handler(self, name: str) -> bool:
        """Remove shutdown handler by name. Returns True if handler was found and removed."""
        initial_count = len(self.shutdown_handlers)
        self.shutdown_handlers = [h for h in self.shutdown_handlers if h.name != name]
        removed = len(self.shutdown_handlers) < initial_count
        if removed:
            logger.debug("Removed shutdown handler: %s", name)
        return removed

    def get_shutdown_handlers(self) -> list[dict[str, Any]]:
        """Get information about all registered handlers (for debugging)."""
        return [
            {
                "name": h.name,
                "priority": h.priority.name,
                "timeout": h.timeout,
                "critical": h.critical,
            }
            for h in self.shutdown_handlers
        ]

    # =================== ORIGINAL METHODS (refactoring) ===================

    def _shutdown_controllers(self, timeout_ms: int) -> bool:
        """Stop background controllers - improved version of original."""
        controllers_to_shutdown = [
            ("links", "Links controller"),
            ("links_business", "Links business controller"),
            ("tiles", "Tiles controller"),
        ]

        for attr_name, display_name in controllers_to_shutdown:
            try:
                if not hasattr(self.window, attr_name):
                    logger.debug("%s not found on window object", display_name)
                    continue

                controller = getattr(self.window, attr_name)
                if controller is None:
                    logger.debug("%s is None", display_name)
                    continue

                if not hasattr(controller, "shutdown"):
                    logger.debug("%s has no shutdown method", display_name)
                    continue

                logger.debug("Shutting down %s", display_name)
                shutdown_method = controller.shutdown
                if callable(shutdown_method):
                    shutdown_method()
                else:
                    logger.warning("%s.shutdown is not callable", display_name)

            except Exception as exc:
                logger.error(
                    "Error shutting down %s: %s", display_name, exc, exc_info=True
                )
        return True

    def _wait_for_thread_pools(self, timeout_ms: int) -> bool:
        """Wait for thread completion - improved version of original."""
        timeout = app_config.ui.get_thread_pool_shutdown_timeout()

        # Global thread pool
        try:
            pool = QThreadPool.globalInstance()
            if pool and pool.activeThreadCount() > 0:
                logger.debug(
                    "Waiting for %s global threads to finish",
                    pool.activeThreadCount(),
                )
                if not pool.waitForDone(timeout):
                    logger.warning(
                        "Global thread pool did not finish within timeout, forcing cleanup"
                    )
                    # Пытаемся форсированно завершить
                    try:
                        pool.clear()
                    except Exception as clear_exc:
                        logger.error("Error clearing global thread pool: %s", clear_exc)
        except Exception as exc:
            logger.error("Error waiting for global thread pool: %s", exc, exc_info=True)

        # Локальный thread pool окна
        try:
            if hasattr(self.window, "thread_pool"):
                local_pool = self.window.thread_pool
                if local_pool and local_pool.activeThreadCount() > 0:
                    logger.debug(
                        "Waiting for %s local threads to finish",
                        local_pool.activeThreadCount(),
                    )
                    if not local_pool.waitForDone(timeout):
                        logger.warning(
                            "Local thread pool did not finish within timeout, forcing cleanup"
                        )
                        try:
                            local_pool.clear()
                        except Exception as clear_exc:
                            logger.error(
                                "Error clearing local thread pool: %s",
                                clear_exc,
                            )
        except Exception as exc:
            logger.error("Error waiting for local thread pool: %s", exc, exc_info=True)
        return True

    def _backup_database(self, timeout_ms: int) -> bool:
        """Create database backup - improved version of original."""
        try:
            if not hasattr(self.window, "db"):
                logger.debug("No 'db' attribute found on window, skipping backup")
                return True

            db = self.window.db
            if db is None:
                logger.debug("Database instance is None, skipping backup")
                return True

            if not hasattr(db, "backup"):
                logger.debug("Database has no backup method")
                return True

            backup_method = db.backup
            if not callable(backup_method):
                logger.debug("Database backup attribute is not callable")
                return True

            logger.info("Creating database backup...")
            backup_method()
            logger.info("Database backup completed successfully")

        except Exception as exc:
            # Backup error is not critical, but we log it
            logger.error("Database backup failed: %s", exc, exc_info=True)
            return False
        return True

    def cleanup(self) -> None:
        """Release controller resources.

        ✅ FIX: Added cleanup method to prevent memory leaks.

        Called automatically after shutdown sequence completion.
        Idempotent - can be called multiple times.
        """
        if self._cleaned_up:
            return

        try:
            # Release RLock
            if hasattr(self, "_shutdown_lock") and self._shutdown_lock:
                try:
                    # RLock doesn't require explicit release, but we clear the reference
                    self._shutdown_lock = None
                except Exception as e:
                    logger.debug("Error clearing shutdown lock: %s", e)

            # Clear handlers
            if hasattr(self, "shutdown_handlers"):
                self.shutdown_handlers.clear()

            self._cleaned_up = True
            logger.debug("AppShutdownController cleanup completed")

        except Exception as exc:
            logger.error(
                "Error during AppShutdownController cleanup: %s", exc, exc_info=True
            )


# ===================== HELPER FUNCTIONS =====================


def create_shutdown_controller(main_window: "QMainWindow") -> AppShutdownController:
    """Factory function to create controller with default settings.

    ✅ FIX: Added parameter typing.

    Args:
        main_window: Application main window

    Returns:
        Configured AppShutdownController instance
    """
    controller = AppShutdownController(main_window)

    # Additional handlers can be added here
    # controller.add_shutdown_handler("custom_cleanup", custom_cleanup_function, ShutdownPriority.LOW)

    return controller


def emergency_shutdown():
    """Emergency application shutdown in case of critical errors."""
    logger.critical("Emergency shutdown initiated")
    try:
        app = QApplication.instance()
        if app:
            app.quit()
        else:
            sys.exit(1)
    except Exception as exc:
        logger.critical("Error during emergency shutdown: %s", exc)
        sys.exit(1)
