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
        logging.info(f"Операционная система: {platform.platform()}")
        logging.info(f"Версия Python: {sys.version}")
        logging.info(f"Архитектура Python: {platform.architecture()}")
        logging.info(f"Версия PyQt6: {QT_VERSION_STR}")
        logging.info(f"Путь запуска: {sys.argv[0]}")
        logging.info(f"Рабочая директория: {os.getcwd()}")
        logging.info(f"PID процесса: {os.getpid()}")
        logging.info(f"Количество аргументов командной строки: {len(sys.argv)}")
        
        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            geometry = screen.geometry()
            logging.info(
                f"Дисплей {i}: {geometry.width()}x{geometry.height()} @ {screen.devicePixelRatio()}x"
            )
    except Exception as e:
        logging.warning(f"Не удалось получить системную информацию: {e}")


def log_shutdown() -> None:
    """Логирует завершение работы приложения."""
    logging.info("=" * 60)
    logging.info("ЗАВЕРШЕНИЕ РАБОТЫ ПРИЛОЖЕНИЯ")
    logging.info("=" * 60)
