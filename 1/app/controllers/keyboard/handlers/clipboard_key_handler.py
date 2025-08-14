# app/controllers/keyboard/handlers/clipboard_key_handler.py

from typing import Any

from .base_key_handler import BaseKeyHandler


class ClipboardKeyHandler(BaseKeyHandler):
    """Обработчик клавиш буфера обмена."""
    
    def handle_select_all(self) -> None:
        """Выделить все в таблице."""
        table = self._safe_getattr(self.main_window, 'table')
        if table:
            self._safe_call(table, 'selectAll')
    
    def handle_copy(self) -> None:
        """Копировать выбранные ссылки."""
        links_controller = self._safe_getattr(self.main_window, 'links')
        if links_controller:
            self._safe_call(links_controller, 'copy_selected_links')
    
    def handle_cut(self) -> None:
        """Вырезать выбранные ссылки."""
        links_controller = self._safe_getattr(self.main_window, 'links')
        if links_controller:
            self._safe_call(links_controller, 'cut_selected_links')
    
    def handle_paste(self) -> None:
        """Вставить ссылки."""
        links_controller = self._safe_getattr(self.main_window, 'links')
        if links_controller:
            self._safe_call(links_controller, 'paste_links')
