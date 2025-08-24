# app/controllers/structure_modules/exceptions.py
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Optional


def handle_exceptions(default_return=None):
    """Декоратор для обработки исключений в методах.

    Ожидает, что у self есть атрибуты logger и метод _emit_error(title, message).
    """

    def decorator(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:  # noqa: BLE001
                logger: Optional[logging.Logger] = getattr(self, "logger", None)
                if logger:
                    logger.error(f"Ошибка в {func.__name__}: {e}", exc_info=True)
                # Сообщение в UI, если метод доступен
                emit_error = getattr(self, "_emit_error", None)
                if callable(emit_error):
                    emit_error(f"Ошибка в {func.__name__}", str(e))
                return default_return

        return wrapper

    return decorator
