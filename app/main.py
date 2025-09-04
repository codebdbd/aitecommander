import logging
import sys
import sqlite3

from PyQt6.QtCore import QTimer

from app.controllers.system.bootstrap import create_main_window
from app.controllers.system.db_init import DatabaseInitializer
from app.controllers.ui.theme_controller import ThemeController
from app.models.db import Database
from app.settings import AppSettings
from app.startup.app_factory import create_application
from app.startup.argument_parser import parse_arguments, determine_log_level
from app.startup.browser_profiles_loader import BrowserProfilesLoader
from app.startup.logging_setup import setup_logging, log_system_info, log_shutdown


class ApplicationInitializer:
    """Класс для инициализации компонентов приложения."""

    def __init__(self, settings=None):
        self.settings = settings
        self.database = None
        self.theme_controller = None
        self.main_window = None

    def cleanup(self):
        """Очищает ресурсы приложения."""
        try:
            # Закрываем соединение, если база и метод close доступны
            if self.database and hasattr(self.database, "close"):
                self.database.close()
        except (sqlite3.Error, AttributeError) as e:
            # Предсказуемые ошибки соединения/атрибутов логируем
            logging.error(f"Ошибка при закрытии соединения с базой данных: {e}")
        # Любые другие неожиданные исключения не подавляем
        
        # Корректно дожидаемся завершения фоновых задач БД (run_db)
        try:
            from app.utils.db.executors.pool import get_thread_pool

            pool = get_thread_pool()
            try:
                # Пытаемся дождаться завершения с таймаутом (если поддерживается)
                if hasattr(pool, "waitForDone"):
                    try:
                        pool.waitForDone(5000)  # 5 секунд на мягкое завершение
                    except TypeError:
                        # В некоторых версиях сигнатура без аргументов
                        pool.waitForDone()
            except AttributeError as e:
                # Нет ожидаемого метода у пула — не критично
                logging.debug("Исключение при ожидании завершения пула потоков: %s", e)
        except AttributeError as e:
            # Пул не тот объект/без ожидаемых атрибутов — не критично
            logging.debug("Не удалось получить пул потоков для задач БД: %s", e)

    def initialize_settings(self) -> bool:
        """Инициализирует настройки приложения."""
        try:
            if self.settings is None:
                self.settings = AppSettings()
            return True
        except Exception as e:
            logging.error(f"Ошибка загрузки настроек: {e}", exc_info=True)
            return False

    def initialize_database(self) -> bool:
        """Инициализирует подключение к базе данных."""
        try:
            self.database = Database()
            return True
        except Exception as e:
            logging.error(f"Ошибка подключения к базе данных: {e}", exc_info=True)
            return False

    def initialize_theme_controller(self) -> bool:
        """Инициализирует контроллер темы."""
        try:
            self.theme_controller = ThemeController(
                self.settings,
                top_panels_controller=None,
            )
            return True
        except Exception as e:
            logging.error(f"Ошибка создания контроллера темы: {e}", exc_info=True)
            return False

    def initialize_main_window(self) -> bool:
        """Инициализирует главное окно приложения."""
        try:
            # Создание окна через bootstrap: окно не принимает Database в конструктор
            self.main_window = create_main_window(
                self.settings, self.theme_controller, self.database
            )
            if hasattr(self.theme_controller, "set_main_window"):
                self.theme_controller.set_main_window(self.main_window)
            else:
                self.theme_controller.main_window = self.main_window
            return True
        except Exception as e:
            logging.error(f"Ошибка создания главного окна: {e}", exc_info=True)
            return False

    def apply_initial_theme(self) -> bool:
        """Применяет начальную тему оформления."""
        try:
            theme_name = self.settings.get_theme()
            self.theme_controller.apply(theme_name)
            return True
        except Exception as e:
            logging.error(f"Ошибка применения темы: {e}", exc_info=True)
            return False

    def initialize_all(self) -> bool:
        """Выполняет полную инициализацию всех компонентов."""
        # Применяем тему до создания главного окна, чтобы избежать "белой вспышки"
        initialization_steps = [
            ("настроек", self.initialize_settings),
            ("базы данных", self.initialize_database),
            ("контроллера темы", self.initialize_theme_controller),
            ("темы оформления", self.apply_initial_theme),
            ("главного окна", self.initialize_main_window),
        ]
        for step_name, step_func in initialization_steps:
            if not step_func():
                logging.critical(f"Критическая ошибка при инициализации {step_name}")
                return False
        return True




def main():
    """Главная функция приложения."""
    # Парсинг аргументов командной строки
    args = parse_arguments()
    log_level = determine_log_level(args)
    
    # Инициализируем систему логирования
    setup_logging(log_level)
    
    # Инициализируем инициализатор приложения заранее, чтобы cleanup() отработал даже при ранних ошибках
    initializer = ApplicationInitializer()
    try:
        app = create_application()
        log_system_info()
        
        if not initializer.initialize_all():
            logging.critical("Не удалось инициализировать приложение")
            if app:
                app.quit()
            return 1
        
        # Инициализация БД в фоне
        db_initializer = DatabaseInitializer(initializer.database, initializer.main_window)
        db_initializer.initialize_async()
        
        # Настройка ленивой загрузки профилей браузеров
        profiles_loader = BrowserProfilesLoader(initializer.main_window)
        profiles_loader.setup_lazy_loading()
        
        QTimer.singleShot(100, lambda: logging.info("Приложение успешно запущено"))
        exit_code = app.exec()
        return exit_code
    except Exception as e:
        logging.critical(f"Критическая ошибка в main(): {e}", exc_info=True)
        return 1
    finally:
        if initializer:
            initializer.cleanup()
        log_shutdown()


if __name__ == "__main__":
    sys.exit(main())
