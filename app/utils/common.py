"""
Общие утилиты, используемые по всему приложению.

Изменения:
- Сужена зона перехвата исключений до ожидаемых (AttributeError, TypeError) в
  стандартных сценариях.
- Неожиданные исключения логируются на уровне DEBUG с полным стек‑трейсом,
  после чего возвращается значение по умолчанию.
- Аннотации типов возвращают Optional, отражая возможность возврата default.
"""

import logging
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_value(obj: Any, key: str, default: T | None = None) -> T | None:
    """Безопасно извлекает значение по ключу/атрибуту из объекта.

    Поддерживает:
    - словареподобные объекты (имеющие метод ``.get``)
    - обычные объекты (через ``getattr``)

    Поведение при ошибках:
    - Ожидаемые ошибки (AttributeError, TypeError) приводят к возврату ``default`` без
      логирования.
    - Неожиданные исключения логируются на уровне DEBUG с полным стек‑трейсом и
      затем возвращается ``default``.

    Args:
        obj: источник данных (словарь, dataclass, объект и т.п.)
        key: ключ/имя атрибута
        default: значение по умолчанию, если ключ/атрибут отсутствует

    Returns:
        Значение по ключу/атрибуту или ``default``.
    """
    try:
        if hasattr(obj, "get"):
            return obj.get(key, default)  # type: ignore[attr-defined]
        return getattr(obj, key, default)
    except (AttributeError, TypeError):
        return default
    except Exception as exc:  # неожиданные исключения
        logger.debug(
            "get_value: unexpected exception while accessing key %r on %r: %s",
            key,
            obj,
            exc,
            exc_info=True,
        )
        return default


def safe_getattr(obj: Any, attr: str, default: T | None = None) -> T | None:
    """Безопасно получить атрибут у объекта.

    Поведение при ошибках:
    - При ``AttributeError`` или ``TypeError`` возвращается ``default`` без логирования.
    - Неожиданные исключения логируются на уровне DEBUG (с ``exc_info``) и
      возвращается ``default``.
    """
    try:
        return getattr(obj, attr) if obj is not None else default
    except (AttributeError, TypeError):
        return default
    except Exception as exc:
        logger.debug(
            "safe_getattr: unexpected exception while getting %r from %r: %s",
            attr,
            obj,
            exc,
            exc_info=True,
        )
        return default


def safe_call(
    obj: Any,
    method_name: str,
    *args: Any,
    default: T | None = None,
    **kwargs: Any,
) -> T | None:
    """Безопасно вызвать метод объекта по имени.

    Поведение:
    - Если метода нет или он не вызываем, возвращается ``default``.
    - Ожидаемые ошибки (AttributeError, TypeError) приводят к возврату ``default`` без
      логирования.
    - Неожиданные исключения логируются на уровне DEBUG с полным стек‑трейсом и
      затем возвращается ``default``.
    """
    try:
        method = getattr(obj, method_name, None)
        if method and callable(method):
            result = method(*args, **kwargs)
            return result if result is not None else default
    except (AttributeError, TypeError):
        return default
    except Exception as exc:
        logger.debug(
            "safe_call: unexpected exception while calling %r on %r: %s",
            method_name,
            obj,
            exc,
            exc_info=True,
        )
        return default
    return default
