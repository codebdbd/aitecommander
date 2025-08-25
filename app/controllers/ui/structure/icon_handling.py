# app/controllers/structure/icon_handling.py

from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.qt.roles import get_tree_tuple


class IconHandling:
    def __init__(self, controller):
        self.controller = controller
        self.tree = controller.tree
        self.business = controller.business

    def _get_icon_for_item(self, item_type: str, icon_name: str) -> QIcon:
        # Централизованный резолвер: учитывает и заданный icon_name, и тип
        try:
            resolved = resolve_icon_for_link(
                {"type": item_type, "icon_path": icon_name or ""}
            )
            if resolved:
                return create_icon_from_path(resolved)
        except Exception:
            pass
        # Пустая иконка, если ничего не найдено
        return QIcon()

    def reload_icons(self) -> None:
        """Переустанавливает иконки для всех элементов дерева.

        Обходим модель QTreeView и выставляем иконки через DecorationRole.
        """
        # Ветвь для QTreeView — обходим модель и выставляем DecorationRole
        try:
            model = getattr(self.tree, "model", lambda: None)()
            if not model:
                return

            # Локальная рекурсивная функция обхода
            def iter_indexes(parent_index=None):
                from PyQt6.QtCore import QModelIndex

                if parent_index is None:
                    parent_index = QModelIndex()
                rows = model.rowCount(parent_index)
                for r in range(rows):
                    idx = model.index(r, 0, parent_index)
                    if idx.isValid():
                        yield idx
                        yield from iter_indexes(idx)

            from app.utils.ui.qt.roles import get_tree_tuple

            for idx in iter_indexes():
                t = get_tree_tuple(idx, 0)
                if not t:
                    # Сбрасываем иконку, если нет валидных данных
                    try:
                        model.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                    except Exception:
                        pass
                    continue
                item_type, item_id = t
                try:
                    if item_type == "section":
                        data = self.business.get_section_data(item_id)
                    elif item_type == "category":
                        data = self.business.get_category_data(item_id)
                    else:
                        data = None
                    if data:
                        icon = self._get_icon_for_item(item_type, data.get("icon_path"))
                        model.setData(idx, icon, Qt.ItemDataRole.DecorationRole)
                    else:
                        model.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                except Exception:
                    try:
                        model.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                    except Exception:
                        pass
        except Exception:
            # В случае любой ошибки не прерываем UI
            pass
