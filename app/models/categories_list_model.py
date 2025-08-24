from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt
from PyQt6.QtGui import QIcon

from app.utils.ui.icon import resolve_category_icon_path
from app.utils.ui.icon.cache_manager import get_cached_category_icon


class CategoriesListModel(QAbstractListModel):
    """Простая модель для списка категорий.

    Элемент: dict с ключами: id (int), name (str), icon_path (str|None)
    Roles:
      - DisplayRole: name
      - DecorationRole: QIcon по icon_path
      - UserRole: id
      - ToolTipRole: name (можно расширить)
    """

    def __init__(self, categories: Optional[List[Dict[str, Any]]] = None, parent=None):
        super().__init__(parent)
        self._items: List[Dict[str, Any]] = []
        if categories:
            self.set_categories(categories)

    # --- data API ---
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._items):
            return None
        item = self._items[row]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.get("name", "")
        if role == Qt.ItemDataRole.DecorationRole:
            icon = item.get("_icon")
            return icon if isinstance(icon, QIcon) else QIcon()
        if role == Qt.ItemDataRole.UserRole:
            return item.get("id")
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.get("name", "")
        return None

    # --- mutators ---
    def set_categories(self, categories: List[Dict[str, Any]]) -> None:
        # Нормализуем входные данные и подготавливаем иконки
        items: List[Dict[str, Any]] = []
        for cat in categories:
            name = cat.get("name", "")
            raw_id = cat.get("id")
            try:
                if raw_id is None:
                    raise ValueError("id is None")
                cat_id = int(raw_id)
            except Exception:
                # пропускаем некорректные
                continue
            icon_path = cat.get("icon_path", "") or ""
            if icon_path:
                resolved_path = resolve_category_icon_path(icon_path)
                icon = get_cached_category_icon(resolved_path)
            else:
                icon = QIcon()
            items.append({"id": cat_id, "name": name, "_icon": icon})

        self.beginResetModel()
        self._items = items
        self.endResetModel()

    # --- helpers ---
    def find_row_by_id(self, category_id: int) -> int:
        for i, it in enumerate(self._items):
            if it.get("id") == category_id:
                return i
        return -1
