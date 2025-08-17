"""Строитель главного меню приложения."""
import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QModelIndex
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QMenuBar

from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
from app.utils.ui.menu_actions import ActionBuilder, Shortcuts

if TYPE_CHECKING:
    from app.main_window import MainWindow

logger = logging.getLogger(__name__)


class MainMenuBuilder:
    """Строитель для главного меню приложения."""
    
    def __init__(self, main_window: 'MainWindow'):
        self.main_window = main_window
        self.actions = ActionBuilder(main_window)
        self.theme = main_window.settings.get_theme()
    
    def build(self) -> QMenuBar:
        """Создаёт и возвращает готовое главное меню."""
        logger.debug(f"Создание главного меню для темы: {self.theme}")
        
        menubar = QMenuBar(self.main_window)
        
        self._create_file_menu(menubar)
        self._create_search_menu(menubar)
        self._create_edit_menu(menubar)
        self._create_themes_menu(menubar)
        self._create_help_menu(menubar)
        
        return menubar
    
    def _get_icon(self, name: str, source: str = 'main_menu'):
        """Получить иконку с учётом темы."""
        return icon_cache.get_icon(name, self.theme, source)
    
    def _create_file_menu(self, menubar: QMenuBar):
        """Создаёт меню 'Файл'."""
        file_menu = menubar.addMenu("&Файл")
        
        # Настройки
        file_menu.addAction(self.actions.create(
            "Настройки...", 
            self.main_window.show_settings_dialog,
            icon=self._get_icon('settings')
        ))
        
        # Очистить избранное
        file_menu.addAction(self.actions.create(
            "Очистить избранное...",
            self._clear_favorites,
            icon=self._get_icon('delete')
        ))
        
        # Импорт из браузера
        file_menu.addAction(self.actions.create(
            "Импорт из браузера",
            self.main_window.handle_import_browser_bookmarks,
            icon=self._get_icon('import')
        ))
        
        file_menu.addSeparator()
        
        # Операции с базой данных
        file_menu.addAction(self.actions.create(
            "Восстановить базу...",
            self._restore_database,
            icon=self._get_icon('dbrestore')
        ))
        
        file_menu.addAction(self.actions.create(
            "Подключить базу...",
            self._connect_database,
            icon=self._get_icon('import')
        ))
        
        file_menu.addAction(self.actions.create(
            "Сохранить базу...",
            self._save_database,
            icon=self._get_icon('export')
        ))
        
        file_menu.addSeparator()
        
        # Операции с иконками
        file_menu.addAction(self.actions.create(
            "Сохранить иконки...",
            self._save_icons,
            icon=self._get_icon('zip_ico')
        ))
        
        file_menu.addAction(self.actions.create(
            "Вставить иконки...",
            self._load_icons,
            icon=self._get_icon('add_ico')
        ))
        
        file_menu.addSeparator()
        
        # Выход
        file_menu.addAction(self.actions.create(
            "Выход", 
            self.main_window.close,
            icon=self._get_icon('exit')
        ))
    
    def _create_search_menu(self, menubar: QMenuBar):
        """Создаёт меню 'Поиск'."""
        search_menu = menubar.addMenu("&Поиск")
        search_menu.addAction(self.actions.create(
            "Поиск файлов...",
            self.main_window.show_file_search_dialog,
            icon=self._get_icon('search')
        ))
    
    def _create_edit_menu(self, menubar: QMenuBar):
        """Создаёт меню 'Правка'."""
        edit_menu = menubar.addMenu("&Правка")
        
        # Создание undo/redo действий через публичный метод
        undo_action, redo_action = self.main_window.create_undo_redo_actions()
        
        if undo_action and redo_action:
            undo_action.setIcon(self._get_icon('undo'))
            redo_action.setIcon(self._get_icon('redo'))
        
        # Действия структуры и ссылок
        edit_menu.addAction(self.actions.create(
            "Добавить раздел",
            self.main_window.show_section_dialog,
            Shortcuts.ADD_SECTION,
            self._get_icon('add_section')
        ))
        edit_menu.addAction(self.actions.create(
            "Добавить категорию",
            self.main_window.show_category_dialog,
            Shortcuts.ADD_CATEGORY,
            self._get_icon('add_category')
        ))
        edit_menu.addAction(self.actions.create(
            "Добавить ссылку",
            lambda: self.main_window.show_link_dialog_for_category(
                category_id=self.main_window.get_current_category_id()
            ),
            Shortcuts.ADD_LINK,
            self._get_icon('add_link')
        ))
        
        edit_menu.addSeparator()
        
        edit_menu.addAction(self.actions.create(
            "Редактировать",
            self.main_window.edit_current,
            Shortcuts.EDIT,
            self._get_icon('edit')
        ))
        edit_menu.addAction(self.actions.create(
            "Удалить",
            self.main_window.delete_current,
            Shortcuts.DELETE,
            self._get_icon('delete')
        ))
        
        edit_menu.addSeparator()
        
        # Undo/Redo в конце группы правки
        edit_menu.addAction(self.main_window.undo_action)
        edit_menu.addAction(self.main_window.redo_action)
    
    def _create_themes_menu(self, menubar: QMenuBar):
        """Создаёт меню 'Темы'."""
        themes_menu = menubar.addMenu("&Темы")
        
        theme_icons = {
            'dark': self._get_icon('dark'),
            'light': self._get_icon('light')
        }
        
        for name, display_name in self.main_window.get_available_themes():
            icon = theme_icons.get(name) or self._get_icon(name)
            
            # Создаем функцию с правильным замыканием для каждой темы
            def make_theme_handler(theme_name):
                return lambda: self.main_window.apply_theme(theme_name)
            
            action = self.actions.create(
                display_name, 
                make_theme_handler(name),
                icon=icon
            )
            themes_menu.addAction(action)
    
    def _create_help_menu(self, menubar: QMenuBar):
        """Создаёт меню 'Справка'."""
        help_menu = menubar.addMenu("&Справка")
        help_menu.addAction(self.actions.create(
            "О программе", 
            self.main_window.show_about_dialog,
            icon=self._get_icon('help')
        ))
    
    # Методы для действий меню
    
    def _clear_favorites(self):
        """Очистить избранное - делегирование в DialogController."""
        if hasattr(self.main_window, 'database_controller'):
            self.main_window.database_controller.handle_clear_favorites()
    
    def _restore_database(self):
        """Восстановить базу данных - делегирование в DialogController."""
        if hasattr(self.main_window, 'database_controller'):
            self.main_window.database_controller.handle_restore_database()
    
    def _connect_database(self):
        """Подключить другую базу данных - делегирование в DialogController."""
        if hasattr(self.main_window, 'database_controller'):
            self.main_window.database_controller.handle_connect_database()
    

    
    def _save_database(self):
        """Сохранить копию базы данных - делегирование в DialogController."""
        if hasattr(self.main_window, 'database_controller'):
            self.main_window.database_controller.handle_save_database()
    
    def _save_icons(self):
        """Сохранить архив иконок - делегирование в DialogController."""
        if hasattr(self.main_window, 'database_controller'):
            self.main_window.database_controller.handle_save_icons()
    
    def _load_icons(self):
        """Загрузить архив иконок - делегирование в DialogController."""
        if hasattr(self.main_window, 'database_controller'):
            self.main_window.database_controller.handle_load_icons()
