# app/controllers/keyboard/handlers/base_key_handler.py

from typing import Any, Optional, TypeVar

from PyQt6.QtWidgets import QWidget

T = TypeVar('T')

# Константы для имен классов виджетов
WIDGET_CLASSES = {
    'STRUCTURE_TREE': 'StructureTreeWidget',
    'LINKS_TABLE': 'LinksTableView', 
    'CATEGORY_TILES': 'CategoryTiles'
}

WIDGET_OBJECT_NAMES = {
    'CATEGORY_TILES': 'tiles'
}


class BaseKeyHandler:
    """Базовый класс для обработчиков клавиш."""
    
    def __init__(self, main_window: Any) -> None:
        """Инициализация обработчика."""
        self.main_window = main_window
    
    def _is_widget_of_type(self, widget: Optional[QWidget], widget_type: str) -> bool:
        """Проверяет, является ли виджет указанного типа."""
        if not widget or widget_type not in WIDGET_CLASSES:
            return False
        
        class_name_to_check = WIDGET_CLASSES[widget_type]
        object_name_to_check = WIDGET_OBJECT_NAMES.get(widget_type)
        
        current = widget
        while current:
            class_name = current.__class__.__name__
            if class_name_to_check in class_name:
                return True
            if (object_name_to_check and hasattr(current, 'objectName') 
                and object_name_to_check in current.objectName().lower()):
                return True
            current = current.parent()
        
        return False
    
    def _is_tree_focused(self, widget: Optional[QWidget]) -> bool:
        """Проверяет фокус на дереве структуры."""
        return self._is_widget_of_type(widget, 'STRUCTURE_TREE')
    
    def _is_table_focused(self, widget: Optional[QWidget]) -> bool:
        """Проверяет фокус на таблице ссылок."""
        return self._is_widget_of_type(widget, 'LINKS_TABLE')
    
    def _is_tiles_focused(self, widget: Optional[QWidget]) -> bool:
        """Проверяет фокус на плитках категорий."""
        return self._is_widget_of_type(widget, 'CATEGORY_TILES')
    
    def _safe_getattr(self, obj: Any, attr: str, default: T = None) -> Any:
        """Безопасное получение атрибута с обработкой исключений."""
        try:
            return getattr(obj, attr, default)
        except (AttributeError, TypeError):
            return default
    
    def _safe_call(self, obj: Any, method_name: str, *args: Any, default: T = None, **kwargs: Any) -> Any:
        """Безопасный вызов метода с обработкой исключений."""
        try:
            method = getattr(obj, method_name, None)
            if method and callable(method):
                result = method(*args, **kwargs)
                return result if result is not None else default
        except (AttributeError, TypeError):
            pass
        return default
