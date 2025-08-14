# app/controllers/keyboard/handlers/search_key_handler.py

from typing import Any, Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QWidget

from .base_key_handler import BaseKeyHandler


class SearchKeyHandler(BaseKeyHandler):
    """Обработчик клавиш поиска."""
    
    SEARCH_TIMEOUT = 1000
    
    def __init__(self, main_window: Any) -> None:
        """Инициализация обработчика поиска."""
        super().__init__(main_window)
        self._search_text: str = ""
        self._search_timer: QTimer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._reset_search)
    
    def handle_focus_search(self) -> None:
        """Перевод фокуса на поле поиска."""
        search = self._safe_getattr(self.main_window, 'search')
        if search:
            self._safe_call(search, 'setFocus')
    
    def handle_clear_search(self) -> None:
        """Очистка поля поиска."""
        search = self._safe_getattr(self.main_window, 'search')
        if search:
            self._safe_call(search, 'clear')
    
    def handle_quick_search(self, event: QKeyEvent, focused_widget: Optional[QWidget]) -> bool:
        """Быстрый поиск по первой букве в плитках."""
        if not self._is_tiles_focused(focused_widget):
            return False
        
        char = event.text().lower()
        self._search_timer.stop()
        self._search_text += char
        self._search_timer.start(self.SEARCH_TIMEOUT)
        
        tiles = self._safe_getattr(self.main_window, 'tiles')
        if tiles:
            result = self._safe_call(tiles, '_quick_search', self._search_text, default=False)
            return bool(result)
        
        return False
    
    def _reset_search(self) -> None:
        """Сброс текста поиска."""
        self._search_text = ""
