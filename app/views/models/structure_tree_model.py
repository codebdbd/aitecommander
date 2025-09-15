from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Iterable

from PyQt6.QtCore import QAbstractItemModel, QModelIndex, Qt, QMimeData
from PyQt6.QtGui import QIcon

# Типы узлов дерева
NodeType = str  # "section" | "category" | "root"


@dataclass(eq=False)
class TreeNode:
    type: NodeType
    id: Optional[int]
    name: str = ""
    parent: Optional["TreeNode"] = None
    children: List["TreeNode"] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    icon: Optional[QIcon] = None

    def row(self) -> int:
        if not self.parent:
            return 0
        try:
            return self.parent.children.index(self)
        except ValueError:
            return -1

    def __hash__(self) -> int:
        # Идентичностный хеш позволяет использовать узлы как ключи словаря
        # (например, при группировке по родителю) и безопасен для мутируемых объектов
        return id(self)


class StructureTreeModel(QAbstractItemModel):
    """
    Иерархическая модель для структуры разделов/категорий.

    - Колонка одна (имя).
    - Qt.UserRole возвращает кортеж (type, id) для совместимости с get_tree_tuple().
    - Qt.DecorationRole возвращает иконку узла (если задана).

    Публичные batch-методы (минимальный набор для начального этапа):
    - set_snapshot(tree: list[dict])
    - index_for(item_type: str, item_id: int) -> QModelIndex | invalid
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root = TreeNode(type="root", id=None, name="root")
        # Быстрые отображения для поиска индексов
        self._section_by_id: Dict[int, TreeNode] = {}
        self._category_by_id: Dict[int, TreeNode] = {}
        # Для будущего: можно хранить persistent index'ы, если потребуется

    

    # --- Базовая иерархия ---
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 (Qt API)
        return 1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        node = self._node_from_index(parent)
        return len(node.children)

    def index(
        self, row: int, column: int, parent: QModelIndex = QModelIndex()
    ) -> QModelIndex:  # noqa: N802
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
            # Родителем секций является root → top-level
            return QModelIndex()
        grand = node.parent.parent
        row = node.parent.row()
        if grand is None:
            row = node.parent.row()
        return self.createIndex(row, 0, node.parent)

    # --- Данные/роли ---
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None
        # Пытаемся получить узел из internalPointer; при сбое восстанавливаем по (parent,row)
        node: TreeNode
        try:
            node = index.internalPointer()  # type: ignore[assignment]
            if not isinstance(node, TreeNode):
                raise TypeError("invalid internalPointer type")
        except Exception:
            # Fallback: извлечь родителя и вычислить узел по индексу строки
            try:
                parent_idx = index.parent()
            except Exception:
                parent_idx = QModelIndex()
            parent_node = self._node_from_index(parent_idx)
            try:
                row = index.row()
                node = parent_node.children[row]
            except Exception:
                return None
        if role == Qt.ItemDataRole.DisplayRole:
            return node.name
        if role == Qt.ItemDataRole.DecorationRole:
            return node.icon
        if role == Qt.ItemDataRole.UserRole:
            # Совместимость с get_tree_tuple(): (type, id)
            return (node.type, node.id)
        return None

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:  # noqa: N802
        if not index.isValid():
            return False
        node: TreeNode = index.internalPointer()
        if role == Qt.ItemDataRole.EditRole:
            node.name = str(value)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            return True
        if role == Qt.ItemDataRole.DecorationRole:
            if isinstance(value, QIcon):
                node.icon = value
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])
                return True
        if role == Qt.ItemDataRole.UserRole:
            # Поддержка записи кортежа (type, id) — для совместимости с set_tree_tuple()
            try:
                if isinstance(value, (tuple, list)) and len(value) == 2:
                    t_val, i_val = value
                    if isinstance(t_val, str) and (
                        isinstance(i_val, int) or i_val is None
                    ):
                        # Обновляем мапы, если меняется id/тип
                        old_type, old_id = node.type, node.id
                        if (
                            old_type == "section"
                            and isinstance(old_id, int)
                            and old_id in self._section_by_id
                        ):
                            del self._section_by_id[old_id]
                        if (
                            old_type == "category"
                            and isinstance(old_id, int)
                            and old_id in self._category_by_id
                        ):
                            del self._category_by_id[old_id]

                        node.type = t_val
                        node.id = int(i_val) if isinstance(i_val, int) else None

                        if node.type == "section" and isinstance(node.id, int):
                            self._section_by_id[node.id] = node
                        if node.type == "category" and isinstance(node.id, int):
                            self._category_by_id[node.id] = node

                        self.dataChanged.emit(index, index, [Qt.ItemDataRole.UserRole])
                        return True
            except Exception:
                return False
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        if not index.isValid():
            # Разрешаем drop на пустое пространство верхнего уровня (как минимум для разделов)
            return Qt.ItemFlag.ItemIsDropEnabled | Qt.ItemFlag.ItemIsEnabled
        node: TreeNode = index.internalPointer()
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        # Разрешаем drop на раздел (для категорий) и на корень (для разделов, по необходимости)
        if node.type in ("root", "section"):
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        return flags

    def supportedDropActions(self) -> Qt.DropAction:  # noqa: N802
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    # --- MIME/DnD поддержка модели (минимальная) ---
    def mimeTypes(self) -> list[str]:  # noqa: N802
        # Используются типы из app_config; модель объявляет общий тип
        return ["application/x-structure-tree-index"]

    def mimeData(self, indexes: Iterable[QModelIndex]) -> QMimeData:  # noqa: N802
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
        # В текущей архитектуре перенос обрабатывается на уровне view/handler.
        # Реализуем безопасный no-op, чтобы не ломать стандартный DnD Qt.
        # Возвращаем False, чтобы указать, что модель не обрабатывает drop напрямую.
        return False

    # --- Инкрементальные операции высокого уровня (удобные API) ---
    def insert_sections(self, row: int, sections: List[Dict[str, Any]]) -> None:
        if row < 0:
            row = len(self._root.children)
        count = len(sections or [])
        if count == 0:
            return
        self.beginInsertRows(QModelIndex(), row, row + count - 1)
        for i, s in enumerate(sections):
            sid = s.get("id")
            sec_node = TreeNode(
                type="section",
                id=(sid if isinstance(sid, int) else None),
                name=str(s.get("name", "")),
                parent=self._root,
                icon=(s.get("icon") if isinstance(s.get("icon"), QIcon) else None),
                payload=s,
            )
            self._root.children.insert(row + i, sec_node)
            if isinstance(sec_node.id, int):
                self._section_by_id[sec_node.id] = sec_node
        self.endInsertRows()

    def insert_categories(
        self, section_id: int, row: int, categories: List[Dict[str, Any]]
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
        self.beginInsertRows(parent_index, row, row + count - 1)
        for i, c in enumerate(categories):
            cid = c.get("id")
            cat_node = TreeNode(
                type="category",
                id=(cid if isinstance(cid, int) else None),
                name=str(c.get("name", "")),
                parent=sec_node,
                icon=(c.get("icon") if isinstance(c.get("icon"), QIcon) else None),
                payload=c,
            )
            sec_node.children.insert(row + i, cat_node)
            if isinstance(cat_node.id, int):
                self._category_by_id[cat_node.id] = cat_node
        self.endInsertRows()

    def remove_sections(self, section_ids: List[int]) -> None:
        # Удаляем по одному, учитывая сдвиги индексов
        for sec_id in list(section_ids or []):
            sec_node = self._section_by_id.get(int(sec_id))
            if not sec_node:
                continue
            row = sec_node.row()
            self.beginRemoveRows(QModelIndex(), row, row)
            # Удаляем все категории из мапы
            for cat in sec_node.children:
                if isinstance(cat.id, int) and cat.id in self._category_by_id:
                    del self._category_by_id[cat.id]
            # Удаляем раздел
            self._root.children.pop(row)
            if isinstance(sec_id, int) and sec_id in self._section_by_id:
                del self._section_by_id[sec_id]
            self.endRemoveRows()

    def remove_categories(self, category_ids: List[int]) -> None:
        # Группируем по родителю, чтобы корректно вызывать beginRemoveRows per parent
        by_parent: Dict[TreeNode, List[TreeNode]] = {}
        for cid in list(category_ids or []):
            cat_node = self._category_by_id.get(int(cid))
            if not cat_node or not cat_node.parent:
                continue
            by_parent.setdefault(cat_node.parent, []).append(cat_node)
        for parent_node, cats in by_parent.items():
            cats_sorted = sorted(cats, key=lambda n: n.row())
            # Удаляем по одному (простая и безопасная стратегия)
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

    def update_item(self, item_type: str, item_id: int, data: Dict[str, Any]) -> None:
        """Инкрементальное обновление узла по типу и id.

        Поддерживаются поля: name, icon. При отсутствии узла — no-op.
        """
        node: Optional[TreeNode]
        if item_type == "section":
            node = self._section_by_id.get(int(item_id))
        elif item_type == "category":
            node = self._category_by_id.get(int(item_id))
        else:
            node = None
        if not node:
            return
        idx = self.createIndex(node.row(), 0, node)
        # Имя
        if "name" in data:
            try:
                node.name = str(data.get("name", node.name))
            except Exception:
                pass
        # Иконка
        if "icon" in data:
            ic = data.get("icon")
            if isinstance(ic, QIcon) or ic is None:
                node.icon = ic
        # Нотификация
        try:
            self.dataChanged.emit(
                idx,
                idx,
                [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole],
            )
        except Exception:
            pass

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
        # Корректируем new_row если перенос внутри одного родителя и ниже по списку
        if src_parent is dst_parent and new_row > src_row:
            new_row -= 1
        # Выполняем перенос
        if not self.beginMoveRows(
            src_parent_index, src_row, src_row, dst_parent_index, new_row
        ):
            return False
        # Реальный перенос в структуре
        src_parent.children.pop(src_row)
        cat_node.parent = dst_parent
        dst_parent.children.insert(new_row, cat_node)
        self.endMoveRows()
        return True

    # --- Пакетные операции ---
    def set_snapshot(self, sections: List[Dict[str, Any]]) -> None:
        """
        Полная перезагрузка дерева. Формат sections — список dict:
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
            sec_node = TreeNode(
                type="section",
                id=(s.get("id") if isinstance(s.get("id"), int) else None),
                name=str(s.get("name", "")),
                parent=self._root,
                icon=s.get("icon"),
                payload=s,
            )
            self._root.children.append(sec_node)
            if isinstance(sec_node.id, int):
                self._section_by_id[sec_node.id] = sec_node

            for c in s.get("categories") or []:
                cid = c.get("id")
                cat_node = TreeNode(
                    type="category",
                    id=(cid if isinstance(cid, int) else None),
                    name=str(c.get("name", "")),
                    parent=sec_node,
                    icon=(c.get("icon") if isinstance(c.get("icon"), QIcon) else None),
                    payload=c,
                )
                sec_node.children.append(cat_node)
                if isinstance(cat_node.id, int):
                    self._category_by_id[cat_node.id] = cat_node

        self.endResetModel()

    def _create_section_node(self, s: Dict[str, Any]) -> TreeNode:
        sec_node = TreeNode(
            type="section",
            id=(s.get("id") if isinstance(s.get("id"), int) else None),
            name=str(s.get("name", "")),
            parent=self._root,
            icon=s.get("icon") if isinstance(s.get("icon"), QIcon) or s.get("icon") is None else None,
            payload=s,
        )
        if isinstance(sec_node.id, int):
            self._section_by_id[sec_node.id] = sec_node
        for c in s.get("categories") or []:
            cid = c.get("id")
            cat_node = TreeNode(
                type="category",
                id=(cid if isinstance(cid, int) else None),
                name=str(c.get("name", "")),
                parent=sec_node,
                icon=(c.get("icon") if isinstance(c.get("icon"), QIcon) else None),
                payload=c,
            )
            sec_node.children.append(cat_node)
            if isinstance(cat_node.id, int):
                self._category_by_id[cat_node.id] = cat_node
        return sec_node

    def update_snapshot(self, sections: List[Dict[str, Any]]) -> None:
        """Инкрементально обновляет модель по новому снапшоту без full reset.

        Выполняет удаления отсутствующих узлов, вставки новых и dataChanged для обновлений.
        Перестановка существующих секций реализована через remove+insert для минимальной поддержки порядка.
        Перестановка категорий внутри раздела пока не поддерживает move и выполняется через insert в
        заданные позиции при необходимости, а отсутствующие удаляются.
        """
        new_sections = sections or []
        new_sec_ids: List[int] = []
        new_sec_by_id: Dict[int, Dict[str, Any]] = {}
        for s in new_sections:
            sid = s.get("id")
            if isinstance(sid, int):
                new_sec_ids.append(sid)
                new_sec_by_id[sid] = s

        # 1) Удаление отсутствующих секций
        self._remove_absent_sections(new_sec_by_id)
        # 2) Вставка/обновление секций и их категорий
        self._upsert_sections(new_sec_ids, new_sec_by_id)

    def _remove_absent_sections(self, new_sec_by_id: Dict[int, Dict[str, Any]]) -> None:
        for row in range(len(self._root.children) - 1, -1, -1):
            node = self._root.children[row]
            if node.type == "section" and isinstance(node.id, int) and node.id not in new_sec_by_id:
                # Удаляем все категории из мапы
                for child in node.children:
                    if isinstance(child.id, int) and child.id in self._category_by_id:
                        del self._category_by_id[child.id]
                self.beginRemoveRows(QModelIndex(), row, row)
                self._root.children.pop(row)
                if node.id in self._section_by_id:
                    del self._section_by_id[node.id]
                self.endRemoveRows()

    def _upsert_sections(self, new_sec_ids: List[int], new_sec_by_id: Dict[int, Dict[str, Any]]) -> None:
        root_index = QModelIndex()
        i = 0
        while i < len(new_sec_ids):
            sid = new_sec_ids[i]
            desired_data = new_sec_by_id[sid]
            existing = self._section_by_id.get(sid)
            if existing is None:
                # Вставка новой секции на позицию i
                self.beginInsertRows(root_index, i, i)
                node = self._create_section_node(desired_data)
                node.parent = self._root
                self._root.children.insert(i, node)
                self.endInsertRows()
            else:
                # Убедимся, что узел на позиции i соответствует sid; иначе переставим
                current_row = existing.row()
                if current_row != i and current_row >= 0:
                    # remove+insert для минимальной поддержки порядка
                    self.beginRemoveRows(root_index, current_row, current_row)
                    self._root.children.pop(current_row)
                    self.endRemoveRows()
                    self.beginInsertRows(root_index, i, i)
                    self._root.children.insert(i, existing)
                    self.endInsertRows()
                # Обновление имени/иконки секции
                changed = False
                try:
                    new_name = str(desired_data.get("name", existing.name))
                    if existing.name != new_name:
                        existing.name = new_name
                        changed = True
                except Exception:
                    pass
                try:
                    new_icon = desired_data.get("icon")
                    if isinstance(new_icon, QIcon) or new_icon is None:
                        if existing.icon != new_icon:
                            existing.icon = new_icon
                            changed = True
                except Exception:
                    pass
                if changed:
                    idx = self.createIndex(i, 0, existing)
                    self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])

                # Синхронизация категорий
                self._sync_categories(existing, i, desired_data)
            i += 1

    def _sync_categories(self, section_node: TreeNode, section_row: int, desired_data: Dict[str, Any]) -> None:
        new_cats = desired_data.get("categories") or []
        new_cat_ids: List[int] = []
        new_cat_by_id: Dict[int, Dict[str, Any]] = {}
        for c in new_cats:
            cid = c.get("id")
            if isinstance(cid, int):
                new_cat_ids.append(cid)
                new_cat_by_id[cid] = c

        # Удаление отсутствующих категорий
        for crow in range(len(section_node.children) - 1, -1, -1):
            cnode = section_node.children[crow]
            if cnode.type == "category" and isinstance(cnode.id, int) and cnode.id not in new_cat_by_id:
                parent_index = self.createIndex(section_row, 0, section_node)
                self.beginRemoveRows(parent_index, crow, crow)
                section_node.children.pop(crow)
                if cnode.id in self._category_by_id:
                    del self._category_by_id[cnode.id]
                self.endRemoveRows()

        # Вставка/обновление категорий в порядке
        j = 0
        while j < len(new_cat_ids):
            cid = new_cat_ids[j]
            c_existing = self._category_by_id.get(cid)
            parent_index = self.createIndex(section_row, 0, section_node)
            if c_existing is None or c_existing.parent is not section_node:
                # новая категория
                self.beginInsertRows(parent_index, j, j)
                cdata = new_cat_by_id[cid]
                cnode = TreeNode(
                    type="category",
                    id=cid,
                    name=str(cdata.get("name", "")),
                    parent=section_node,
                    icon=(cdata.get("icon") if isinstance(cdata.get("icon"), QIcon) else None),
                    payload=cdata,
                )
                section_node.children.insert(j, cnode)
                self._category_by_id[cid] = cnode
                self.endInsertRows()
            else:
                # Убедимся, что на позиции j нужный узел; иначе переставим
                cur_row = c_existing.row()
                if cur_row != j and cur_row >= 0 and c_existing.parent is section_node:
                    self.beginRemoveRows(parent_index, cur_row, cur_row)
                    section_node.children.pop(cur_row)
                    self.endRemoveRows()
                    self.beginInsertRows(parent_index, j, j)
                    section_node.children.insert(j, c_existing)
                    self.endInsertRows()
                # Обновление имени/иконки
                cdata = new_cat_by_id[cid]
                c_changed = False
                try:
                    new_name = str(cdata.get("name", c_existing.name))
                    if c_existing.name != new_name:
                        c_existing.name = new_name
                        c_changed = True
                except Exception:
                    pass
                try:
                    new_icon = cdata.get("icon")
                    if isinstance(new_icon, QIcon) or new_icon is None:
                        if c_existing.icon != new_icon:
                            c_existing.icon = new_icon
                            c_changed = True
                except Exception:
                    pass
                if c_changed:
                    cidx = self.createIndex(j, 0, c_existing)
                    self.dataChanged.emit(cidx, cidx, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
            j += 1

    # --- Сортировка ---
    def sort(  # noqa: N802
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
        """Сортирует разделы и категории по имени без реконструкции снапшота.

        - Сортируется только колонка 0 (имена)
        - Секции (`self._root.children`) и категории внутри каждой секции
        - Используются сигналы `layoutAboutToBeChanged`/`layoutChanged` для уведомления представлений
        """
        if column != 0:
            return
        try:
            self.layoutAboutToBeChanged.emit()
            reverse = order == Qt.SortOrder.DescendingOrder
            # Секции
            try:
                self._root.children.sort(key=lambda n: (n.name or "").lower(), reverse=reverse)
            except Exception:
                pass
            # Категории в каждой секции
            for sec in self._root.children:
                try:
                    sec.children.sort(key=lambda n: (n.name or "").lower(), reverse=reverse)
                except Exception:
                    continue
        finally:
            self.layoutChanged.emit()

    # --- Поиск индексов ---
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

    # --- Вспомогательное ---
    def _node_from_index(self, index: QModelIndex) -> TreeNode:
        if index.isValid():
            node = index.internalPointer()
            if isinstance(node, TreeNode):
                return node
        return self._root
