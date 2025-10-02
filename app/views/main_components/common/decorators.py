"""Decorators for main_components package.

УЛУЧШЕНИЕ: Утилиты для упрощения типичных паттернов:
- Thread safety checks
- Logging guards
- Error handling
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar, cast

from .exceptions import ThreadSafetyError

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


def require_main_thread(func: F) -> F:
    """Decorator to ensure method is called from main Qt thread.
    
    ИСПРАВЛЕНИЕ: Добавляет thread safety проверку для методов,
    которые должны выполняться только в main thread.
    
    Usage:
        @require_main_thread
        def adjust(self) -> None:
            # Will raise ThreadSafetyError if called from worker thread
            ...
    
    Raises:
        ThreadSafetyError: If called from non-main thread
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            from PyQt6.QtCore import QThread
            from PyQt6.QtWidgets import QApplication
            
            app = QApplication.instance()
            if app is not None:
                current_thread = QThread.currentThread()
                main_thread = app.thread()
                
                if current_thread != main_thread:
                    thread_name = getattr(current_thread, 'objectName', lambda: 'unknown')()
                    raise ThreadSafetyError(
                        method_name=func.__name__,
                        current_thread=thread_name or str(current_thread),
                        required_thread="main"
                    )
        except (ImportError, AttributeError):
            # If we can't check, allow it (for testing/compatibility)
            pass
        
        return func(*args, **kwargs)
    
    return cast(F, wrapper)


def log_if_enabled(level: int = logging.DEBUG):
    """Decorator to add logging guard for expensive string formatting.
    
    УЛУЧШЕНИЕ: Добавляет проверку уровня логирования перед
    выполнением дорогих операций форматирования.
    
    Usage:
        @log_if_enabled(logging.DEBUG)
        def some_method(self):
            logger.debug("Expensive: %s", self._expensive_operation())
            # expensive_operation() won't be called if DEBUG is disabled
    
    Args:
        level: Logging level to check (default: DEBUG)
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get logger from module
            func_logger = logging.getLogger(func.__module__)
            
            if not func_logger.isEnabledFor(level):
                return None
            
            return func(*args, **kwargs)
        
        return cast(F, wrapper)
    
    return decorator


def safe_qt_operation(default_return: Any = None):
    """Decorator to safely handle deleted Qt objects.
    
    УЛУЧШЕНИЕ: Автоматически обрабатывает RuntimeError от deleted Qt objects.
    
    Usage:
        @safe_qt_operation(default_return=0)
        def get_width(self, widget: QWidget) -> int:
            return widget.width()  # Safe even if widget is deleted
    
    Args:
        default_return: Value to return if operation fails
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                # Check for deleted objects in args
                try:
                    from sip import isdeleted
                    for arg in args:
                        if hasattr(arg, '__class__') and isdeleted(arg):
                            logger.debug(
                                "%s: skipping operation on deleted Qt object",
                                func.__name__
                            )
                            return default_return
                except ImportError:
                    pass
                
                return func(*args, **kwargs)
                
            except RuntimeError as e:
                # Qt object was deleted during operation
                if "wrapped C/C++ object" in str(e) or "deleted" in str(e).lower():
                    logger.debug(
                        "%s: Qt object deleted during operation: %s",
                        func.__name__,
                        e
                    )
                    return default_return
                raise
            except AttributeError as e:
                # Object doesn't have expected attribute (possibly deleted)
                logger.debug(
                    "%s: AttributeError (possibly deleted object): %s",
                    func.__name__,
                    e
                )
                return default_return
        
        return cast(F, wrapper)
    
    return decorator


def retry_on_failure(max_attempts: int = 3, exceptions: tuple = (Exception,)):
    """Decorator to retry function on failure.
    
    УЛУЧШЕНИЕ: Автоматически повторяет операцию при временных сбоях.
    
    Usage:
        @retry_on_failure(max_attempts=3, exceptions=(RuntimeError,))
        def flaky_operation(self):
            # Will retry up to 3 times on RuntimeError
            ...
    
    Args:
        max_attempts: Maximum number of attempts
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.debug(
                            "%s: attempt %d/%d failed: %s, retrying...",
                            func.__name__,
                            attempt + 1,
                            max_attempts,
                            e
                        )
                    else:
                        logger.warning(
                            "%s: all %d attempts failed",
                            func.__name__,
                            max_attempts
                        )
            
            # All attempts failed
            if last_exception:
                raise last_exception
            
            return None
        
        return cast(F, wrapper)
    
    return decorator
