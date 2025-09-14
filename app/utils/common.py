"""
Общие утилиты, используемые по всему приложению.
"""

from typing import Any, Callable, TypeVar

T = TypeVar("T")


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    """Безопасно извлекает значение по ключу/атрибуту из объекта.

    Поддерживает:
    - словареподобные объекты (имеющие метод .get)
    - обычные объекты (через getattr)

    Args:
        obj: источник данных (словарь, dataclass, объект и т.п.)
        key: ключ/имя атрибута
        default: значение по умолчанию, если ключ/атрибут отсутствует

    Returns:
        Значение по ключу/атрибуту или default
    """
    try:
        if hasattr(obj, "get"):
            # у словареподобных объектов безопасно вызываем get
            return obj.get(key, default)
        return getattr(obj, key, default)
    except Exception:
        return default


def safe_getattr(obj: Any, attr: str, default: T | None = None) -> T | None:
    """Безопасно получить атрибут у объекта, возвращая default при ошибке.

    Обрабатывает AttributeError/TypeError и любые неожиданные исключения,
    чтобы не ронять UI‑код при обращении к заглушкам/тестовым объектам.
    """
    try:
        return getattr(obj, attr) if obj is not None else default
    except (AttributeError, TypeError):
        return default
    except Exception:
        return default


def safe_call(
    obj: Any,
    method_name: str,
    *args: Any,
    default: T | None = None,
    **kwargs: Any,
) -> T | None:
    """Безопасно вызвать метод объекта по имени.

    Если метода нет или он выбросил ожидаемые ошибки, возвращает default.
    Непредвиденные исключения проглатываются для защиты UI‑потока.
    """
    try:
        method = getattr(obj, method_name, None)
        if method and callable(method):
            result = method(*args, **kwargs)
            return result if result is not None else default
    except (AttributeError, TypeError):
        return default
    except Exception:
        return default
    return default
