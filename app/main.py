import argparse
import logging
import os
import sys

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

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
            except Exception as e:
                logging.debug("Исключение при ожидании завершения пула потоков: %s", e)
        except Exception as e:
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


def _log_system_info():
    """Логирует системную информацию для отладки."""
    # Сокращаем объём логирования при обычном запуске — только в режиме DEBUG
    try:
        root_logger = logging.getLogger()
        if not root_logger.isEnabledFor(logging.DEBUG):
            return
    except Exception:
        pass
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

            def _on_db_init_finished(res=None):
                # Проверяем результат фоновой инициализации БД
                if not res:
                    try:
                        # Сообщаем пользователю и завершаем приложение
                        QMessageBox.critical(
                            mw if 'mw' in globals() else None,
                            "Ошибка инициализации БД",
                            "Произошла ошибка при инициализации базы данных. Приложение будет закрыто.",
                        )
                    except Exception:
                        pass
                    try:
                        app_inst = QApplication.instance()
                        if app_inst is not None:
                            app_inst.quit()
                    except Exception:
                        pass
                    return

                # При успехе — завершаем штатные действия
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
                    # Не выбрасываем исключение, чтобы результат обработался в on_finished(res)
                    return False

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
                                # Обновить кеш через публичный API менеджера профилей
                                mgr = _pm.get_profile_manager()
                                try:
                                    mgr.update_profiles_bulk(all_profiles or {})
                                except Exception:
                                    pass
                            except Exception as e:
                                logging.warning("Ошибка сохранения/обновления кеша профилей: %s", e)
                            finally:
                                # Одноразовое подключение: после первого вызова отключаем слот
                                try:
                                    async_mgr.all_profiles_ready.disconnect(_save_and_update)
                                except Exception:
                                    pass

                        async_mgr.all_profiles_ready.connect(
                            _save_and_update,
                            type=Qt.ConnectionType.UniqueConnection,
                        )
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
