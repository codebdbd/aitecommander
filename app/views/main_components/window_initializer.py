# app/views/main_components/window_initializer.py

import logging
import time

from app.controllers.system.window_controllers_setup import WindowControllersSetup

# Компоненты для рефакторинга
from .window_ui_setup import WindowUISetup


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
        t_total0 = time.perf_counter()
        # Блокируем обновления во время инициализации
        self.window.setUpdatesEnabled(False)

        try:
            # Базовые UI свойства и окружение
            for name, fn in (
                ("window_properties", self.ui_setup.setup_window_properties),
                ("basic_attributes", self.ui_setup.setup_basic_attributes),
                ("menu", self.ui_setup.setup_menu),
                ("central_widget", self.ui_setup.setup_central_widget),
            ):
                t0 = time.perf_counter()
                fn()
                t1 = time.perf_counter()
                logging.info(f"WindowInit: {name} took {(t1 - t0)*1000:.1f} ms")

            # Получаем main_layout из UI компонента для совместимости со старыми методами
            self.main_layout = self.ui_setup.main_layout

            # Верхняя панель
            t0 = time.perf_counter()
            self.ui_setup.setup_top_panel()
            t1 = time.perf_counter()
            logging.info(f"WindowInit: top_panel took {(t1 - t0)*1000:.1f} ms")

            # Основное содержимое
            t0 = time.perf_counter()
            self.ui_setup.setup_main_content()
            t1 = time.perf_counter()
            logging.info(f"WindowInit: main_content took {(t1 - t0)*1000:.1f} ms")

            # Нижняя панель
            t0 = time.perf_counter()
            self.ui_setup.setup_bottom_panel()
            t1 = time.perf_counter()
            logging.info(f"WindowInit: bottom_panel took {(t1 - t0)*1000:.1f} ms")

            # Статус-бар
            t0 = time.perf_counter()
            self.ui_setup.setup_status_bar()
            t1 = time.perf_counter()
            logging.info(f"WindowInit: status_bar took {(t1 - t0)*1000:.1f} ms")

            # Контроллеры
            t0 = time.perf_counter()
            self.controllers_setup.setup_controllers()
            t1 = time.perf_counter()
            logging.info(f"WindowInit: setup_controllers took {(t1 - t0)*1000:.1f} ms")

            # Горячие клавиши
            t0 = time.perf_counter()
            self.ui_setup.setup_shortcuts()
            t1 = time.perf_counter()
            logging.info(f"WindowInit: shortcuts took {(t1 - t0)*1000:.1f} ms")
        finally:
            # Включаем обновления после завершения инициализации
            self.window.setUpdatesEnabled(True)

        t_total1 = time.perf_counter()
        logging.info(f"WindowInit: total initialize_window took {(t_total1 - t_total0)*1000:.1f} ms")

        # Инициализация сфер выполняется асинхронно
        self.controllers_setup.initialize_spheres()
    
    # Старые методы _setup_* удалены - функциональность перенесена в WindowUISetup
    
    # Метод _setup_top_panel удален - функциональность в WindowUISetup.setup_top_panel()
    
    # Все методы _setup_* удалены - функциональность перенесена в WindowUISetup и WindowControllersSetup
