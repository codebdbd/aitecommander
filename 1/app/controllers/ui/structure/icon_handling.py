# app/controllers/structure/icon_handling.py

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QTreeWidgetItem, QTreeWidgetItemIterator

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.qt.roles import get_tree_tuple


class IconHandling:
    def __init__(self, controller):
        self.controller = controller
        self.tree = controller.tree
        self.business = controller.business
    
    def _get_icon_for_item(self, item_type: str, icon_name: str) -> QIcon:
        default_icons = app_config.get_default_icons()
        default_icon = default_icons.get("section") if item_type == "section" else default_icons.get("category")
        icon_file = icon_name or default_icon
        
        # Если icon_file пустая, используем иконку по умолчанию
        if not icon_file:
            icon_file = default_icon
        
        # Проверяем пользовательские иконки
        icon_path = icon_path_service.get_user_icons_dir() / icon_file
        if icon_path.exists():
            return create_icon_from_path(str(icon_path))
        
        # Проверяем UI иконки
        icon_path = icon_path_service.get_ui_icons_dir() / icon_file
        if icon_path.exists():
            return create_icon_from_path(str(icon_path))
        
        # Если иконка не найдена, используем иконку по умолчанию
        if default_icon:
            icon_path = icon_path_service.get_ui_icons_dir() / default_icon
            if icon_path.exists():
                return create_icon_from_path(str(icon_path))
        
        # Если ничего не найдено, возвращаем пустую иконку
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