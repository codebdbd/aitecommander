# app/controllers/structure_modules/normalization.py

"""Модуль для нормализации данных из базы данных."""

import logging
from typing import Any, Dict, List


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
    if row is None:
        return {}
    
    # Уже словарь
    if isinstance(row, dict):
        return row
    
    # namedtuple (имеет _asdict)
    if hasattr(row, '_asdict'):
        return row._asdict()
    
    # sqlite3.Row или другие объекты с keys()
    if hasattr(row, 'keys'):
        return dict(row)
    
    # Fallback для неожиданных типов
    try:
        return dict(row)
    except (TypeError, ValueError):
        if logger:
            logger.warning(f"Не удалось нормализовать объект типа {type(row)}: {row}")
        return {}


def normalize_rows(rows: Any, logger: logging.Logger = None) -> List[Dict[str, Any]]:
    """Нормализует список строк БД в список словарей.
    
    Args:
        rows: Список строк БД или одиночная строка
        logger: Логгер для предупреждений
        
    Returns:
        List[Dict[str, Any]]: Нормализованный список словарей
    """
    if rows is None:
        return []
    
    # Если передана одиночная строка, оборачиваем в список
    if not isinstance(rows, (list, tuple)):
        rows = [rows]
    
    return [normalize_row(row, logger) for row in rows]


def row_to_dict(row: Any, logger: logging.Logger = None) -> Dict[str, Any]:
    """Устаревший метод - используйте normalize_row()."""
    return normalize_row(row, logger)
