# app/controllers/keyboard/handlers/editing_key_handler.py

from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QWidget

from .base_key_handler import BaseKeyHandler


class EditingKeyHandler(BaseKeyHandler):
    """Обработчик клавиш редактирования."""
    
    def handle_key(self, event: QKeyEvent, focused_widget: Optional[QWidget]) -> bool:
        """Обработка клавиш редактирования в зависимости от контекста."""
        key = event.key()
        
        if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            return self._handle_enter_key(focused_widget)
        elif key == Qt.Key.Key_Escape:
            return self._handle_escape_key(focused_widget)
        
        return False
    
    def _handle_enter_key(self, focused_widget: Optional[QWidget]) -> bool:
        """Обработка клавиши Enter в зависимости от контекста."""
        # В дереве - ничего не делаем, навигация только стрелками
        if self._is_tree_focused(focused_widget):
            return False
        
        # В плитках - открытие категории (обрабатываем первым, чтобы избежать конфликта с таблицей)
        elif self._is_tiles_focused(focused_widget):
            return self._handle_tiles_enter()
        
        # В таблице - открытие ссылки
        elif self._is_table_focused(focused_widget):
            return self._handle_table_enter()
        
        return False
    
    def _handle_escape_key(self, focused_widget: Optional[QWidget]) -> bool:
        """Обработка клавиши Escape в зависимости от контекста."""
        # В плитках - очистка фильтра
        if self._is_tiles_focused(focused_widget):
            return self._handle_tiles_escape()
        
        # Глобально - очистка поиска
        return self._handle_global_escape()
    
    def _handle_table_enter(self) -> bool:
        """Открытие ссылки в таблице."""
        table = self._safe_getattr(self.main_window, 'table')
        if not table:
            return False
        
        current_row = self._safe_call(table, 'currentRow', default=-1)
        row_count = self._safe_call(table, 'rowCount', default=0)
        if current_row >= 0 and current_row < row_count:
            link = self._safe_call(table, 'get_link_at', current_row)
            if link:
                links = self._safe_getattr(self.main_window, 'links')
                if links:
                    link_ops = self._safe_getattr(links, 'link_ops')
                    if link_ops:
                        self._safe_call(link_ops, '_open_link', link)
                        return True
        
        return False
    
    def _handle_tiles_enter(self) -> bool:
        """Открытие категории в плитках."""
        tiles = self._safe_getattr(self.main_window, 'tiles')
        if not tiles:
            return False
        
        list_widget = self._safe_getattr(tiles, 'list_widget')
        if list_widget:
            current_item = self._safe_call(list_widget, 'currentItem')
            if current_item:
                result = self._safe_call(tiles, '_on_item_clicked', current_item, default=False)
                return bool(result)
        
        return False
    
    def _handle_tiles_escape(self) -> bool:
        """Очистка фильтра в плитках."""
        tiles = self._safe_getattr(self.main_window, 'tiles')
        if tiles:
            filter_text = self._safe_getattr(tiles, '_filter_text')
            if filter_text:
                result = self._safe_call(tiles, 'clear_filter', default=False)
                return bool(result)
        
        return False
    
    def _handle_global_escape(self) -> bool:
        """Глобальная очистка поиска."""
        search = self._safe_getattr(self.main_window, 'search')
        if search and self._safe_call(search, 'text', default=''):
            self._safe_call(search, 'clear')
            return True
        
        return False
    
    def handle_show_note(self) -> None:
        """Показать заметку для текущей ссылки."""
        links = self._safe_getattr(self.main_window, 'links')
        if links:
            selected_links = self._safe_call(links, 'get_selected_links')
            if selected_links:
                self._safe_call(links, 'show_note_dialog', selected_links[0])
    
    def handle_toggle_favorite(self) -> None:
        """Переключить избранное для текущей ссылки."""
        links = self._safe_getattr(self.main_window, 'links')
        if links:
            selected_links = self._safe_call(links, 'get_selected_links')
            if selected_links:
                self._safe_call(self.main_window, 'toggle_link_favorite', selected_links[0])
    

