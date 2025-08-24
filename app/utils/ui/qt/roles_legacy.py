"""
Legacy helpers for QListWidgetItem/QTableWidgetItem.
[DEPRECATED] Сохранены для обратной совместимости с плитками/старым кодом.
Новые реализации должны использовать индексно-модельные аналоги из roles.py
(QTableView + QModelIndex + model.setData/data).
"""
from typing import Any, Dict, Optional

from PyQt6.QtCore import Qt


def get_item_int(item) -> Optional[int]:
    """[DEPRECATED] Читает UserRole из QListWidgetItem/QTableWidgetItem и приводит к int.
    Возвращает None при неудаче.
    """
    try:
        val = item.data(Qt.ItemDataRole.UserRole)
        if val is None:
            return None
        return int(val)
    except Exception:
        return None


def set_item_int(item, value: int) -> None:
    """[DEPRECATED] Устанавливает целочисленное значение в UserRole для QListWidgetItem/QTableWidgetItem."""
    item.setData(Qt.ItemDataRole.UserRole, int(value))


def get_item_dict(item) -> Optional[Dict[str, Any]]:
    """[DEPRECATED] Читает словарь из UserRole. Возвращает None, если не dict."""
    try:
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def set_item_dict(item, value: Dict[str, Any]) -> None:
    """[DEPRECATED] Устанавливает словарь в UserRole."""
    item.setData(Qt.ItemDataRole.UserRole, value)
