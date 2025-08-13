from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import Qt


def get_tree_tuple(item, column: int = 0) -> Optional[Tuple[str, int]]:
    """Безопасно читает UserRole из QTreeWidgetItem в колонке column и возвращает (type, id).
    Возвращает None, если структура некорректна.
    """
    try:
        data = item.data(column, Qt.ItemDataRole.UserRole)
        if isinstance(data, (tuple, list)) and len(data) == 2:
            type_val, id_val = data
            if isinstance(type_val, str) and isinstance(id_val, int):
                return type_val, id_val
        return None
    except Exception:
        return None


def get_item_int(item) -> Optional[int]:
    """Читает UserRole из QListWidgetItem/QTableWidgetItem и приводит к int. Возвращает None при неудаче."""
    try:
        val = item.data(Qt.ItemDataRole.UserRole)
        if val is None:
            return None
        return int(val)
    except Exception:
        return None


def set_item_int(item, value: int) -> None:
    """Устанавливает целочисленное значение в UserRole для QListWidgetItem/QTableWidgetItem."""
    item.setData(Qt.ItemDataRole.UserRole, int(value))


def get_item_dict(item) -> Optional[Dict[str, Any]]:
    """Читает словарь из UserRole. Возвращает None, если не dict."""
    try:
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def set_item_dict(item, value: Dict[str, Any]) -> None:
    """Устанавливает словарь в UserRole."""
    item.setData(Qt.ItemDataRole.UserRole, value)
