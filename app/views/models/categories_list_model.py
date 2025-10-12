import logging
from typing import Any, Optional

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget

from app.utils.ui.icon import resolve_category_icon_path
from app.utils.ui.icon.cache_manager import get_cached_category_icon

logger = logging.getLogger(__name__)

# Single default QIcon to save allocations
DEFAULT_ICON = QIcon()


class CategoriesListModel(QAbstractListModel):
    """Simple model for a list of categories.

    Item: dict with keys: id (int), name (str), icon_path (str|None)
    Roles:
      - DisplayRole: name
      - DecorationRole: QIcon resolved from icon_path
      - UserRole: id
      - ToolTipRole: name (can be extended)
    """

    def __init__(self, categories: Optional[list[dict[str, Any]]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._items: list[dict[str, Any]] = []
        # Row cache by id for O(1) lookup: id -> row
        self._row_by_id: dict[int, int] = {}
        if categories:
            self.set_categories(categories)

    # --- data API ---
    def rowCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        if parent is None:
            parent = QModelIndex()
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
    def set_categories(self, categories: list[dict[str, Any]]) -> None:
        # Normalize input data and prepare icons
        items: list[dict[str, Any]] = []
        for cat in categories:
            name = cat.get("name", "")
            raw_id = cat.get("id")
            try:
                if raw_id is None:
                    raise ValueError("id is None")
                cat_id = int(raw_id)
            except Exception as e:
                # Log skipping of invalid element per common pattern
                logger.warning(
                    "Skipped category list item: invalid id (%r). Item=%r; reason: %s",
                    raw_id,
                    cat,
                    e,
                    exc_info=False,
                )
                continue
            icon_path = cat.get("icon_path", "") or ""
            resolved_path = resolve_category_icon_path(icon_path)
            icon = get_cached_category_icon(resolved_path) if resolved_path else DEFAULT_ICON
            items.append({"id": cat_id, "name": name, "_icon": icon})

        self.beginResetModel()
        self._items = items
        # Rebuild row cache by id
        # Important: keep the index of the FIRST occurrence for compatibility with previous linear lookup
        row_by_id: dict[int, int] = {}
        for idx, it in enumerate(self._items):
            cid = it["id"]
            if cid not in row_by_id:
                row_by_id[cid] = idx
        self._row_by_id = row_by_id
        self.endResetModel()

    # --- helpers ---
    def find_row_by_id(self, category_id: int) -> int:
        # Use cache for O(1) lookup
        return self._row_by_id.get(category_id, -1)
