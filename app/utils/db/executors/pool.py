"""Пул потоков для задач БД с возможностью подмены (для тестов).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThreadPool

__all__ = ["get_thread_pool", "set_thread_pool"]

# Храним пользовательский пул для тестов/особых случаев
_CUSTOM_POOL: Optional[QThreadPool] = None


def set_thread_pool(pool: Optional[QThreadPool]) -> None:
    """Установить пользовательский пул потоков (например, для тестов).

    Передайте None, чтобы вернуться к глобальному пулу Qt.
    """
    global _CUSTOM_POOL
    _CUSTOM_POOL = pool


def get_thread_pool() -> QThreadPool:
    """Получить пул потоков для запуска задач.

    По умолчанию — глобальный пул Qt.
    """
    return _CUSTOM_POOL or QThreadPool.globalInstance()
