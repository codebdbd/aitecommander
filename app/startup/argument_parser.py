"""Модуль для парсинга аргументов командной строки."""

import argparse
import logging
from typing import NamedTuple


class AppArguments(NamedTuple):
    """Структура для хранения аргументов приложения."""

    debug: bool
    log_level: str | None


def parse_arguments() -> AppArguments:
    """
    Парсит аргументы командной строки.

    Returns:
        AppArguments: Структура с распарсенными аргументами
    """
    parser = argparse.ArgumentParser(description="Запуск приложения")
    parser.add_argument("--debug", action="store_true", help="Включить режим отладки")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Уровень логирования (перекрывает --debug)",
    )
    args = parser.parse_args()

    return AppArguments(debug=args.debug, log_level=args.log_level)


def determine_log_level(args: AppArguments) -> int:
    """
    Определяет уровень логирования на основе аргументов.

    Args:
        args: Аргументы приложения

    Returns:
        int: Уровень логирования
    """
    if args.log_level:
        return getattr(logging, args.log_level)
    else:
        return logging.DEBUG if args.debug else logging.INFO
