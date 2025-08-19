# app/controllers/commands/base.py

import logging

from app.utils.db.db_error_handler import handle_db_error
from app.utils.ui.dialog_manager import DialogManager, DialogMixin
from app.utils.system.undo.base import BaseCommand as UtilsBaseCommand


class BaseCommand(UtilsBaseCommand, DialogMixin):
    """Базовый класс для всех команд, чтобы передавать общие зависимости."""
    def __init__(self, description, main_window, parent=None):
        # parent оставляем в сигнатуре для совместимости, но QUndoCommand-предок управляется в UtilsBaseCommand
        super().__init__(description, main_window)
        self.main = main_window
        self.db = main_window.db
        self.structure = main_window.structure
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def update_links_table(self, category_id: int) -> None:
        """Обновить таблицу ссылок для указанной категории.
        
        ЦЕНТРАЛИЗОВАНО: Использует UIStateManager.load_category() вместо дублированной логики.
        """
        if hasattr(self.main, 'ui_state') and self.main.ui_state:
            success = self.main.ui_state.load_category(category_id, source=self.__class__.__name__)
            if not success:
                self.logger.error(f"Failed to load category {category_id} in {self.__class__.__name__}")
        else:
            self.logger.critical(f"UIStateManager not available in {self.__class__.__name__} - critical architecture error")
    
    def update_favorites(self) -> None:
        """Обновить панель избранного."""
        if hasattr(self.main, 'fav_widget') and self.main.fav_widget:
            self.main.fav_widget.update_favorites()
    
    def update_structure_tree(self, item_to_select=None) -> None:
        """Обновить дерево структуры."""
        if hasattr(self.main, 'structure') and self.main.structure:
            self.main.structure.load(item_to_select)
    
    def refresh_all_views(self, category_id: int = None, item_to_select=None) -> None:
        """Обновить все связанные представления."""
        if category_id:
            self.update_links_table(category_id)
        self.update_favorites()
        if item_to_select:
            self.update_structure_tree(item_to_select)
    
    def show_error(self, message: str, title: str = "Ошибка", parent=None) -> None:
        """Показать диалог ошибки.
        ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox.
        """
        parent = parent or self.main
        DialogManager.show_error(parent, message, title)
    
    def show_warning(self, message: str, title: str = "Предупреждение", parent=None) -> None:
        """Показать диалог предупреждения.
        ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox.
        """
        parent = parent or self.main
        DialogManager.show_warning(parent, message, title)
    
    def show_info(self, message: str, title: str = "Информация", parent=None) -> None:
        """Показать информационный диалог.
        ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox.
        """
        parent = parent or self.main
        DialogManager.show_info(parent, message, title)
    
    def show_question(self, message: str, title: str = "Подтверждение", parent=None) -> bool:
        """Показать диалог подтверждения. Возвращает True если пользователь согласен.
        ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox.
        """
        parent = parent or self.main
        return DialogManager.ask_confirmation(parent, message, title)
    
    def handle_db_error(self, error: Exception) -> bool:
        """Обработать ошибку базы данных с помощью централизованного обработчика."""
        return handle_db_error(error, self)
    
    @staticmethod
    def show_error_static(parent, message: str, title: str = "Ошибка") -> None:
        """Статический метод для показа диалога ошибки.
        ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox.
        """
        DialogManager.show_error(parent, message, title)
    
    @staticmethod
    def show_info_static(parent, message: str, title: str = "Информация") -> None:
        """Статический метод для показа информационного диалога.
        ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox.
        """
        DialogManager.show_info(parent, message, title)
    
    @staticmethod
    def show_question_static(parent, message: str, title: str = "Подтверждение") -> bool:
        """Статический метод для показа диалога подтверждения. Возвращает True если пользователь согласен.
        ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox.
        """
        return DialogManager.ask_confirmation(parent, message, title)
    
    @staticmethod
    def show_warning_static(parent, message: str, title: str = "Предупреждение") -> None:
        """Статический метод для показа диалога предупреждения.
        ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox.
        """
        DialogManager.show_warning(parent, message, title)
    
    def load_structure_with_selection(self, item_to_select=None):
        """Централизованная загрузка структуры с восстановлением выделения."""
        if hasattr(self.main, 'structure') and self.main.structure:
            self.main.structure.load(item_to_select=item_to_select)
    
    def restore_tree_selection(self, item_type: str, item_id: int):
        """Централизованное восстановление выделения в дереве."""
        if hasattr(self.main, 'structure') and hasattr(self.main.structure, 'selection_handler'):
            self.main.structure.selection_handler._restore_selection_after_load(item_type, item_id)
    
    def reload_structure_tree(self, item_to_select=None):
        """Полная перезагрузка дерева структуры с опциональным выделением."""
        # Используем item_operations для полной загрузки
        if hasattr(self.main, 'structure') and hasattr(self.main.structure, 'item_ops'):
            self.main.structure.item_ops.load(item_to_select=item_to_select)
    
    def reload_business_structure(self):
        """Перезагрузка бизнес-структуры (используется при смене сферы)."""
        if hasattr(self.main, 'structure') and hasattr(self.main.structure, 'business'):
            self.main.structure.business.load_structure()