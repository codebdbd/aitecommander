import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, QVariant
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget

from app.utils.ui.icon import resolve_category_icon_path
from app.utils.ui.icon.cache_manager import get_cached_category_icon

logger = logging.getLogger(__name__)

# Единый дефолтный QIcon для экономии аллокаций
DEFAULT_ICON = QIcon()


class CategoriesListModel(QAbstractListModel):
    """Простая модель для списка категорий.

    Элемент: dict с ключами: id (int), name (str), icon_path (str|None)
    Roles:
      - DisplayRole: name
      - DecorationRole: QIcon по icon_path
      - UserRole: id
      - ToolTipRole: name (можно расширить)
    """

    def __init__(self, categories: Optional[List[Dict[str, Any]]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._items: List[Dict[str, Any]] = []
        # Кэш строк по id для O(1) поиска: id -> row
        self._row_by_id: Dict[int, int] = {}
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
            return icon if isinstance(icon, QIcon) else DEFAULT_ICON
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
            except Exception as e:
                # Логируем пропуск некорректного элемента по общему паттерну
                logger.warning(
                    "Пропущен элемент списка категорий: некорректный id (%r). Элемент=%r; причина: %s",
                    raw_id,
                    cat,
                    e,
                    exc_info=False,
                )
                continue
            icon_path = cat.get("icon_path", "") or ""
            if icon_path:
                resolved_path = resolve_category_icon_path(icon_path)
                icon = get_cached_category_icon(resolved_path)
            else:
                icon = DEFAULT_ICON
            items.append({"id": cat_id, "name": name, "_icon": icon})

        self.beginResetModel()
        self._items = items
        # Перестроим кэш строк по id
        # Важно: сохраняем индекс ПЕРВОГО вхождения для совместимости с прежним линейным поиском
        row_by_id: Dict[int, int] = {}
        for idx, it in enumerate(self._items):
            cid = it["id"]
            if cid not in row_by_id:
                row_by_id[cid] = idx
        self._row_by_id = row_by_id
        self.endResetModel()

    # --- helpers ---
    def find_row_by_id(self, category_id: int) -> int:
        # Используем кэш для O(1) поиска
        return self._row_by_id.get(category_id, -1)
