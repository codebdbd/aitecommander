# app/controllers/keyboard/keyboard_manager.py

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication

from .handlers.clipboard_key_handler import ClipboardKeyHandler
from .handlers.editing_key_handler import EditingKeyHandler
from .handlers.global_key_handler import GlobalKeyHandler
from .handlers.search_key_handler import SearchKeyHandler


class KeyboardManager(QObject):
    """Централизованный менеджер горячих клавиш."""
    
    ENTER_COOLDOWN = 150
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.shortcuts = []
        
        self.global_handler = GlobalKeyHandler(main_window)
        self.editing_handler = EditingKeyHandler(main_window)
        self.clipboard_handler = ClipboardKeyHandler(main_window)
        self.search_handler = SearchKeyHandler(main_window)
        
        self._last_enter_time = 0
        
        self.main_window.installEventFilter(self)
        self._setup_shortcuts()

    
    def _setup_shortcuts(self):
        """Настройка QShortcut для комбинаций клавиш."""

        global_shortcuts = [
            ("F1", self.global_handler.handle_f1),
            ("F2", self.global_handler.handle_f2),
            ("F3", self.global_handler.handle_f3),
            ("F4", self.global_handler.handle_f4),
            ("F6", self.global_handler.handle_f6),
            ("Del", self.global_handler.handle_delete),
        ]
        
        for key_seq, handler in global_shortcuts:
            shortcut = QShortcut(QKeySequence(key_seq), self.main_window)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)
        

        table_shortcuts = [
            ("Ctrl+A", self.clipboard_handler.handle_select_all),
            ("Ctrl+F", self.search_handler.handle_focus_search),
            ("Escape", self.search_handler.handle_clear_search),
            ("Ctrl+X", self.clipboard_handler.handle_cut),
            ("Ctrl+C", self.clipboard_handler.handle_copy),
            ("Ctrl+V", self.clipboard_handler.handle_paste),
            ("Ctrl+N", self.editing_handler.handle_show_note),
            ("Ctrl+D", self.editing_handler.handle_toggle_favorite),
        ]
        
        table = getattr(self.main_window, 'table', None)
        if table:
            for key_seq, handler in table_shortcuts:
                shortcut = QShortcut(QKeySequence(key_seq), table)
                shortcut.activated.connect(handler)
                self.shortcuts.append(shortcut)
    

    
    def eventFilter(self, obj, event):
        """Фильтр событий для перехвата клавиш."""
        if event.type() == event.Type.KeyPress:
            if self._is_enter_duplicate(event):
                return True
            
            focused_widget = QApplication.focusWidget()
            
            if self._handle_editing_keys(event, focused_widget):
                return True
            elif self._handle_search_keys(event, focused_widget):
                return True
        
        return super().eventFilter(obj, event)
    
    def _is_enter_duplicate(self, event):
        """Проверка на двойное нажатие Enter."""
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            import time
            current_time = int(time.time() * 1000)
            
            if current_time - self._last_enter_time < self.ENTER_COOLDOWN:
                return True
            
            self._last_enter_time = current_time
        
        return False
    
    def _handle_editing_keys(self, event, focused_widget):
        """Обработка клавиш редактирования."""
        key = event.key()
        
        if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape):
            return self.editing_handler.handle_key(event, focused_widget)
        
        return False
    
    def _handle_search_keys(self, event, focused_widget):
        """Обработка клавиш поиска."""
        if (event.text().isalnum() and len(event.text()) == 1 and
            self.search_handler._is_tiles_focused(focused_widget)):
            return self.search_handler.handle_quick_search(event, focused_widget)
        
        return False
    

    
    def cleanup(self):
        """Очистка ресурсов."""
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts.clear()
        
        # Удаляем фильтр событий
        self.main_window.removeEventFilter(self)
