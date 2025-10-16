from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import QModelIndex, Qt


def get_tree_tuple(index: QModelIndex, column: int = 0) -> Optional[Tuple[str, int]]:
    """Read ``(type, id)`` from UserRole for the given ``QModelIndex``.

    Uses the specified ``column`` (defaults to 0). Returns ``None`` if the data
    structure is invalid or the index is not valid.
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
    """Read an integer value from UserRole by ``QModelIndex``. Returns ``None`` on failure."""
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
    """Read a ``dict`` from UserRole by ``QModelIndex``. Returns ``None`` if not a dict."""
    try:
        if not index or not index.isValid():
            return None
        data = index.model().data(index, Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def set_index_data(
    index, value: Any, role: Qt.ItemDataRole = Qt.ItemDataRole.UserRole
) -> bool:
    """Set value via ``model.setData(index, value, role)``.
    Returns ``True`` on success, ``False`` otherwise. Requires the model to support ``setData`` for the role.
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
    """Set ``(type, id)`` into UserRole for ``QModelIndex`` via ``model.setData``.
    Requires the model to support ``setData`` for ``UserRole``.
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


def get_row_userrole(
    view, row: int, column: int = 0, role: Qt.ItemDataRole = Qt.ItemDataRole.UserRole
) -> Any:
    """Return role data from the model by row index via a view (QTableView).
    Handy to get a link dict from UserRole: ``role=UserRole``, ``column=0``.
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


def get_selected_rows(view) -> list[int]:
    """Return sorted unique selected rows.

    Works safely with QTableView/QTreeView using ``selectionModel().selectedRows()``.
    Returns an empty list on any error or when no selection is present.
    """
    try:
        selection_model = view.selectionModel()
        if not selection_model:
            return []

        # selectedRows() returns one index per selected row only
        # This is more efficient than collecting from selectedIndexes() and deduplicating
        selected_rows = {index.row() for index in selection_model.selectedRows()}
        return sorted(list(selected_rows))
    except Exception:
        return []


def find_index_by_role(
    model, type_val: str, id_val: int, parent: QModelIndex | None = None
) -> Optional[QModelIndex]:
    """Recursive search for ``QModelIndex`` by ``(type, id)`` tuple in ``UserRole``, column 0.
    Generic and model-agnostic. For large trees, prefer specialized model methods (e.g., ``index_for``).
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
            # Recursively traverse the tree
            found = find_index_by_role(model, type_val, id_val, idx)
            if found is not None:
                return found
        return None
    except Exception:
        return None
