"""Строитель контекстного меню для дерева структуры."""
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QTreeWidget

from app.utils.ui.menu_actions import ActionBuilder, Shortcuts, StructureItemType
from app.utils.ui.qt.roles import get_tree_tuple
from .base import get_menu_icon

if TYPE_CHECKING:
    from app.main_window import MainWindow

logger = logging.getLogger(__name__)


class StructureMenuBuilder:
    """Строитель контекстного меню для дерева структуры."""
    
    def __init__(self, tree_widget: QTreeWidget, main_window: 'MainWindow'):
        self.tree_widget = tree_widget
        self.main_window = main_window
        self.actions = ActionBuilder(tree_widget)
        self.theme = main_window.settings.get_theme()
    
    def build(self, item: Optional[Any], delete_item_cb: Callable, 
              add_new_section_cb: Callable, sort_tree_cb: Callable) -> QMenu:
        """Создаёт контекстное меню для дерева структуры."""
        menu = QMenu(self.tree_widget)
        
        if item:
            self._add_item_actions(menu, item, delete_item_cb)
        else:
            self._add_root_actions(menu, add_new_section_cb, sort_tree_cb)
        
        return menu
    
    
    
    def _add_item_actions(self, menu: QMenu, item: Any, delete_item_cb: Callable):
        """Добавляет действия для выбранного элемента."""
        t = get_tree_tuple(item, 0)
        if not t:
            logger.warning("Invalid item data in context menu: None")
            return
        typ, id_ = t
        if typ not in (StructureItemType.SECTION, StructureItemType.CATEGORY):
            logger.warning(f"Unknown item type in context menu: {typ}")
            return
        
        if typ == StructureItemType.SECTION:
            self._add_section_actions(menu, item, delete_item_cb)
        elif typ == StructureItemType.CATEGORY:
            self._add_category_actions(menu, item, id_, delete_item_cb)
    
    def _add_section_actions(self, menu: QMenu, item: Any, delete_item_cb: Callable):
        """Добавляет действия для раздела."""
        menu.addAction(self.actions.create(
            "Редактировать раздел", 
            lambda: self.main_window.edit_structure_item(item),
            Shortcuts.EDIT,
            get_menu_icon('edit', self.theme)
        ))
        
        menu.addAction(self.actions.create(
            "Добавить категорию", 
            self.main_window.add_new_category,
            Shortcuts.ADD_CATEGORY,
            get_menu_icon('add_category', self.theme)
        ))
        
        menu.addSeparator()
        
        menu.addAction(self.actions.create(
            "Удалить раздел", 
            lambda: delete_item_cb(item),
            Shortcuts.DELETE,
            get_menu_icon('delete', self.theme)
        ))
    
    def _add_category_actions(self, menu: QMenu, item: Any, id_: Any, delete_item_cb: Callable):
        """Добавляет действия для категории."""
        menu.addAction(self.actions.create(
            "Редактировать категорию", 
            lambda: self.main_window.edit_structure_item(item),
            Shortcuts.EDIT,
            get_menu_icon('edit', self.theme)
        ))
        
        menu.addAction(self.actions.create(
            "Добавить ссылку", 
            lambda: self.main_window.show_link_dialog_for_category(category_id=id_),
            Shortcuts.ADD_LINK,
            get_menu_icon('add_link', self.theme)
        ))
        
        menu.addSeparator()
        
        menu.addAction(self.actions.create(
            "Удалить категорию", 
            lambda: delete_item_cb(item),
            Shortcuts.DELETE,
            get_menu_icon('delete', self.theme)
        ))
    
    def _add_root_actions(self, menu: QMenu, add_new_section_cb: Callable, sort_tree_cb: Callable):
        """Добавляет действия для корневого уровня."""
        menu.addAction(self.actions.create(
            "Добавить раздел", 
            add_new_section_cb,
            Shortcuts.ADD_SECTION,
            get_menu_icon('add_section', self.theme)
        ))
        
        menu.addSeparator()
        
        menu.addAction(self.actions.create(
            "Сортировать категории", 
            sort_tree_cb,
            Shortcuts.SORT,
            get_menu_icon('sort', self.theme)
        ))
