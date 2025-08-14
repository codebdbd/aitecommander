# app/views/main_components/window_initializer.py

import os
import sys

from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.controllers.window_controllers_setup import WindowControllersSetup
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path, themed_icon
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.system.task_scheduler import LimitedThreadPool

# Компоненты для рефакторинга
from .window_ui_setup import WindowUISetup
from .common import create_font


class WindowInitializer:
    """Инициализатор главного окна - извлекает всю логику создания UI из __init__."""
    
    def __init__(self, main_window, db, settings, theme_ctrl):
        """
        Инициализация компонента.
        
        Args:
            main_window: Ссылка на главное окно
            db: База данных
            settings: Настройки приложения
            theme_ctrl: Контроллер тем
        """
        self.window = main_window
        self.db = db
        self.settings = settings
        self.theme_ctrl = theme_ctrl
        
        # Композиция компонентов (пока сохраняем старую логику для обратной совместимости)
        self.ui_setup = WindowUISetup(self)
        self.controllers_setup = WindowControllersSetup(self)
    
    def initialize_window(self):
        """Выполняет полную инициализацию главного окна."""
        # Блокируем обновления во время инициализации
        self.window.setUpdatesEnabled(False)
        
        try:
            # Используем новые компоненты (тестируем постепенно)
            self.ui_setup.setup_window_properties()
            self.ui_setup.setup_basic_attributes()
            self.ui_setup.setup_menu()
            self.ui_setup.setup_central_widget()
            
            # Получаем main_layout из UI компонента для совместимости со старыми методами
            self.main_layout = self.ui_setup.main_layout
            
            # Используем UI компонент для верхней панели
            self.ui_setup.setup_top_panel()
            
            # Используем UI компонент для основного содержимого
            self.ui_setup.setup_main_content()
            
            # Используем UI компонент для нижней панели и статус-бара
            self.ui_setup.setup_bottom_panel()
            self.ui_setup.setup_status_bar()
            
            # Используем контроллер компонент (должен быть до горячих клавиш)
            self.controllers_setup.setup_controllers()
            
            # Горячие клавиши после создания контроллеров
            self.ui_setup.setup_shortcuts()
        finally:
            # Включаем обновления после завершения инициализации
            self.window.setUpdatesEnabled(True)
            
        # Инициализация сфер выполняется асинхронно
        self.controllers_setup.initialize_spheres()
    
    # Старые методы _setup_* удалены - функциональность перенесена в WindowUISetup
    
    # Метод _setup_top_panel удален - функциональность в WindowUISetup.setup_top_panel()
    
    # Все методы _setup_* удалены - функциональность перенесена в WindowUISetup и WindowControllersSetup
