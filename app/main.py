import argparse
import logging
import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from app.controllers.system.bootstrap import create_main_window
from app.controllers.ui.theme_controller import ThemeController
from app.models.db import Database
from app.settings import AppSettings
from app.utils.db.api import run_db
from app.utils.logging.application_logger import ApplicationLogger
from app.utils.logging.exception_handler import ExceptionHandler


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
        except Exception as e:
            logging.error(f"Ошибка при закрытии соединения с базой данных: {e}")

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
            self.theme_controller = ThemeController(self.settings)
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
        initialization_steps = [
            ("настроек", self.initialize_settings),
            ("базы данных", self.initialize_database),
            ("контроллера темы", self.initialize_theme_controller),
            ("главного окна", self.initialize_main_window),
            ("темы оформления", self.apply_initial_theme),
        ]
        for step_name, step_func in initialization_steps:
            if not step_func():
                logging.critical(f"Критическая ошибка при инициализации {step_name}")
                return False
        return True


def _log_system_info():
    """Логирует системную информацию для отладки."""
    import platform

    from PyQt6.QtCore import QT_VERSION_STR
    from PyQt6.QtGui import QGuiApplication

    try:
        logging.info(f"Операционная система: {platform.platform()}")
        logging.info(f"Версия Python: {sys.version}")
        logging.info(f"Архитектура Python: {platform.architecture()}")
        logging.info(f"Версия PyQt6: {QT_VERSION_STR}")
        logging.info(f"Путь запуска: {sys.argv[0]}")
        logging.info(f"Рабочая директория: {os.getcwd()}")
        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            geometry = screen.geometry()
            logging.info(
                f"Дисплей {i}: {geometry.width()}x{geometry.height()} @ {screen.devicePixelRatio()}x"
            )
    except Exception as e:
        logging.warning(f"Не удалось получить системную информацию: {e}")


def create_application() -> QApplication:
    """Создает и настраивает QApplication."""
    app = QApplication(sys.argv)
    app.setApplicationName("MyPyQtApp")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("MyCompany")
    return app


def main():
    """Главная функция приложения."""
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description="Запуск приложения")
    parser.add_argument("--debug", action="store_true", help="Включить режим отладки")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Уровень логирования (перекрывает --debug)",
    )
    args = parser.parse_args()

    # Определяем уровень логирования
    if args.log_level:
        log_level = getattr(logging, args.log_level)
    else:
        log_level = logging.DEBUG if args.debug else logging.INFO

    # Инициализируем систему логирования
    ApplicationLogger(log_level)
    logging.info("=" * 60)
    logging.info("ЗАПУСК ПРИЛОЖЕНИЯ")
    logging.info("=" * 60)
    # Устанавливаем глобальный обработчик исключений
    ExceptionHandler()

    # Инициализируем инициализатор приложения
    initializer = None
    try:
        app = create_application()
        _log_system_info()
        logging.info(f"PID процесса: {os.getpid()}")
        logging.info(f"Количество аргументов командной строки: {len(sys.argv)}")
        settings = AppSettings()
        initializer = ApplicationInitializer(settings)
        from PyQt6.QtGui import QFont

        # Централизовано: фиксируем базовый размер шрифта приложения на 10 pt (DPI‑дружественно)
        app.setFont(QFont(app.font().family(), 10))
        if not initializer.initialize_all():
            logging.critical("Не удалось инициализировать приложение")
            if app:
                app.quit()
            return 1
        initializer.main_window.show()
        # Вариант B: мгновенно показать окно и инициализировать БД в фоне
        try:
            db = initializer.database
            mw = initializer.main_window

            # Показать статус в строке состояния (если доступно)
            try:
                if hasattr(mw, "message_label") and mw.message_label:
                    mw.message_label.setText("Инициализация базы данных…")
            except Exception:
                pass

            def _on_db_init_finished(_res=None):
                try:
                    # Создаём соединение в главном потоке по требованию
                    _ = db.connection
                except Exception as e:
                    logging.warning("Не удалось открыть соединение в главном потоке: %s", e)
                # Обновить статус-бар
                try:
                    if hasattr(mw, "update_statusbar"):
                        mw.update_statusbar()
                    if hasattr(mw, "message_label") and mw.message_label:
                        mw.message_label.setText("Готово")
                except Exception:
                    pass

            def _on_db_init_error(e: Exception):
                logging.error("Ошибка инициализации БД в фоне: %s", e, exc_info=True)
                try:
                    if hasattr(mw, "message_label") and mw.message_label:
                        mw.message_label.setText("Ошибка инициализации БД")
                    if hasattr(mw, "update_statusbar"):
                        mw.update_statusbar()
                except Exception:
                    pass

            # Запуск тяжёлых операций инициализации в пуле потоков
            def _do_db_init():
                try:
                    db.prepare_dirs()
                    db.initialize_or_migrate()
                    return True
                except Exception:
                    # Исключение обработается в on_error через run_db
                    raise

            run_db(_do_db_init, use_lock=False, description="db_init", on_finished=_on_db_init_finished, on_error=_on_db_init_error)
        except Exception as e:
            logging.debug("Не удалось запустить фоновую инициализацию БД: %s", e)
        # После показа окна: однажды фоново загрузить профили браузеров, если кеша нет
        try:
            from app.utils.browser.browser_profiles import async_profile_manager as _apm

            # Ленивый импорт: используем только PersistentProfileCache
            from app.utils.browser.browser_profiles import persistent_cache as _pc
            from app.utils.browser.browser_profiles import profile_manager as _pm

            def _on_window_shown():
                try:
                    cache_path = _pc.get_cache_path()
                    if not cache_path.exists():
                        async_mgr = _apm.get_async_profile_manager()

                        def _save_and_update(all_profiles: dict):
                            try:
                                # Сохранить в персистентный кэш
                                cache = _pc.PersistentProfileCache(default_ttl=3600)
                                for key, profiles in (all_profiles or {}).items():
                                    try:
                                        cache.set(key, profiles)
                                    except Exception:
                                        pass
                                # Обновить кеш синхронного менеджера
                                mgr = _pm.get_profile_manager()
                                now = __import__("time").time()
                                for key, profiles in (all_profiles or {}).items():
                                    mgr._cache[key] = profiles
                                    mgr._last_update[key] = now
                            except Exception as e:
                                logging.warning("Ошибка сохранения/обновления кеша профилей: %s", e)

                        async_mgr.all_profiles_ready.connect(_save_and_update)
                        async_mgr.load_all_profiles_async(use_cache=False)
                except Exception as e:
                    logging.debug("Ленивая загрузка профилей пропущена: %s", e)

            initializer.main_window.shown.connect(_on_window_shown)
        except Exception as _e:
            logging.debug("Не удалось подключить ленивую загрузку профилей: %s", _e)
        QTimer.singleShot(100, lambda: logging.info("Приложение успешно запущено"))
        exit_code = app.exec()
        return exit_code
    except Exception as e:
        logging.critical(f"Критическая ошибка в main(): {e}", exc_info=True)
        return 1
    finally:
        if initializer:
            initializer.cleanup()
        logging.info("=" * 60)
        logging.info("ЗАВЕРШЕНИЕ РАБОТЫ ПРИЛОЖЕНИЯ")
        logging.info("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
