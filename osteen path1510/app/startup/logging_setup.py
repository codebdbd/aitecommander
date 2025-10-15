"""Module for configuring the logging system."""

import logging
import os
import platform
import sys

from app.utils.logging.application_logger import ApplicationLogger
from app.utils.logging.exception_handler import ExceptionHandler

# Module-level logger
logger = logging.getLogger(__name__)


def setup_logging(log_level: int) -> None:
    """
    Configure application logging.

    Args:
        log_level: Initial logging level
    """
    # Allow overriding level via APP_LOG_LEVEL environment variable
    try:
        env_level = os.getenv("APP_LOG_LEVEL")
        if isinstance(env_level, str):
            upper = env_level.strip().upper()
            numeric_level = getattr(logging, upper, None)
            if isinstance(numeric_level, int):
                log_level = numeric_level
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        # Test expects a WARNING-level message
        logger.warning("APP_LOG_LEVEL read failed")

    ApplicationLogger(log_level)
    logger.info("=" * 60)
    logger.info("APPLICATION START")
    logger.info("=" * 60)

    # Install global exception handler
    ExceptionHandler()

    # Suppress noise from third-party libraries (keep WARNING+)
    try:
        for noisy in ("asyncio", "urllib3", "PIL"):
            nl = logging.getLogger(noisy)
            nl.setLevel(max(logging.WARNING, log_level))
    except (OSError, ValueError, KeyError, AttributeError, RuntimeError):
        # Test expects a WARNING-level message
        logger.warning("failed to adjust noisy loggers")


def log_system_info() -> None:
    """Log system information for debugging."""
    # Reduce log volume in normal runs — only in DEBUG
    try:
        if not logger.isEnabledFor(logging.DEBUG):
            return
    except (AttributeError, RuntimeError):
        logger.warning("Failed to check log level", exc_info=True)

    from PyQt6.QtCore import QT_VERSION_STR
    from PyQt6.QtGui import QGuiApplication

    try:
        logger.info("Operating system: %s", platform.platform())
        logger.info("Python version: %s", sys.version)
        logger.info("Python architecture: %s", platform.architecture())
        logger.info("PyQt6 version: %s", QT_VERSION_STR)
        logger.info("Launch path: %s", sys.argv[0])
        logger.info("Working directory: %s", os.getcwd())
        logger.info("Process PID: %s", os.getpid())
        logger.info("Command-line arguments count: %s", len(sys.argv))

        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            geometry = screen.geometry()
            logger.info(
                "Display %s: %sx%s @ %sx",
                i,
                geometry.width(),
                geometry.height(),
                screen.devicePixelRatio(),
            )
    except (OSError, RuntimeError, AttributeError) as e:
        logger.warning("Failed to obtain system information: %s", e)


def log_shutdown() -> None:
    """Log application shutdown."""
    logger.info("=" * 60)
    logger.info("APPLICATION SHUTDOWN")
    logger.info("=" * 60)
