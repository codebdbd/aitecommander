# app/controllers/structure_modules/exceptions.py
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable


def handle_exceptions(default_return=None):
    """Decorator for handling exceptions in methods.

    Expects self to have logger attribute and _emit_error(title, message) method.
    """

    def decorator(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:  # noqa: BLE001
                logger: logging.Logger | None = getattr(self, "logger", None)
                if logger:
                    logger.error("Error in %s: %s", func.__name__, e, exc_info=True)
                # UI message if method is available
                emit_error = getattr(self, "_emit_error", None)
                if callable(emit_error):
                    emit_error(f"Error in {func.__name__}", str(e))
                return default_return

        return wrapper

    return decorator
