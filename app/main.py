import logging
import sqlite3
import sys

from PyQt6.QtCore import QTimer

from app.config_data import app_config
from app.controllers.system.bootstrap import create_main_window
from app.controllers.system.db_init import DatabaseInitializer
from app.controllers.ui.theme_controller import ThemeController
from app.models.db import Database
from app.settings import AppSettings
from app.startup.app_factory import create_application
from i18n.language_service import LanguageService
from app.startup.argument_parser import determine_log_level, parse_arguments

# Register Qt resources for translations (:/i18n/app_*.qm) if available
try:  # noqa: SIM105 - best-effort import, optional in dev mode
    from i18n import resources_rc  # type: ignore  # noqa: F401
except Exception:
    # Fallback: LanguageService will try filesystem i18n/app_*.qm
    pass
from app.startup.browser_profiles_loader import BrowserProfilesLoader
from app.startup.logging_setup import log_shutdown, log_system_info, setup_logging

# Модульный логгер
logger = logging.getLogger(__name__)


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
            logger.error("Ошибка при закрытии соединения с базой данных: %s", e)
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
                logger.debug("Исключение при ожидании завершения пула потоков: %s", e)
        except AttributeError as e:
            # Пул не тот объект/без ожидаемых атрибутов — не критично
            logger.debug("Не удалось получить пул потоков для задач БД: %s", e)

    def initialize_settings(self) -> bool:
        """Инициализирует настройки приложения."""
        try:
            if self.settings is None:
                self.settings = AppSettings()
            return True
        except (ValueError, OSError, RuntimeError) as e:
            # Ожидаемые ошибки конфигурации окружения/настроек
            logger.error("Ошибка загрузки настроек: %s", e, exc_info=True)
            return False
        except Exception as e:
            # Неожиданная ошибка — выделяем уровнем CRITICAL для быстрой диагностики
            logger.critical(
                "Неожиданная ошибка при инициализации настроек: %s", e, exc_info=True
            )
            return False

    def initialize_database(self) -> bool:
        """Инициализирует подключение к базе данных."""
        try:
            self.database = Database()
            return True
        except (sqlite3.Error, OSError, RuntimeError) as e:
            logger.error("Ошибка подключения к базе данных: %s", e, exc_info=True)
            return False
        except Exception as e:
            logger.critical(
                "Неожиданная ошибка при инициализации базы данных: %s", e, exc_info=True
            )
            return False

    def initialize_theme_controller(self) -> bool:
        """Инициализирует контроллер темы."""
        try:
            self.theme_controller = ThemeController(
                self.settings,
                top_panels_controller=None,
            )
            return True
        except (ValueError, TypeError, RuntimeError) as e:
            logger.error("Ошибка создания контроллера темы: %s", e, exc_info=True)
            return False
        except Exception as e:
            logger.critical(
                "Неожиданная ошибка при создании контроллера темы: %s", e, exc_info=True
            )
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
        except (RuntimeError, TypeError, ValueError) as e:
            logger.error("Ошибка создания главного окна: %s", e, exc_info=True)
            return False
        except Exception as e:
            logger.critical(
                "Неожиданная ошибка при создании главного окна: %s", e, exc_info=True
            )
            return False

    def apply_initial_theme(self) -> bool:
        """Применяет начальную тему оформления."""
        try:
            theme_name = self.settings.get_theme()
            self.theme_controller.apply(theme_name)
            return True
        except (ValueError, RuntimeError, TypeError) as e:
            logger.error("Ошибка применения темы: %s", e, exc_info=True)
            return False
        except Exception as e:
            logger.critical(
                "Неожиданная ошибка при применении темы: %s", e, exc_info=True
            )
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
                logger.critical("Критическая ошибка при инициализации %s", step_name)
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
        LanguageService.instance().install_translator(app)
        log_system_info()

        if not initializer.initialize_all():
            logger.critical("Не удалось инициализировать приложение")
            if app:
                app.quit()
            return 1

        # Инициализация БД в фоне
        db_initializer = DatabaseInitializer(
            initializer.database, initializer.main_window
        )
        db_initializer.initialize_async()

        # Настройка ленивой загрузки профилей браузеров
        profiles_loader = BrowserProfilesLoader(initializer.main_window)
        profiles_loader.setup_lazy_loading()

        startup_delay = app_config.get("startup.app_ready_delay_ms", 100)
        QTimer.singleShot(startup_delay, lambda: logger.info("Приложение успешно запущено"))
        exit_code = app.exec()
        return exit_code
    except Exception as e:
        logger.critical("Критическая ошибка в main(): %s", e, exc_info=True)
        return 1
    finally:
        if initializer:
            initializer.cleanup()
        log_shutdown()


if __name__ == "__main__":
    sys.exit(main())
