"""Строитель контекстного меню для плиток категорий."""
import logging
from typing import TYPE_CHECKING, Any, Callable, Tuple

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QListWidget, QMenu

from app.utils.ui.icon.icon_operations.creators import themed_icon
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.menu_actions import ActionBuilder, Shortcuts

if TYPE_CHECKING:
    from app.main_window import MainWindow

logger = logging.getLogger(__name__)


class CategoryMenuBuilder:
    """Строитель контекстного меню для плиток категорий."""
    
    def __init__(self, list_widget: QListWidget, main_window: 'MainWindow'):
        self.list_widget = list_widget
        self.main_window = main_window
        self.actions = ActionBuilder(list_widget)
    
    def build(self, item_id: Any, edit_cb: Callable, delete_cb: Callable, 
              add_link_cb: Callable) -> Tuple[QMenu, QAction, QAction, QAction]:
        """Создаёт контекстное меню для плитки категории.
        
        Меню унифицировано с деревом структуры и содержит:
        - Редактировать категорию
        - Добавить ссылку
        - Разделитель
        - Удалить категорию
        """
        menu = QMenu(self.list_widget)
        
        # Редактировать категорию
        edit_action = self.actions.create(
            "Редактировать категорию", 
            lambda: edit_cb(item_id),
            Shortcuts.EDIT,
            self._get_icon('edit')
        )
        
        # Добавить ссылку
        add_link_action = self.actions.create(
            "Добавить ссылку", 
            lambda: add_link_cb(item_id),
            Shortcuts.ADD_LINK,
            self._get_icon('add_link')
        )
        
        # Удалить категорию
        delete_action = self.actions.create(
            "Удалить категорию", 
            lambda: delete_cb(item_id),
            Shortcuts.DELETE,
            self._get_icon('delete')
        )
        
        menu.addAction(edit_action)
        menu.addAction(add_link_action)
        menu.addSeparator()
        menu.addAction(delete_action)
        
        return menu, edit_action, delete_action, add_link_action
    
    def _get_icon(self, name: str):
        """Получить иконку с учётом темы."""
        theme = get_current_theme()
        # Маппинг имен иконок на файлы (унифицировано с деревом структуры)
        icon_files = {
            'edit': 'edit.svg',
            'add_link': 'add_link.svg',
            'delete': 'delete.svg'
        }
        icon_file = icon_files.get(name, f'{name}.svg')
        return themed_icon(icon_file, theme, 'context_menu')
