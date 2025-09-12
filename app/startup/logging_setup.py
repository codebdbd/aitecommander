"""Модуль для настройки системы логирования."""

import logging
import os
import platform
import sys

from app.utils.logging.application_logger import ApplicationLogger
from app.utils.logging.exception_handler import ExceptionHandler

# Модульный логгер
logger = logging.getLogger(__name__)


def setup_logging(log_level: int) -> None:
    """
    Настраивает систему логирования приложения.

    Args:
        log_level: Уровень логирования
    """
    # Разрешаем переопределить уровень через переменную окружения APP_LOG_LEVEL
    try:
        env_level = os.getenv("APP_LOG_LEVEL")
        if isinstance(env_level, str):
            upper = env_level.strip().upper()
            numeric_level = getattr(logging, upper, None)
            if isinstance(numeric_level, int):
                log_level = numeric_level
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        # В спорных случаях просто игнорируем переопределение, но предупреждаем
        logger.warning("APP_LOG_LEVEL read failed", exc_info=True)

    ApplicationLogger(log_level)
    logger.info("=" * 60)
    logger.info("ЗАПУСК ПРИЛОЖЕНИЯ")
    logger.info("=" * 60)

    # Устанавливаем глобальный обработчик исключений
    ExceptionHandler()

    # Подавляем шум от сторонних библиотек (оставляем только WARNING+)
    try:
        for noisy in ("asyncio", "urllib3", "PIL"):
            nl = logging.getLogger(noisy)
            nl.setLevel(max(logging.WARNING, log_level))
    except (OSError, ValueError, KeyError, AttributeError, RuntimeError):
        logger.warning("failed to adjust noisy loggers", exc_info=True)


def log_system_info() -> None:
    """Логирует системную информацию для отладки."""
    # Сокращаем объём логирования при обычном запуске — только в режиме DEBUG
    try:
        if not logger.isEnabledFor(logging.DEBUG):
            return
    except (AttributeError, RuntimeError):
        logger.warning("Failed to check log level", exc_info=True)

    from PyQt6.QtCore import QT_VERSION_STR
    from PyQt6.QtGui import QGuiApplication

    try:
        logger.info("Операционная система: %s", platform.platform())
        logger.info("Версия Python: %s", sys.version)
        logger.info("Архитектура Python: %s", platform.architecture())
        logger.info("Версия PyQt6: %s", QT_VERSION_STR)
        logger.info("Путь запуска: %s", sys.argv[0])
        logger.info("Рабочая директория: %s", os.getcwd())
        logger.info("PID процесса: %s", os.getpid())
        logger.info("Количество аргументов командной строки: %s", len(sys.argv))

        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            geometry = screen.geometry()
            logger.info(
                "Дисплей %s: %sx%s @ %sx",
                i,
                geometry.width(),
                geometry.height(),
                screen.devicePixelRatio(),
            )
    except (OSError, RuntimeError, AttributeError) as e:
        logger.warning("Не удалось получить системную информацию: %s", e)


def log_shutdown() -> None:
    """Логирует завершение работы приложения."""
    logger.info("=" * 60)
    logger.info("ЗАВЕРШЕНИЕ РАБОТЫ ПРИЛОЖЕНИЯ")
    logger.info("=" * 60)
