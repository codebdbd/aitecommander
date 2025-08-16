# app/main.py

import json
import logging
import logging.config
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6 import QtCore

from app.controllers.ui.theme_controller import ThemeController
from app.models.db import Database
from app.settings import AppSettings
from app.utils.ui.dialog_manager import DialogManager
from app.views.main_window import MainWindow


class ApplicationLogger:
    """Централизованная система логирования приложения."""
    
    def __init__(self, log_level=logging.INFO):
        self.log_level = log_level
        self.logs_dir = self._ensure_logs_directory()
        self.log_file_path = self._create_log_file_path()
        self._setup_logging()
    
    def _ensure_logs_directory(self) -> Path:
        """Создает директорию для логов, если она не существует."""
        project_root = Path(__file__).parent.parent
        logs_dir = project_root / "logs"
        logs_dir.mkdir(exist_ok=True)
        return logs_dir
    
    def _create_log_file_path(self) -> Path:
        """Создает путь к лог-файлу с датой."""
        log_filename = f"app_log_{datetime.now().strftime('%Y%m%d')}.txt"
        return self.logs_dir / log_filename
    
    def _get_app_directory(self):
        """Определяет корневую директорию приложения (работает в упакованном виде)."""
        if getattr(sys, 'frozen', False):
            # Упакованное приложение (PyInstaller, cx_Freeze, etc.)
            return Path(sys.executable).parent
        else:
            # Режим разработки
            return Path(__file__).parent.parent
    
    def _get_config_path(self):
        """Определяет путь к конфигурации логирования с приоритетами."""
        # Приоритет 1: Переменная окружения (для продвинутых пользователей)
        env_path = os.getenv('LOGGING_CONFIG_PATH')
        if env_path and Path(env_path).exists():
            logging.info(f"Используется конфигурация из переменной окружения: {env_path}")
            return Path(env_path)
        
        # Приоритет 2: Рядом с исполняемым файлом (портативность)
        app_dir = self._get_app_directory()
        portable_path = app_dir / "config_data" / "logging_config.json"
        if portable_path.exists():
            logging.info(f"Используется портативная конфигурация: {portable_path}")
            return portable_path
        
        # Приоритет 3: Стандартное место в проекте (разработка)
        dev_path = Path(__file__).parent / "config_data" / "logging_config.json"
        if dev_path.exists():
            logging.info(f"Используется конфигурация разработки: {dev_path}")
            return dev_path
        
        # Если ничего не найдено
        logging.warning("Конфигурационный файл логирования не найден, используются настройки по умолчанию")
        return None
    
    def _get_embedded_config(self):
        """Возвращает встроенную конфигурацию логирования как fallback."""
        return {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'standard': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                },
                'detailed': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s'
                },
            },
            'handlers': {
                'console': {
                    'level': 'INFO',
                    'class': 'logging.StreamHandler',
                    'formatter': 'standard'
                },
                'file': {
                    'level': 'DEBUG',
                    'class': 'logging.handlers.RotatingFileHandler',
                    'filename': str(self.log_file_path),
                    'maxBytes': 10485760,  # 10MB
                    'backupCount': 5,
                    'formatter': 'detailed',
                    'encoding': 'utf-8'
                }
            },
            'loggers': {
                '': {
                    'handlers': ['console', 'file'],
                    'level': self.log_level,
                    'propagate': False
                }
            }
        }

    def _setup_logging(self):
        """Настраивает систему логирования через dictConfig с ротацией логов."""
        try:
            # Получаем путь к конфигурационному файлу
            config_path = self._get_config_path()
            
            if config_path:
                # Загружаем конфигурацию из файла
                with open(config_path, 'r', encoding='utf-8') as f:
                    log_config = json.load(f)
                
                # Обновляем путь к файлу лога в конфигурации
                if 'handlers' in log_config and 'file' in log_config['handlers']:
                    log_config['handlers']['file']['filename'] = str(self.log_file_path)
                
                # Применяем уровень логирования
                if 'loggers' in log_config and '' in log_config['loggers']:
                    log_config['loggers']['']['level'] = self.log_level
                
                # Настраиваем логирование через dictConfig
                logging.config.dictConfig(log_config)
                logging.info(f"Логирование настроено из файла: {config_path}")
            else:
                # Используем встроенную конфигурацию
                log_config = self._get_embedded_config()
                logging.config.dictConfig(log_config)
                logging.info(f"Логирование настроено через встроенную конфигурацию. Файл: {self.log_file_path}")
                
        except (FileNotFoundError, PermissionError, json.JSONDecodeError) as e:
            # Если возникла ошибка при загрузке конфигурации, используем встроенную
            logging.warning(f"Ошибка при загрузке конфигурации логирования: {e}. Используется встроенная конфигурация.")
            try:
                log_config = self._get_embedded_config()
                logging.config.dictConfig(log_config)
                logging.info("Логирование настроено через встроенную конфигурацию (fallback)")
            except Exception as fallback_error:
                # Последний резерв - базовая настройка
                logging.basicConfig(
                    level=self.log_level,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler(self.log_file_path, encoding='utf-8')
                    ]
                )
                logging.error(f"Критическая ошибка настройки логирования: {fallback_error}. Используется базовая конфигурация.")
        except Exception as e:
            # Общий обработчик для непредвиденных ошибок
            logging.error(f"Неожиданная ошибка при настройке логирования: {e}. Используется базовая конфигурация.")
            logging.basicConfig(
                level=self.log_level,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
    
    def _setup_default_logging(self):
        """Настраивает систему логирования с параметрами по умолчанию."""
        log_config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'standard': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                },
                'detailed': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s'
                },
            },
            'handlers': {
                'console': {
                    'level': 'INFO',
                    'class': 'logging.StreamHandler',
                    'formatter': 'standard',
                },
                'file': {
                    'level': 'DEBUG',
                    'class': 'logging.handlers.RotatingFileHandler',
                    'formatter': 'detailed',
                    'filename': str(self.log_file_path),
                    'maxBytes': 1024*1024*5,  # 5 MB
                    'backupCount': 5,
                    'encoding': 'utf-8',
                },
            },
            'loggers': {
                '': {  # root logger
                    'handlers': ['console', 'file'],
                    'level': self.log_level,
                    'propagate': False
                }
            }
        }
        
        logging.config.dictConfig(log_config)
        logging.info(f"Логирование настроено через dictConfig (по умолчанию). Файл: {self.log_file_path}")


