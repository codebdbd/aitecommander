"""Centralized logging configuration and access."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.core.paths.path_manager import PathManager

_LOG_FILE_NAME = "app.log"
_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_LOG_MAX_BYTES = 5_242_880
_LOG_BACKUP_COUNT = 5


class LogManager:
    """Static API for logging setup and logger retrieval."""

    _configured = False

    @classmethod
    def setup(cls, level: int | str = "INFO") -> None:
        if cls._configured:
            return

        numeric_level = cls._resolve_level(level)
        log_dir = PathManager.logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / _LOG_FILE_NAME

        formatter = cls._create_formatter()

        file_handler = cls._create_file_handler(log_file, formatter)

        stream_handler = cls._create_stream_handler(formatter)

        root_logger = logging.getLogger()
        if not cls._has_handler(root_logger, RotatingFileHandler):
            root_logger.addHandler(file_handler)
        if not cls._has_stream_handler(root_logger):
            root_logger.addHandler(stream_handler)

        root_logger.setLevel(numeric_level)
        cls._configured = True

    @classmethod
    def set_level(cls, level: int | str) -> None:
        numeric_level = cls._resolve_level(level)
        logging.getLogger().setLevel(numeric_level)

    @staticmethod
    def get_logger(name: str | None = None) -> logging.Logger:
        return logging.getLogger(name)

    @staticmethod
    def _resolve_level(level: int | str) -> int:
        if isinstance(level, int):
            return level
        if isinstance(level, str):
            upper = level.strip().upper()
            numeric_level = getattr(logging, upper, None)
            if isinstance(numeric_level, int):
                return numeric_level
        return logging.INFO

    @staticmethod
    def _has_handler(
        logger: logging.Logger, handler_type: type[logging.Handler]
    ) -> bool:
        return any(isinstance(handler, handler_type) for handler in logger.handlers)

    @staticmethod
    def _has_stream_handler(logger: logging.Logger) -> bool:
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                continue
            if isinstance(handler, logging.StreamHandler):
                return True
        return False

    @staticmethod
    def _create_formatter() -> logging.Formatter:
        return logging.Formatter(_LOG_FORMAT)

    @staticmethod
    def _create_file_handler(
        log_file, formatter: logging.Formatter
    ) -> RotatingFileHandler:
        handler = RotatingFileHandler(
            PathManager.as_str(log_file),
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        return handler

    @staticmethod
    def _create_stream_handler(
        formatter: logging.Formatter,
    ) -> logging.StreamHandler:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        return handler
