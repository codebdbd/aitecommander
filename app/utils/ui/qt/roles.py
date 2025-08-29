from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import QModelIndex, Qt


def get_tree_tuple(index: QModelIndex, column: int = 0) -> Optional[Tuple[str, int]]:
    """Читает (type, id) из UserRole по QModelIndex (колонка column, по умолчанию 0).
    Возвращает None, если структура некорректна или индекс невалиден.
    """
    try:
        if not isinstance(index, QModelIndex) or not index.isValid():
            return None
        model = index.model()
        data = model.data(index, Qt.ItemDataRole.UserRole)
        if isinstance(data, (tuple, list)) and len(data) == 2:
            type_val, id_val = data
            if isinstance(type_val, str) and isinstance(id_val, int):
                return type_val, id_val
        return None
    except Exception:
        return None

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


def set_tree_tuple(index: QModelIndex, value: Tuple[str, int]) -> bool:
    """Устанавливает (type, id) в UserRole для QModelIndex через model.setData.
    Требует поддержки setData в модели для UserRole.
    """
    try:
        if not index or not index.isValid():
            return False
        if not (isinstance(value, (tuple, list)) and len(value) == 2):
            return False
        t, i = value
        if not (isinstance(t, str) and isinstance(i, int)):
            return False
        return bool(index.model().setData(index, (t, i), Qt.ItemDataRole.UserRole))
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


def find_index_by_role(
    model, type_val: str, id_val: int, parent: QModelIndex | None = None
) -> Optional[QModelIndex]:
    """Рекурсивный поиск QModelIndex по кортежу (type,id) в UserRole, колонка 0.
    Универсальный и независящий от конкретной модели. Для больших деревьев
    рекомендуется использовать специализированные методы модели (например, index_for).
    """
    try:
        if model is None:
            return None
        parent = parent or QModelIndex()
        rc = model.rowCount(parent)
        for r in range(rc):
            idx = model.index(r, 0, parent)
            if not idx.isValid():
                continue
            data = model.data(idx, Qt.ItemDataRole.UserRole)
            if (
                isinstance(data, (tuple, list))
                and len(data) == 2
                and data[0] == type_val
                and data[1] == id_val
            ):
                return idx
            # Рекурсивный спуск
            found = find_index_by_role(model, type_val, id_val, idx)
            if found is not None:
                return found
        return None
    except Exception:
        return None
