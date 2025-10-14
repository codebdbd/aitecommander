from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PyQt6.QtGui import QIcon

# Tree node types
NodeType = str  # "section" | "category" | "root"


if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from PyQt6.QtCore import QMimeData


def _coerce_optional_int(value: Any) -> int | None:
    """Return ``int(value)`` when the input can be safely coerced, else ``None``."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


@dataclass(eq=False)
class TreeNode:
    type: NodeType
    id: int | None
    name: str = ""
    parent: TreeNode | None = None
    children: list[TreeNode] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    icon: QIcon | None = None

    def row(self) -> int:
        if not self.parent:
            return 0
        try:
            return self.parent.children.index(self)
        except ValueError:
            return -1

    def __hash__(self) -> int:
        # Identity-based hash allows using nodes as dict keys
        # (e.g., grouping by parent) and is safe for mutable objects
        return id(self)


class StructureTreeModel(QAbstractItemModel):
    """
    Hierarchical model for sections/categories structure.

    - Single column (name).
    - Qt.UserRole returns a tuple (type, id) for compatibility with get_tree_tuple().
    - Qt.DecorationRole returns node icon (if provided).

    Public batch methods (minimal initial set):
    - set_snapshot(tree: list[dict])
    - index_for(item_type: str, item_id: int) -> QModelIndex | invalid
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root = TreeNode(type="root", id=None, name="root")
        self._section_by_id: dict[int, TreeNode] = {}
        self._category_by_id: dict[int, TreeNode] = {}

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802 (Qt API)
        return 1

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is None:
            parent = QModelIndex()
        node = self._node_from_index(parent)
        return len(node.children)

    def index(
        self, row: int, column: int, parent: QModelIndex | None = None
    ) -> QModelIndex:  # noqa: N802
        if parent is None:
            parent = QModelIndex()
        if column != 0 or row < 0:
            return QModelIndex()
        parent_node = self._node_from_index(parent)
        if 0 <= row < len(parent_node.children):
            child = parent_node.children[row]
            return self.createIndex(row, 0, child)
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:  # type: ignore[override]  # noqa: N802
        if not index.isValid():
            return QModelIndex()
        node: TreeNode = index.internalPointer()
        if not node.parent or node.parent is self._root:
            return QModelIndex()
        grand = node.parent.parent
        row = node.parent.row()
        if grand is None:
            row = node.parent.row()
        return self.createIndex(row, 0, node.parent)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None

        node: TreeNode = index.internalPointer()
        if node is None:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return node.name
        if role == Qt.ItemDataRole.DecorationRole:
            return node.icon
        if role == Qt.ItemDataRole.UserRole:
            return (node.type, node.id)
        return None

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:  # noqa: N802
        if not index.isValid():
            return False

        node: TreeNode = index.internalPointer()
        if node is None:
            return False

        if role == Qt.ItemDataRole.EditRole:
            node.name = str(value)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            return True

        if role == Qt.ItemDataRole.DecorationRole:
            if isinstance(value, QIcon):
                node.icon = value
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])
                return True
            elif isinstance(value, str):
                # Если это путь к иконке - загружаем её
                try:
                    from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
                    node.icon = icon_cache.get_icon(value, source="tree_model")
                    self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])
                    return True
                except Exception:
                    node.icon = None
                    self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])
                    return True

        return False

    def _preload_category_icons(self, categories: list[dict[str, Any]]) -> None:
        """Предзагрузка иконок для новых категорий перед их отображением."""
        try:
            from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache

            # Собираем уникальные пути к иконкам
            icon_paths = set()
            for category in categories:
                icon_path = category.get("icon_path")
                if icon_path and isinstance(icon_path, str) and icon_path.strip():
                    icon_paths.add(icon_path.strip())

            if not icon_paths:
                return

            # Предзагружаем иконки синхронно для надежности и мгновенного отображения
            for icon_path in icon_paths:
                if icon_path:
                    try:
                        # Загружаем иконку в кэш синхронно
                        icon_cache.get_icon(icon_path, source="tree_preload")
                    except Exception as exc:
                        # Игнорируем ошибки предзагрузки
                        logger = logging.getLogger(__name__)
                        logger.debug("Icon preload failed for %s: %s", icon_path, exc)

        except Exception as exc:
            # Предзагрузка не должна нарушать основную функциональность
            logger = logging.getLogger(__name__)
            logger.debug("Failed to preload icons: %s", exc)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled | Qt.ItemFlag.ItemIsEnabled
        node: TreeNode = index.internalPointer()
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        if node.type in ("root", "section"):
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        return flags

    def supportedDropActions(self) -> Qt.DropAction:  # noqa: N802
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def mimeTypes(self) -> list[str]:  # noqa: N802
        return ["application/x-structure-tree-index"]

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:  # type: ignore[override]  # noqa: N802
        import json

        from PyQt6.QtCore import QByteArray, QMimeData

        mime = QMimeData()
        payload = []
        for idx in indexes or []:
            if not idx or not idx.isValid() or idx.column() != 0:
                continue
            t = self.data(idx, Qt.ItemDataRole.UserRole)
            if isinstance(t, (tuple, list)) and len(t) == 2:
                payload.append([t[0], t[1]])
        try:
            ba = QByteArray(bytes(json.dumps(payload), encoding="utf-8"))
            mime.setData("application/x-structure-tree-index", ba)
        except Exception:
            pass
        return mime

    def dropMimeData(  # noqa: N802
        self,
        data,
        action: Qt.DropAction,
        row: int,
        column: int,
        parent: QModelIndex,
    ) -> bool:
        # DnD handled by view/handler; model does not process drops
        return False

    # --- High-level incremental operations (convenient APIs) ---
    def insert_sections(self, row: int, sections: list[dict[str, Any]]) -> None:
        if row < 0:
            row = len(self._root.children)
        count = len(sections or [])
        if count == 0:
            return
        self.beginInsertRows(QModelIndex(), row, row + count - 1)
        for i, s in enumerate(sections):
            # Обрабатываем иконку секции правильно
            icon = s.get("icon")
            if isinstance(icon, str):
                # Если это путь к иконке - загружаем её
                try:
                    from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
                    icon = icon_cache.get_icon(icon, source="tree_model")
                except Exception:
                    icon = None
            elif not isinstance(icon, QIcon):
                icon = None

            sec_node = TreeNode(
                type="section",
                id=_coerce_optional_int(s.get("id")),
                name=str(s.get("name", "")),
                parent=self._root,
                icon=icon,
                payload=s,
            )
            self._root.children.insert(row + i, sec_node)
            if isinstance(sec_node.id, int):
                self._section_by_id[sec_node.id] = sec_node
        self.endInsertRows()

    def insert_categories(
        self, section_id: int, row: int, categories: list[dict[str, Any]]
    ) -> None:
        sec_node = self._section_by_id.get(int(section_id))
        if not sec_node:
            return
        parent_index = self.createIndex(sec_node.row(), 0, sec_node)
        if row < 0:
            row = len(sec_node.children)
        count = len(categories or [])
        if count == 0:
            return

        # Сначала предзагружаем иконки для новых категорий
        self._preload_category_icons(categories)

        self.beginInsertRows(parent_index, row, row + count - 1)
        for i, c in enumerate(categories):
            # Обрабатываем иконку категории правильно
            icon = c.get("icon")
            if isinstance(icon, str):
                # Если это путь к иконке - загружаем её
                try:
                    from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
                    icon = icon_cache.get_icon(icon, source="tree_model")
                except Exception:
                    icon = None
            elif not isinstance(icon, QIcon):
                icon = None

            cat_node = TreeNode(
                type="category",
                id=_coerce_optional_int(c.get("id")),
                name=str(c.get("name", "")),
                parent=sec_node,
                icon=icon,
                payload=c,
            )
            sec_node.children.insert(row + i, cat_node)
            if isinstance(cat_node.id, int):
                self._category_by_id[cat_node.id] = cat_node
        self.endInsertRows()

        # Принудительно уведомляем вид об изменении данных для мгновенного обновления
        # Это гарантирует, что иконки отобразятся сразу после вставки строк
        if count > 0:
            # Создаем индекс для первой вставленной категории
            first_cat_index = self.createIndex(row, 0, sec_node.children[row])
            if first_cat_index.isValid():
                # Уведомляем об изменении данных для всех ролей
                last_cat_index = self.createIndex(row + count - 1, 0, sec_node.children[row + count - 1])
                self.dataChanged.emit(first_cat_index, last_cat_index,
                                    [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])

    def update_item(
        self, item_type: NodeType, item_id: int, data: dict[str, Any]
    ) -> None:
        idx = self.index_for(item_type, int(item_id))
        if not idx.isValid():
            return
        node: TreeNode = idx.internalPointer()
        if "name" in data:
            node.name = str(data.get("name", node.name))
        if "icon" in data:
            icon = data.get("icon")
            if isinstance(icon, QIcon):
                node.icon = icon
            elif isinstance(icon, str):
                # Если это путь к иконке - загружаем её
                try:
                    from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
                    node.icon = icon_cache.get_icon(icon, source="tree_model")
                except Exception:
                    node.icon = None
            else:
                node.icon = None
        if data:
            node.payload.update(data)
        self.dataChanged.emit(
            idx,
            idx,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.DecorationRole,
                Qt.ItemDataRole.UserRole,
            ],
        )

    def remove_sections(self, section_ids: list[int]) -> None:
        for sec_id in list(section_ids or []):
            sec_node = self._section_by_id.get(int(sec_id))
            if not sec_node:
                continue
            row = sec_node.row()
            self.beginRemoveRows(QModelIndex(), row, row)
            for cat in sec_node.children:
                if isinstance(cat.id, int) and cat.id in self._category_by_id:
                    del self._category_by_id[cat.id]
            self._root.children.pop(row)
            if isinstance(sec_id, int) and sec_id in self._section_by_id:
                del self._section_by_id[sec_id]
            self.endRemoveRows()

    def remove_categories(self, category_ids: list[int]) -> None:
        by_parent: dict[TreeNode, list[TreeNode]] = {}
        for cid in list(category_ids or []):
            cat_node = self._category_by_id.get(int(cid))
            if not cat_node or not cat_node.parent:
                continue
            by_parent.setdefault(cat_node.parent, []).append(cat_node)
        for parent_node, cats in by_parent.items():
            cats_sorted = sorted(cats, key=lambda n: n.row())
            for node in reversed(cats_sorted):
                parent_index = (
                    QModelIndex()
                    if parent_node is self._root
                    else self.createIndex(parent_node.row(), 0, parent_node)
                )
                row = node.row()
                self.beginRemoveRows(parent_index, row, row)
                parent_node.children.pop(row)
                if isinstance(node.id, int) and node.id in self._category_by_id:
                    del self._category_by_id[node.id]
                self.endRemoveRows()

    def move_category(
        self, category_id: int, new_section_id: int, new_row: int
    ) -> bool:
        cat_node = self._category_by_id.get(int(category_id))
        dst_parent = self._section_by_id.get(int(new_section_id))
        if not cat_node or not dst_parent:
            return False
        src_parent = cat_node.parent
        if not src_parent:
            return False
        if new_row < 0:
            new_row = len(dst_parent.children)
        src_parent_index = (
            QModelIndex()
            if src_parent is self._root
            else self.createIndex(src_parent.row(), 0, src_parent)
        )
        dst_parent_index = (
            QModelIndex()
            if dst_parent is self._root
            else self.createIndex(dst_parent.row(), 0, dst_parent)
        )
        src_row = cat_node.row()
        if src_parent is dst_parent and new_row > src_row:
            new_row -= 1
        if not self.beginMoveRows(
            src_parent_index, src_row, src_row, dst_parent_index, new_row
        ):
            return False
        src_parent.children.pop(src_row)
        cat_node.parent = dst_parent
        dst_parent.children.insert(new_row, cat_node)
        self.endMoveRows()
        return True

    def set_snapshot(self, sections: list[dict[str, Any]]) -> None:
        """
        Full tree reload. The format for sections is a list[dict]:
        {
            "id": int,
            "name": str,
            "icon": Optional[QIcon],
            "categories": [ {"id": int, "name": str, "icon": Optional[QIcon]} ]
        }
        """
        self.beginResetModel()
        self._root.children.clear()
        self._section_by_id.clear()
        self._category_by_id.clear()

        for s in sections or []:
            # Обрабатываем иконку секции правильно
            icon = s.get("icon")
            if isinstance(icon, str):
                # Если это путь к иконке - загружаем её
                try:
                    from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
                    icon = icon_cache.get_icon(icon, source="tree_model")
                except Exception:
                    icon = None
            elif not isinstance(icon, QIcon):
                icon = None

            sec_node = TreeNode(
                type="section",
                id=_coerce_optional_int(s.get("id")),
                name=str(s.get("name", "")),
                parent=self._root,
                icon=icon,
                payload=s,
            )
            self._root.children.append(sec_node)
            if isinstance(sec_node.id, int):
                self._section_by_id[sec_node.id] = sec_node

            for c in s.get("categories") or []:
                # Обрабатываем иконку категории правильно
                icon = c.get("icon")
                if isinstance(icon, str):
                    # Если это путь к иконке - загружаем её
                    try:
                        from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
                        icon = icon_cache.get_icon(icon, source="tree_model")
                    except Exception:
                        icon = None
                elif not isinstance(icon, QIcon):
                    icon = None

                cat_node = TreeNode(
                    type="category",
                    id=_coerce_optional_int(c.get("id")),
                    name=str(c.get("name", "")),
                    parent=sec_node,
                    icon=icon,
                    payload=c,
                )
                sec_node.children.append(cat_node)
                if isinstance(cat_node.id, int):
                    self._category_by_id[cat_node.id] = cat_node

        self.endResetModel()

    def index_for(self, item_type: str, item_id: int) -> QModelIndex:
        if item_type == "section":
            node = self._section_by_id.get(int(item_id))
            if node:
                return self.createIndex(node.row(), 0, node)
            return QModelIndex()
        if item_type == "category":
            node = self._category_by_id.get(int(item_id))
            if node:
                return self.createIndex(node.row(), 0, node)
            return QModelIndex()
        return QModelIndex()

    def _node_from_index(self, index: QModelIndex) -> TreeNode:
        if index.isValid():
            node = index.internalPointer()
            if isinstance(node, TreeNode):
                return node
        return self._root
