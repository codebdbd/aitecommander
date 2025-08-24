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
    """[DEPRECATED] Читает UserRole из QListWidgetItem/QTableWidgetItem и приводит к int. Возвращает None при неудаче.
    Используйте индексно-модельные функции: get_index_int().
    """
    try:
        val = item.data(Qt.ItemDataRole.UserRole)
        if val is None:
            return None
        return int(val)
    except Exception:
        return None


def set_item_int(item, value: int) -> None:
    """[DEPRECATED] Устанавливает целочисленное значение в UserRole для QListWidgetItem/QTableWidgetItem.
    Используйте set_index_data() с QModelIndex.
    """
    item.setData(Qt.ItemDataRole.UserRole, int(value))


def get_item_dict(item) -> Optional[Dict[str, Any]]:
    """[DEPRECATED] Читает словарь из UserRole. Возвращает None, если не dict.
    Используйте get_index_dict() с QModelIndex.
    """
    try:
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def set_item_dict(item, value: Dict[str, Any]) -> None:
    """[DEPRECATED] Устанавливает словарь в UserRole. Используйте set_index_data()."""
    item.setData(Qt.ItemDataRole.UserRole, value)


# --- QTableView/QModelIndex helpers ---

def get_index_int(index) -> Optional[int]:
    """Читает целочисленное значение из UserRole по QModelIndex. Возвращает None при неудаче."""
    try:
        if not index or not index.isValid():
            return None
        val = index.model().data(index, Qt.ItemDataRole.UserRole)
        if val is None:
            return None
        return int(val)
    except Exception:
        return None


def get_index_dict(index) -> Optional[Dict[str, Any]]:
    """Читает словарь из UserRole по QModelIndex. Возвращает None, если не dict."""
    try:
        if not index or not index.isValid():
            return None
        data = index.model().data(index, Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def set_index_data(index, value: Any, role: Qt.ItemDataRole = Qt.ItemDataRole.UserRole) -> bool:
    """Устанавливает значение через model.setData(index, value, role).
    Возвращает True при успехе, False иначе. Требуется, чтобы модель поддерживала setData для данной роли.
    """
    try:
        if not index or not index.isValid():
            return False
        model = index.model()
        if not hasattr(model, "setData"):
            return False
        return bool(model.setData(index, value, role))
    except Exception:
        return False


def get_row_userrole(view, row: int, column: int = 0, role: Qt.ItemDataRole = Qt.ItemDataRole.UserRole) -> Any:
    """Возвращает данные роли из модели по номеру строки через view (QTableView).
    Удобно для получения словаря ссылки из UserRole: role=UserRole, column=0.
    """
    try:
        model = view.model()
        if not model:
            return None
        index = model.index(row, column)
        if not index.isValid():
            return None
        return model.data(index, role)
    except Exception:
        return None


def get_selected_rows(view) -> Tuple[int, ...]:
    """Возвращает кортеж выбранных индексов строк из selectionModel().selectedRows()."""
    try:
        sel = view.selectionModel()
        if not sel:
            return tuple()
        return tuple(sorted({idx.row() for idx in sel.selectedRows()}))
    except Exception:
        return tuple()
