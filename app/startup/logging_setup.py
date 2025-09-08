"""Модуль для настройки системы логирования."""

import logging
import os
import platform
import sys

from app.utils.logging.application_logger import ApplicationLogger
from app.utils.logging.exception_handler import ExceptionHandler


def setup_logging(log_level: int) -> None:
    """
    Настраивает систему логирования приложения.
    
    Args:
        log_level: Уровень логирования
    """
    ApplicationLogger(log_level)
    logging.info("=" * 60)
    logging.info("ЗАПУСК ПРИЛОЖЕНИЯ")
    logging.info("=" * 60)
    
    # Устанавливаем глобальный обработчик исключений
    ExceptionHandler()


def log_system_info() -> None:
    """Логирует системную информацию для отладки."""
    # Сокращаем объём логирования при обычном запуске — только в режиме DEBUG
    try:
        root_logger = logging.getLogger()
        if not root_logger.isEnabledFor(logging.DEBUG):
            return
    except Exception:
        pass
    
    from PyQt6.QtCore import QT_VERSION_STR
    from PyQt6.QtGui import QGuiApplication

    try:
        logging.info("Операционная система: %s", platform.platform())
        logging.info("Версия Python: %s", sys.version)
        logging.info("Архитектура Python: %s", platform.architecture())
        logging.info("Версия PyQt6: %s", QT_VERSION_STR)
        logging.info("Путь запуска: %s", sys.argv[0])
        logging.info("Рабочая директория: %s", os.getcwd())
        logging.info("PID процесса: %s", os.getpid())
        logging.info("Количество аргументов командной строки: %s", len(sys.argv))
        
        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            geometry = screen.geometry()
            logging.info(
                "Дисплей %s: %sx%s @ %sx",
                i,
                geometry.width(),
                geometry.height(),
                screen.devicePixelRatio(),
            )
    except Exception as e:
        logging.warning("Не удалось получить системную информацию: %s", e)


def log_shutdown() -> None:
    """Логирует завершение работы приложения."""
    logging.info("=" * 60)
    logging.info("ЗАВЕРШЕНИЕ РАБОТЫ ПРИЛОЖЕНИЯ")
    logging.info("=" * 60)
