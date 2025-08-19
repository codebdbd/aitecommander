"""Контроллер для управления всеми меню в приложении и обработки пользовательских действий."""
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple

from PyQt6.QtCore import QModelIndex
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QListWidget, QMenu, QMenuBar, QTreeWidget, QWidget

from app.config_data import app_config
from app.utils.ui.menu_builders import (
    CategoryMenuBuilder,
    LinksMenuBuilder,
    MainMenuBuilder,
    StructureMenuBuilder,
)

if TYPE_CHECKING:
    from app.main_window import MainWindow

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
            # Инъекция провайдера текущей категории и явных коллбеков для снижения связанности
            callbacks = {
                'get_link_at_row': self.main_window.get_link_at_row,
                'open_link': self.main_window.open_link,
                'show_link_dialog_for_category': self.main_window.show_link_dialog_for_category,
                'toggle_link_favorite': self.main_window.toggle_link_favorite,
                'copy_selected_links': self.main_window.copy_selected_links,
                'paste_links': self.main_window.paste_links,
                'cut_selected_links': self.main_window.cut_selected_links,
                'select_all_links': self.main_window.select_all_links,
                'show_note_dialog_for_link': self.main_window.show_note_dialog_for_link,
                'delete_selected_links': self.main_window.delete_selected_links,
            }
            self._links_menu_builder = LinksMenuBuilder(
                table_widget,
                self.main_window,
                get_current_category_id=self.main_window.get_current_category_id,
                callbacks=callbacks,
            )
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


class ActionController:
    """Контроллер для обработки пользовательских действий."""
    
    def __init__(self, main_window: 'MainWindow'):
        self.main_window = main_window
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def edit_current(self):
        """Определить контекст и выполнить редактирование текущего элемента."""
        # Проверяем плитки категорий
        tiles_stack_index = app_config.get('ui.stack_indices.tiles', 0)
        if (self.main_window.has_tiles and self.main_window.has_stack and 
            self.main_window.stack.currentIndex() == tiles_stack_index and 
            hasattr(self.main_window.tiles, '_current_item_id') and 
            self.main_window.tiles._current_item_id is not None):
            
            self.main_window.structure.handle_edit_category(self.main_window.tiles._current_item_id)
            return
        
        # Проверяем таблицу ссылок (активная)
        table_stack_index = app_config.get('ui.stack_indices.table', 1)
        if (self.main_window.has_stack and 
            self.main_window.stack.currentIndex() == table_stack_index and 
            self.main_window.links.has_selection()):
            self._edit_selected_link()
            return
        
        # Проверяем фокус на дереве структуры
        if (self.main_window.tree.hasFocus() and 
            self.main_window.tree.currentItem()):
            self.main_window.structure.edit_selected_item()
            return
        
        # Проверяем фокус на таблице ссылок
        if (self.main_window.table.hasFocus() and 
            self.main_window.links.has_selection()):
            self._edit_selected_link()
            return
        
        # Fallback: проверяем наличие выбранного элемента в дереве
        if self.main_window.tree.currentItem():
            self.main_window.structure.edit_selected_item()
            return
        
        # Fallback: проверяем наличие выбранной ссылки
        if self.main_window.links.has_selection():
            self._edit_selected_link()
    
    def delete_current(self):
        """Определить контекст и выполнить удаление текущего элемента."""
        # Проверяем фокус на таблице ссылок
        if ((self.main_window.table.hasFocus() or 
             self.main_window.table.isAncestorOf(self.main_window.focusWidget())) and 
            self.main_window.links.has_selection()):
            links = self._get_selected_links()
            if links:
                self.main_window.link_operations.delete_links_with_confirmation(links)
                self.main_window.update_statusbar()
            return

        # Проверяем фокус на дереве структуры
        if ((self.main_window.tree.hasFocus() or 
             self.main_window.tree.isAncestorOf(self.main_window.focusWidget())) and 
            self.main_window.tree.currentItem()):
            self.main_window.structure.delete_selected_item()
            self.main_window.update_statusbar()
            return

        # Fallback: проверяем наличие выбранных ссылок
        if self.main_window.links.has_selection():
            links = self._get_selected_links()
            if links:
                self.main_window.link_operations.delete_links_with_confirmation(links)
                self.main_window.update_statusbar()
            return

        # Fallback: проверяем наличие выбранного элемента в дереве
        if self.main_window.tree.currentItem():
            self.main_window.structure.delete_selected_item()
            self.main_window.update_statusbar()
    
    def copy_current(self):
        """Копировать выбранные элементы."""
        if self.main_window.links.has_selection():
            self.main_window.copy_selected_links()
    
    def cut_current(self):
        """Вырезать выбранные элементы."""
        if self.main_window.links.has_selection():
            self.main_window.cut_selected_links()
    
    def paste_current(self):
        """Вставить элементы."""
        self.main_window.paste_links()
    
    def select_all_current(self):
        """Выделить все элементы в текущем контексте."""
        if self.main_window.table.hasFocus():
            self.main_window.select_all_links()
    
    def _edit_selected_link(self):
        """Редактировать выбранную ссылку."""
        row = self.main_window.links.current_row()
        if row >= 0:
            link = self.main_window.links.get_link_by_row(row)
            if link:
                self.main_window.show_link_dialog(link)
    
    def _get_selected_links(self):
        """Получить список выбранных ссылок."""
        selected_rows = self.main_window.get_selected_rows()
        links = []
        for row in selected_rows:
            link = self.main_window.get_link_at_row(row)
            if link:
                links.append(link)
        return links
