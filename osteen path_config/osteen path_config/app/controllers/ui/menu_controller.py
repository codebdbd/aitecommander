"""Контроллер для управления всеми меню в приложении и обработки пользовательских действий."""
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple

from PyQt6.QtCore import QModelIndex
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QListWidget, QMenu, QMenuBar, QTreeWidget, QWidget

from app.utils.ui.menu_builders import (
    CategoryMenuBuilder,
    LinksMenuBuilder,
    MainMenuBuilder,
    StructureMenuBuilder,
)

if TYPE_CHECKING:
    from app.views.main_window import MainWindow

logger = logging.getLogger(__name__)


class MenuController:
    """Контроллер для управления всеми меню в приложении."""
    
    def __init__(self, main_window: 'MainWindow'):
        self.main_window = main_window
        self._main_menu_builder = None
        self._structure_menu_builder = None
        self._links_menu_builder = None
        self._category_menu_builder = None
    
    def create_main_menu(self) -> QMenuBar:
        """Создаёт главное меню."""
        if not self._main_menu_builder:
            self._main_menu_builder = MainMenuBuilder(self.main_window)
        return self._main_menu_builder.build()
    
    def create_structure_context_menu(self, tree_widget: QTreeWidget, item: Optional[Any],
                                    delete_item_cb: Callable, add_new_section_cb: Callable, 
                                    sort_tree_cb: Callable) -> QMenu:
        """Создаёт контекстное меню для дерева структуры."""
        if not self._structure_menu_builder:
            self._structure_menu_builder = StructureMenuBuilder(tree_widget, self.main_window)
        return self._structure_menu_builder.build(item, delete_item_cb, add_new_section_cb, sort_tree_cb)
    
    def create_links_context_menu(self, table_widget: QWidget, idx: QModelIndex, 
                                paste_link_cb: Callable) -> QMenu:
        """Создаёт контекстное меню для таблицы ссылок."""
        if not self._links_menu_builder:
            self._links_menu_builder = LinksMenuBuilder(table_widget, self.main_window)
        return self._links_menu_builder.build(idx, paste_link_cb)
    
    def create_category_tile_context_menu(self, list_widget: QListWidget, item_id: Any,
                                        edit_cb: Callable, delete_cb: Callable, 
                                        add_cb: Callable) -> Tuple[QMenu, QAction, QAction, QAction]:
        """Создаёт контекстное меню для плитки категории."""
        if not self._category_menu_builder:
            self._category_menu_builder = CategoryMenuBuilder(list_widget, self.main_window)
        return self._category_menu_builder.build(item_id, edit_cb, delete_cb, add_cb)
    
    def clear_cache(self):
        """Очищает кеш строителей меню (например, при смене темы)."""
        from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
        icon_cache.clear_cache()
        
        # Пересоздаём строители при следующем использовании
        self._main_menu_builder = None
        self._structure_menu_builder = None
        self._links_menu_builder = None
        self._category_menu_builder = None

    def rebuild_after_theme_change(self) -> None:
        """Пересобирает главное меню после смены темы.
        Инкапсулирует очистку кеша и пересоздание меню.
        """
        try:
            old_menu = self.main_window.menuBar()
            if old_menu is not None:
                old_menu.deleteLater()
        except Exception:
            # В случае, если меню ещё не инициализировалось
            pass
        
        self.clear_cache()
        self.main_window.setMenuBar(self.create_main_menu())
