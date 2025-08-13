"""Создание действий для меню."""
import logging
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class ActionBuilder:
    """Строитель действий меню с обработкой ошибок."""
    
    def __init__(self, parent: QWidget):
        self.parent = parent
    
    def create(self, text: str, callback: Optional[Callable] = None, 
               shortcut: Optional[str] = None, icon: Optional[QIcon] = None) -> QAction:
        """Создать действие меню."""
        action = QAction(text, self.parent)
        
        if icon:
            action.setIcon(icon)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutVisibleInContextMenu(True)
            action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        if callback:
            action.triggered.connect(lambda: self._safe_call(callback))
        
        return action
    
    def _safe_call(self, callback: Callable):
        """Безопасный вызов коллбека с обработкой ошибок."""
        try:
            callback()
        except Exception as e:
            logger.error(f"Ошибка выполнения действия меню: {e}")
            if hasattr(self.parent, 'show_error_message'):
                self.parent.show_error_message(f"Ошибка: {str(e)}")


# Константы горячих клавиш
class Shortcuts:
    EDIT = "F2"
    ADD_LINK = "F1"
    ADD_SECTION = "F3"
    ADD_CATEGORY = "F4"
    SORT = "F5"
    DELETE = "Del"
    ENTER = "Enter"
    CTRL_D = "Ctrl+D"
    CTRL_F = "Ctrl+F"
    CTRL_C = "Ctrl+C"
    CTRL_V = "Ctrl+V"
    CTRL_X = "Ctrl+X"
    CTRL_A = "Ctrl+A"
    CTRL_N = "Ctrl+N"
    CTRL_S = "Ctrl+S"


class StructureItemType:
    """Типы элементов в дереве структуры."""
    SECTION = "section"
    CATEGORY = "category"
