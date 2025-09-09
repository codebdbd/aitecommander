"""
Общие утилиты, используемые по всему приложению.
"""

from typing import Any


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
            return obj.get(key, default)  # type: ignore[attr-defined]
        return getattr(obj, key, default)
    except Exception:
        return default
