# app/utils/logging/application_logger.py

import json
import logging
import logging.config
import os
import sys
from datetime import datetime
from pathlib import Path

from app.config_data import app_config


class ApplicationLogger:
    """Централизованная система логирования приложения."""

    def __init__(self, log_level=logging.INFO):
        self.log_level = log_level
        self.logs_dir = self._ensure_logs_directory()
        self.log_file_path = self._create_log_file_path()
        self._setup_logging()

    def _ensure_logs_directory(self) -> Path:
        """Создает директорию для логов в пользовательских данных."""
        pc = app_config.paths
        # гарантируем существование базовых директорий пользователя
        pc.ensure_user_data_dirs()
        logs_dir = pc.get_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    def _create_log_file_path(self) -> Path:
        """Создает путь к лог-файлу с датой."""
        log_filename = f"app_log_{datetime.now().strftime('%Y%m%d')}.txt"
        return self.logs_dir / log_filename

    def _get_app_directory(self):
        """Определяет корневую директорию приложения (работает в упакованном виде)."""
        if getattr(sys, "frozen", False):
            # Упакованное приложение (PyInstaller, cx_Freeze, etc.)
            return Path(sys.executable).parent
        else:
            # Режим разработки — корень проекта
            return Path(__file__).parents[3]

    def _get_config_path(self):
        """Определяет путь к конфигурации логирования с приоритетами."""
        # Приоритет 1: Переменная окружения (для продвинутых пользователей)
        env_path = os.getenv("LOGGING_CONFIG_PATH")
        if env_path and Path(env_path).exists():
            logging.info(
                f"Используется конфигурация из переменной окружения: {env_path}"
            )
            return Path(env_path)

        # Приоритет 2: Рядом с исполняемым файлом (портативность)
        app_dir = self._get_app_directory()
        portable_path = app_dir / "config_data" / "logging_config.json"
        if portable_path.exists():
            logging.info(f"Используется портативная конфигурация: {portable_path}")
            return portable_path

        # Приоритет 3: Стандартное место в проекте (разработка)
        # .../app/config_data/logging_config.json
        dev_path = Path(__file__).parents[2] / "config_data" / "logging_config.json"
        if dev_path.exists():
            logging.info(f"Используется конфигурация разработки: {dev_path}")
            return dev_path

        # Если ничего не найдено
        logging.warning(
            "Конфигурационный файл логирования не найден, используются настройки по умолчанию"
        )
        return None

    def _get_embedded_config(self):
        """Возвращает встроенную конфигурацию логирования как fallback."""
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                },
                "detailed": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s"
                },
            },
            "handlers": {
                "console": {
                    "level": "INFO",
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                },
                "file": {
                    "level": "DEBUG",
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(self.log_file_path),
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 5,
                    "formatter": "detailed",
                    "encoding": "utf-8",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["console", "file"],
                    "level": self.log_level,
                    "propagate": False,
                }
            },
        }

    def _setup_logging(self):
        """Настраивает систему логирования через dictConfig с ротацией логов."""
        try:
            # Получаем путь к конфигурационному файлу
            config_path = self._get_config_path()

            if config_path:
                # Загружаем конфигурацию из файла
                with open(config_path, "r", encoding="utf-8") as f:
                    log_config = json.load(f)

                # Обновляем путь к файлу лога в конфигурации
                if "handlers" in log_config and "file" in log_config["handlers"]:
                    log_config["handlers"]["file"]["filename"] = str(self.log_file_path)

                # Применяем уровень логирования
                if "loggers" in log_config and "" in log_config["loggers"]:
                    log_config["loggers"][""]["level"] = self.log_level

                # Настраиваем логирование через dictConfig
                logging.config.dictConfig(log_config)
                logging.info(f"Логирование настроено из файла: {config_path}")
            else:
                # Используем встроенную конфигурацию
                log_config = self._get_embedded_config()
                logging.config.dictConfig(log_config)
                logging.info(
                    f"Логирование настроено через встроенную конфигурацию. Файл: {self.log_file_path}"
                )

        except (FileNotFoundError, PermissionError, json.JSONDecodeError) as e:
            # Если возникла ошибка при загрузке конфигурации, используем встроенную
            logging.warning(
                f"Ошибка при загрузке конфигурации логирования: {e}. Используется встроенная конфигурация."
            )
            try:
                log_config = self._get_embedded_config()
                logging.config.dictConfig(log_config)
                logging.info(
                    "Логирование настроено через встроенную конфигурацию (fallback)"
                )
            except Exception as fallback_error:
                # Последний резерв - базовая настройка
                logging.basicConfig(
                    level=self.log_level,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler(self.log_file_path, encoding="utf-8"),
                    ],
                )
                logging.error(
                    f"Критическая ошибка настройки логирования: {fallback_error}. Используется базовая конфигурация."
                )
        except Exception as e:
            # Общий обработчик для непредвиденных ошибок
            logging.error(
                f"Неожиданная ошибка при настройке логирования: {e}. Используется базовая конфигурация."
            )
            logging.basicConfig(
                level=self.log_level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )
