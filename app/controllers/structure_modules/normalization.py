# app/controllers/structure_modules/normalization.py

"""Модуль для нормализации данных из базы данных."""

import logging
import warnings
from typing import Any, Dict, List, Protocol, Union, runtime_checkable

# Модульный логгер
logger = logging.getLogger(__name__)


@runtime_checkable
class RowLike(Protocol):
    """Протокол для объектов, похожих на строки БД."""

    def keys(self) -> Any:
        """Возвращает ключи объекта."""
        ...


# Типы данных, которые модуль может обрабатывать
SupportedRowType = Union[Dict[str, Any], RowLike, tuple, None]


def normalize_row(row: Any, logger: logging.Logger = None) -> Dict[str, Any]:
    """Безопасно нормализует строку БД в словарь.

    Поддерживает:
    - sqlite3.Row
    - namedtuple
    - dict
    - любые объекты с методом keys()

    Args:
        row: Строка данных из БД
        logger: Логгер для предупреждений

    Returns:
        Dict[str, Any]: Нормализованный словарь
    """
    active_logger = logger or logging.getLogger(__name__)

    if row is None:
        return {}

    # Уже словарь
    if isinstance(row, dict):
        return row.copy()  # Возвращаем копию для безопасности

    # Проверка на namedtuple (более надежный способ)
    if isinstance(row, tuple) and hasattr(row, "_fields"):
        try:
            return row._asdict()
        except AttributeError as e:
            active_logger.warning(f"Ошибка при вызове _asdict() для namedtuple: {e}")
            # Fallback к ручному созданию словаря
            try:
                return dict(zip(row._fields, row))
            except (AttributeError, TypeError) as fallback_e:
                active_logger.error(f"Не удалось обработать namedtuple: {fallback_e}")
                return {}

    # sqlite3.Row или другие объекты с keys() и поддержкой итерации
    if hasattr(row, "keys"):
        try:
            # Проверяем, что keys() действительно возвращает итерируемый объект
            keys = row.keys()
            if hasattr(keys, "__iter__"):
                return dict(row)
            else:
                active_logger.warning(
                    f"Метод keys() объекта {type(row)} не возвращает итерируемый объект"
                )
                return {}
        except (TypeError, ValueError, AttributeError) as e:
            active_logger.warning(
                f"Ошибка при обращении к keys() объекта {type(row)}: {e}"
            )

    # Проверяем, является ли объект итерируемым парами ключ-значение
    try:
        # Пытаемся преобразовать напрямую
        result = dict(row)
        if result:  # Проверяем, что получили непустой словарь
            return result
    except (TypeError, ValueError, AttributeError):
        pass  # Продолжаем к следующей попытке

    # Последняя попытка - если объект поддерживает протокол mapping
    if hasattr(row, "__getitem__") and hasattr(row, "keys"):
        try:
            return {key: row[key] for key in row.keys()}
        except (KeyError, TypeError, AttributeError) as e:
            active_logger.warning(
                f"Ошибка при ручном создании словаря из объекта {type(row)}: {e}"
            )

    # Если ничего не сработало
    active_logger.error(
        f"Не удалось нормализовать объект типа {type(row).__name__}. "
        "Поддерживаемые типы: dict, namedtuple, sqlite3.Row, объекты с методом keys()"
    )
    return {}


def normalize_rows(rows: Any, logger: logging.Logger = None) -> List[Dict[str, Any]]:
    """Нормализует список строк БД в список словарей.

    Args:
        rows: Список строк БД, одиночная строка или None
        logger: Логгер для предупреждений

    Returns:
        List[Dict[str, Any]]: Нормализованный список словарей
    """
    active_logger = logger or logging.getLogger(__name__)

    if rows is None:
        return []

    # Если передана одиночная строка, оборачиваем в список
    if not isinstance(rows, (list, tuple)):
        rows = [rows]

    result = []
    for i, row in enumerate(rows):
        try:
            normalized = normalize_row(row, active_logger)
            result.append(normalized)
        except Exception as e:
            active_logger.error(f"Ошибка при нормализации строки #{i}: {e}")
            result.append({})  # Добавляем пустой словарь, чтобы сохранить индексы

    return result


def row_to_dict(row: Any, logger: logging.Logger = None) -> Dict[str, Any]:
    """Устаревший метод - используйте normalize_row().

    Args:
        row: Строка данных из БД
        logger: Логгер для предупреждений

    Returns:
        Dict[str, Any]: Нормализованный словарь

    Deprecated:
        Используйте normalize_row() вместо этого метода.
    """
    warnings.warn(
        "row_to_dict() устарел. Используйте normalize_row()",
        DeprecationWarning,
        stacklevel=2,
    )
    return normalize_row(row, logger)


def validate_normalized_data(
    data: Union[Dict[str, Any], List[Dict[str, Any]]], required_keys: List[str] = None
) -> bool:
    """Валидирует нормализованные данные.

    Args:
        data: Нормализованные данные (словарь или список словарей)
        required_keys: Список обязательных ключей для проверки

    Returns:
        bool: True если данные валидны, False иначе
    """
    if required_keys is None:
        required_keys = []

    def _validate_dict(d: Dict[str, Any]) -> bool:
        if not isinstance(d, dict):
            return False
        return all(key in d for key in required_keys)

    if isinstance(data, dict):
        return _validate_dict(data)
    elif isinstance(data, list):
        return all(isinstance(item, dict) and _validate_dict(item) for item in data)

    return False


# Для обратной совместимости - экспортируем старые имена
__all__ = [
    "normalize_row",
    "normalize_rows",
    "row_to_dict",
    "validate_normalized_data",
    "SupportedRowType",
    "RowLike",
]
