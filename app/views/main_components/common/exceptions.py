"""Custom exceptions for the `main_components` package.

Improvement note: concrete exception types replace generic RuntimeError/ValueError
to improve diagnostics and error handling.
"""

from __future__ import annotations


class MainComponentsError(Exception):
    """Base exception for all main_components errors."""

    pass


class InitializationError(MainComponentsError):
    """Raised when component initialization fails."""

    pass


class DatabaseNotReadyError(InitializationError):
    """Raised when database is not ready after timeout."""

    def __init__(self, timeout_seconds: float, attempts: int):
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts
        super().__init__(
            f"Database not ready after {timeout_seconds:.2f}s ({attempts} attempts)"
        )


class ResourceCleanupError(MainComponentsError):
    """Raised when resource cleanup fails."""

    def __init__(self, resource_name: str, original_error: Exception):
        self.resource_name = resource_name
        self.original_error = original_error
        super().__init__(
            f"Failed to cleanup resource '{resource_name}': {original_error}"
        )


class ThreadSafetyError(MainComponentsError):
    """Raised when method is called from wrong thread."""

    def __init__(
        self, method_name: str, current_thread: str, required_thread: str = "main"
    ):
        self.method_name = method_name
        self.current_thread = current_thread
        self.required_thread = required_thread
        super().__init__(
            f"Method '{method_name}' must be called from {required_thread} thread, "
            f"but was called from '{current_thread}'"
        )


class LayoutCalculationError(MainComponentsError):
    """Raised when layout calculation fails."""

    pass


class WidgetDeletedError(MainComponentsError):
    """Raised when attempting to operate on deleted Qt widget."""

    def __init__(self, widget_type: str, operation: str):
        self.widget_type = widget_type
        self.operation = operation
        super().__init__(
            f"Cannot perform '{operation}' on deleted {widget_type} widget"
        )


class ConfigurationError(MainComponentsError):
    """Raised when configuration is invalid."""

    def __init__(self, config_key: str, reason: str):
        self.config_key = config_key
        self.reason = reason
        super().__init__(f"Invalid configuration for '{config_key}': {reason}")
