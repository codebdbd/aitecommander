# app/controllers/keyboard/handlers/global_key_handler.py

from typing import Any

from .base_key_handler import BaseKeyHandler


class GlobalKeyHandler(BaseKeyHandler):
    """Обработчик глобальных горячих клавиш."""
    
    def handle_f1(self) -> None:
        """Показать диалог добавления ссылки."""
        self._safe_call(self.main_window, 'show_link_dialog')
    
    def handle_f2(self) -> None:
        """Редактировать текущий элемент."""
        self._safe_call(self.main_window, 'edit_current')
    
    def handle_f3(self) -> None:
        """Показать диалог добавления раздела."""
        self._safe_call(self.main_window, 'show_section_dialog')
    
    def handle_f4(self) -> None:
        """Показать диалог добавления категории."""
        self._safe_call(self.main_window, 'show_category_dialog')
    
    def handle_f6(self) -> None:
        """Переключить сферу."""
        action = self._safe_getattr(self.main_window, 'switch_sphere_action')
        if action:
            self._safe_call(action, 'trigger')
    
    def handle_delete(self) -> None:
        """Удалить текущий элемент."""
        self._safe_call(self.main_window, 'delete_current')