class ExceptionHandler:
    """Обработчик глобальных исключений."""
    
    def __init__(self):
        self.original_excepthook = sys.excepthook
        sys.excepthook = self.handle_exception
    
    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Обрабатывает непойманные исключения."""
        if issubclass(exc_type, KeyboardInterrupt):
            # Возвращаем стандартное поведение для прерывания
            self.original_excepthook(exc_type, exc_value, exc_traceback)
            return
        
        # Логируем критическую ошибку
        logging.critical(
            "Непойманное исключение",
            exc_info=(exc_type, exc_value, exc_traceback)
        )
        
        # Показываем пользователю информацию об ошибке
        self._show_error_dialog(exc_type, exc_value, exc_traceback)
    
    def _show_error_dialog(self, exc_type, exc_value, exc_traceback):
        """Показывает диалог с информацией об ошибке."""
        try:
            # Проверяем, существует ли QApplication
            if QApplication.instance() is None:
                error_text = f"Произошла критическая ошибка: {exc_type.__name__}"
                error_info = str(exc_value)
                error_details = ''.join(traceback.format_exception(
                    exc_type, exc_value, exc_traceback
                ))
                logging.getLogger(__name__).error(error_text)
                logging.getLogger(__name__).error(error_info)
                logging.getLogger(__name__).error("Подробности:")
                logging.getLogger(__name__).error(error_details)
                return
            
            error_text = f"Произошла критическая ошибка: {exc_type.__name__}"
            error_info = str(exc_value)
            error_details = ''.join(traceback.format_exception(
                exc_type, exc_value, exc_traceback
            ))
            
            DialogManager.show_error(
                None,
                "Критическая ошибка",
                error_text,
                informative_text=f"{error_info}\n\nПриложение будет закрыто.",
                details=error_details,
            )
        except Exception as e:
            # Если даже диалог не удается показать
            print(f"Критическая ошибка: {exc_type.__name__}: {exc_value}")
            print(f"Ошибка показа диалога: {e}")


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
            # Проверяем, что database существует и имеет активное соединение
            if self.database and hasattr(self.database, 'thread_local') and hasattr(self.database.thread_local, 'conn'):
                self.database.close()
                logging.info("Соединение с базой данных закрыто")
            elif self.database:
                logging.info("Соединение с базой данных уже было закрыто или не было установлено")
        except Exception as e:
            logging.error(f"Ошибка при закрытии соединения с базой данных: {e}")
    
    def initialize_settings(self) -> bool:
        """Инициализирует настройки приложения."""
        try:
            # Если настройки уже были переданы извне, используем их
            if self.settings is None:
                logging.info("Загрузка настроек приложения...")
                self.settings = AppSettings()
            else:
                logging.info("Используются переданные настройки приложения")
            logging.info("Настройки успешно загружены")
            return True
        except Exception as e:
            logging.error(f"Ошибка загрузки настроек: {e}", exc_info=True)
            return False
    
    def initialize_database(self) -> bool:
        """Инициализирует подключение к базе данных."""
        try:
            logging.info("Подключение к базе данных...")
            self.database = Database()
            logging.info("База данных успешно инициализирована")
            return True
        except Exception as e:
            logging.error(f"Ошибка подключения к базе данных: {e}", exc_info=True)
            return False
    
    def initialize_theme_controller(self) -> bool:
        """Инициализирует контроллер темы."""
        try:
            logging.info("Создание контроллера темы...")
            self.theme_controller = ThemeController(self.settings)
            logging.info("Контроллер темы создан")
            return True
        except Exception as e:
            logging.error(f"Ошибка создания контроллера темы: {e}", exc_info=True)
            return False
    
    def initialize_main_window(self) -> bool:
        """Инициализирует главное окно приложения."""
        try:
            logging.info("Создание главного окна...")
            self.main_window = MainWindow(
                self.database, 
                self.settings, 
                self.theme_controller
            )
            
            # Устанавливаем связь между контроллером темы и окном
            if hasattr(self.theme_controller, 'set_main_window'):
                self.theme_controller.set_main_window(self.main_window)
            else:
                # Fallback для старого API
                self.theme_controller.main_window = self.main_window
            
            logging.info("Главное окно создано")
            return True
        except Exception as e:
            logging.error(f"Ошибка создания главного окна: {e}", exc_info=True)
            return False
    
    def apply_initial_theme(self) -> bool:
        """Применяет начальную тему оформления."""
        try:
            theme_name = self.settings.get_theme()
            logging.info(f"Применение начальной темы: {theme_name}")
            self.theme_controller.apply(theme_name)
            logging.info("Тема успешно применена")
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
            logging.info(f"Инициализация {step_name}...")
            if not step_func():
                logging.critical(f"Критическая ошибка при инициализации {step_name}")
                return False
        
        logging.info("Все компоненты успешно инициализированы")
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
        
        # Информация о дисплеях
        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            geometry = screen.geometry()
            logging.info(f"Дисплей {i}: {geometry.width()}x{geometry.height()} @ {screen.devicePixelRatio()}x")
    except Exception as e:
        logging.warning(f"Не удалось получить системную информацию: {e}")


def _is_running_as_admin() -> bool:
    """Проверяет, запущен ли процесс с правами администратора (Windows)."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class _AppWideDnDLogger(QtCore.QObject):
    """Глобальный логгер DnD-событий на уровне QApplication.

    Ловит DragEnter/DragMove/Drop для диагностики случаев, когда события
    не доходят до окон/виджетов (например, из-за UAC или перехвата фильтрами).
    """

    def eventFilter(self, obj, event):
        et = event.type()
        if et in (QtCore.QEvent.Type.DragEnter, QtCore.QEvent.Type.DragMove, QtCore.QEvent.Type.Drop):
            try:
                mime = event.mimeData()
                fmts = getattr(mime, 'formats', lambda: [])()
                name = ''
                try:
                    name = obj.objectName()
                except Exception:
                    name = ''
                if not name:
                    name = obj.__class__.__name__
                logging.info(
                    "[DnD][APP] %s on %s: formats=%s hasUrls=%s hasText=%s hasHtml=%s",
                    et.name,
                    name,
                    fmts,
                    getattr(mime, 'hasUrls', lambda: False)(),
                    getattr(mime, 'hasText', lambda: False)(),
                    getattr(mime, 'hasHtml', lambda: False)(),
                )
            except Exception:
                pass
        return super().eventFilter(obj, event)


