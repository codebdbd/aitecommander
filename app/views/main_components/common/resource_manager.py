"""Centralized resource manager that ensures safe cleanup.

Improvement note: `ResourceManager` governs resource lifecycles and guarantees
cleanup. It replaces fragile ``__del__`` implementations and prevents memory
leaks.
"""

from __future__ import annotations

import logging
import weakref
from contextlib import contextmanager
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ResourceManager:
    """Manager that centralizes resource cleanup.

    Improvement note: uses ``weakref.finalize()`` instead of ``__del__`` for
    reliable cleanup. Supports context-manager semantics for automatic cleanup
    when leaving scope.

    Example:
        >>> manager = ResourceManager()
        >>> timer = QTimer()
        >>> manager.register_resource(timer, timer.stop, "main_timer")
        >>> # ... use resources
        >>> manager.cleanup_all()  # Clean up all resources

        >>> # Or with the context manager
        >>> with ResourceManager() as manager:
        ...     timer = QTimer()
        ...     manager.register_resource(timer, timer.stop)
        ...     # Automatic cleanup on exit
    """

    def __init__(self, name: str = "ResourceManager") -> None:
        """Initialize the resource manager.

        Args:
            name: Manager identifier used for logging.
        """
        self._name = name
        self._resources: List[Tuple[str, Callable[[], None], Optional[weakref.finalize]]] = []
        self._cleaned_up = False
        self._cleanup_errors: List[Tuple[str, Exception]] = []

    def register_resource(
        self,
        resource: Any,
        cleanup_func: Optional[Callable[[], None]] = None,
        name: str = "",
        use_finalize: bool = True,
    ) -> None:
        """Register a resource for automatic cleanup.

        Improvement note: automatically detects cleanup methods for Qt objects.

        Args:
            resource: Resource object (used for ``weakref`` binding).
            cleanup_func: Cleanup callable; auto-detected when ``None``.
            name: Human-readable name for logging.
            use_finalize: Whether to create a ``weakref.finalize`` helper.

        Example:
            >>> # Automatic cleanup detection
            >>> manager.register_resource(QTimer())  # Calls stop()
            >>> manager.register_resource(QWidget())  # Calls deleteLater()
        """
        if self._cleaned_up:
            logger.warning(
                "%s: attempted to register resource '%s' after cleanup",
                self._name,
                name or "unnamed",
            )
            return

        # Improvement: auto-detect cleanup function for Qt objects
        if cleanup_func is None:
            cleanup_func = self._auto_detect_cleanup(resource)
            if cleanup_func is None:
                logger.warning(
                    "%s: cannot auto-detect cleanup for %s, skipping",
                    self._name,
                    type(resource).__name__
                )
                return

        resource_name = name or f"{type(resource).__name__}@{id(resource)}"
        
        finalizer = None
        if use_finalize:
            try:
                # weakref.finalize invokes cleanup_func once the resource is deleted
                finalizer = weakref.finalize(resource, self._safe_cleanup, cleanup_func, resource_name)
                logger.debug("%s: registered resource '%s' with finalize", self._name, resource_name)
            except TypeError as e:
                logger.debug(
                    "%s: cannot create finalize for '%s': %s (will use manual cleanup)",
                    self._name,
                    resource_name,
                    e,
                )

        self._resources.append((resource_name, cleanup_func, finalizer))
    
    def _auto_detect_cleanup(self, resource: Any) -> Optional[Callable[[], None]]:
        """Automatically detect a cleanup method for the resource.

        Improvement note: makes the API simpler—no need to supply ``cleanup_func``
        for typical Qt objects.
        """
        # QTimer -> stop()
        if hasattr(resource, 'stop') and callable(getattr(resource, 'stop')):
            return resource.stop
        
        # QWidget, QObject -> deleteLater()
        if hasattr(resource, 'deleteLater') and callable(getattr(resource, 'deleteLater')):
            return resource.deleteLater
        
        # File-like -> close()
        if hasattr(resource, 'close') and callable(getattr(resource, 'close')):
            return resource.close
        
        return None

    def _safe_cleanup(self, cleanup_func: Callable[[], None], resource_name: str) -> None:
        """Invoke the cleanup function with error handling.

        Args:
            cleanup_func: Cleanup callable.
            resource_name: Resource name used for logging.
        """
        try:
            cleanup_func()
            logger.debug("%s: cleaned up resource '%s'", self._name, resource_name)
        except Exception as e:
            logger.warning(
                "%s: error cleaning up resource '%s': %s",
                self._name,
                resource_name,
                e,
                exc_info=True,
            )
            self._cleanup_errors.append((resource_name, e))

    def cleanup_all(self) -> None:
        """Clean up every registered resource.

        Improvement note: guarantees cleanup invocations even when errors occur
        and records them for diagnostics.
        """
        if self._cleaned_up:
            logger.debug("%s: cleanup_all called multiple times, ignoring", self._name)
            return

        logger.debug("%s: starting cleanup of %d resources", self._name, len(self._resources))
        self._cleaned_up = True
        self._cleanup_errors.clear()

        # Clean resources in reverse registration order (LIFO)
        for resource_name, cleanup_func, finalizer in reversed(self._resources):
            # Detach finalize because cleanup is performed manually now
            if finalizer is not None:
                try:
                    finalizer.detach()
                except Exception:
                    pass  # Ignore detach errors

            self._safe_cleanup(cleanup_func, resource_name)

        self._resources.clear()

        if self._cleanup_errors:
            logger.warning(
                "%s: cleanup completed with %d errors",
                self._name,
                len(self._cleanup_errors),
            )
        else:
            logger.info("%s: cleanup completed successfully", self._name)

    def is_cleaned_up(self) -> bool:
        """Return whether cleanup has already been executed.

        Returns:
            ``True`` if ``cleanup_all()`` has been called.
        """
        return self._cleaned_up

    def get_cleanup_errors(self) -> List[Tuple[str, Exception]]:
        """Return the list of cleanup errors encountered.

        Returns:
            List of ``(resource_name, exception)`` tuples.
        """
        return self._cleanup_errors.copy()

    def __enter__(self) -> ResourceManager:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit that performs automatic cleanup."""
        self.cleanup_all()

    def __del__(self) -> None:
        """Destructor that performs cleanup when it was not invoked explicitly."""
        if not self._cleaned_up:
            logger.debug("%s: cleanup_all not called explicitly, cleaning up in __del__", self._name)
            try:
                self.cleanup_all()
            except Exception:
                # Ignore destructor failures; cleanup is best-effort here
                pass


@contextmanager
def managed_resource(
    resource: Any,
    cleanup_func: Callable[[], None],
    name: str = "",
):
    """Context manager for a single resource.

    Improvement note: provides a lightweight API for managing one resource.

    Example:
        >>> timer = QTimer()
        >>> with managed_resource(timer, timer.stop, "my_timer"):
        ...     timer.start(1000)
        ...     # ... use the timer
        ... # Automatically invokes timer.stop()
    """
    manager = ResourceManager(name=name or "managed_resource")
    manager.register_resource(resource, cleanup_func, name, use_finalize=False)
    try:
        yield resource
    finally:
        manager.cleanup_all()
