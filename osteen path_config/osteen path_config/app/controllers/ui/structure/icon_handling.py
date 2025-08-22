# app/controllers/structure/icon_handling.py

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QTreeWidgetItem, QTreeWidgetItemIterator

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
            resolved = resolve_icon_for_link({"type": item_type, "icon_path": icon_name or ""})
            if resolved:
                return create_icon_from_path(resolved)
        except Exception:
            pass
        # Пустая иконка, если ничего не найдено
        return QIcon()
    
    def _set_tree_item_icon(self, item: QTreeWidgetItem, item_type: str, data: dict) -> None:
        icon = self._get_icon_for_item(item_type, data.get("icon_path"))
        item.setIcon(0, icon)
    
    def reload_icons(self) -> None:
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            self._update_item_icon(iterator.value())
            iterator += 1
    
    def _update_item_icon(self, item: QTreeWidgetItem) -> None:
        t = get_tree_tuple(item, 0)
        if not t:
            item.setIcon(0, QIcon())
            return
        item_type, item_id = t
        try:
            if item_type == "section":
                data = self.business.get_section_data(item_id)
            elif item_type == "category":
                data = self.business.get_category_data(item_id)
            else:
                item.setIcon(0, QIcon())
                return
            if data:
                self._set_tree_item_icon(item, item_type, data)
            else:
                item.setIcon(0, QIcon())
        except Exception:
            item.setIcon(0, QIcon())