def create_application() -> QApplication:
    """Создает и настраивает QApplication."""
    app = QApplication(sys.argv)
    
    # Настройки приложения
    app.setApplicationName("MyPyQtApp")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("MyCompany")
    
    logging.info(f"QApplication создан: {app.applicationName()} v{app.applicationVersion()}")
    return app


def main():
    """Главная функция приложения."""
    # Определяем уровень логирования в зависимости от режима
    log_level = logging.DEBUG if '--debug' in sys.argv else logging.INFO
    
    # Инициализируем систему логирования
    app_logger = ApplicationLogger(log_level)
    logging.info("=" * 60)
    logging.info("ЗАПУСК ПРИЛОЖЕНИЯ")
    logging.info("=" * 60)
    
    # Устанавливаем глобальный обработчик исключений
    exception_handler = ExceptionHandler()
    
    # Инициализируем инициализатор приложения
    initializer = None
    
    try:
        # Создаем QApplication
        app = create_application()
        
        # Логируем системную информацию после создания QApplication
        _log_system_info()
        # Логируем статус прав процесса (для диагностики UAC и DnD)
        try:
            is_admin = _is_running_as_admin()
            logging.info(f"Права процесса: {'Администратор' if is_admin else 'Обычный пользователь'}")
        except Exception:
            pass
        
        # Устанавливаем глобальный eventFilter для DnD-диагностики на уровне приложения
        try:
            _global_dnd_filter = _AppWideDnDLogger(app)
            app.installEventFilter(_global_dnd_filter)
            logging.info("[DnD][APP] QApplication DnD diagnostics installed")
        except Exception as e:
            logging.warning(f"[DnD][APP] Failed to install QApplication DnD diagnostics: {e}")
        
        # Логируем PID процесса и количество аргументов
        logging.info(f"PID процесса: {os.getpid()}")
        logging.info(f"Количество аргументов командной строки: {len(sys.argv)}")
        
        # Создаем настройки один раз и передаем их в инициализатор
        settings = AppSettings()
        # Вариант A: единоразово зафиксировать размер шрифта 10pt в пользовательских настройках
        try:
            settings.set_font_size(10)
            logging.info("Пользовательский размер шрифта установлен в 10pt (Option A)")
        except Exception as e:
            logging.warning(f"Не удалось записать размер шрифта в настройки: {e}")
        initializer = ApplicationInitializer(settings)

        # Предзагрузка профилей браузеров в фоне
        from PyQt6.QtCore import QRunnable, QThreadPool

        from app.utils.browser.browser_profiles import BrowserProfileManager
        
        class ProfilePreloader(QRunnable):
            def run(self):
                try:
                    manager = BrowserProfileManager()
                    manager.get_all_profiles()
                    logging.info("Профили браузеров предзагружены")
                except Exception as e:
                    logging.warning(f"Ошибка предзагрузки профилей: {e}")
        
        QThreadPool.globalInstance().start(ProfilePreloader())

        # Применяем размер шрифта из настроек
        from PyQt6.QtGui import QFont
        font_size = settings.get_font_size() if hasattr(settings, 'get_font_size') else 12
        app.setFont(QFont(app.font().family(), font_size))
        logging.info(f"Глобальный шрифт приложения установлен: {app.font().family()} {font_size}pt")

        if not initializer.initialize_all():
            logging.critical("Не удалось инициализировать приложение")
            if app:
                app.quit()
            return 1
        
        # Показываем главное окно
        logging.info("Отображение главного окна...")
        initializer.main_window.show()
        logging.info("Главное окно отображено")
        
        # Логируем успешный старт через небольшую задержку
        QTimer.singleShot(100, lambda: logging.info("Приложение успешно запущено"))
        
        # Запускаем главный цикл событий
        logging.info("Запуск главного цикла событий...")
        exit_code = app.exec()
        
        logging.info(f"Приложение завершено с кодом: {exit_code}")
        return exit_code
        
    except Exception as e:
        logging.critical(f"Критическая ошибка в main(): {e}", exc_info=True)
        return 1
    
    finally:
        # Очищаем ресурсы приложения
        if initializer:
            initializer.cleanup()
        
        logging.info("=" * 60)
        logging.info("ЗАВЕРШЕНИЕ РАБОТЫ ПРИЛОЖЕНИЯ")
        logging.info("=" * 60)


if __name__ == "__main__":
    sys.exit(main())