# lock_manager.py
"""Централизованное управление блокировками для предотвращения deadlocks.

Иерархия блокировок (порядок захвата):
1. GLOBAL_LOCK - глобальная блокировка для критических операций
2. CACHE_LOCK - блокировка кэша (пути + иконки)
3. METRICS_LOCK - блокировка метрик
4. LRU_LOCK - блокировка LRU-политики

Правило: блокировки должны захватываться строго в указанном порядке.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from enum import IntEnum
from typing import Generator

logger = logging.getLogger(__name__)


class LockLevel(IntEnum):
    """Уровни блокировок в порядке приоритета."""

    GLOBAL = 1
    CACHE = 2
    METRICS = 3
    LRU = 4


class LockManager:
    """Упрощенный менеджер блокировок."""

    def __init__(self) -> None:
        # Используем RLock для возможности повторного захвата в том же потоке
        self._locks = {
            LockLevel.GLOBAL: threading.RLock(),
            LockLevel.CACHE: threading.RLock(),
            LockLevel.METRICS: threading.RLock(),
            LockLevel.LRU: threading.RLock(),
        }

    @contextmanager
    def acquire_lock(self, level: LockLevel) -> Generator[None, None, None]:
        """Захватить блокировку."""
        lock = self._locks[level]
        lock.acquire()

        try:
            yield
        finally:
            lock.release()

    @contextmanager
    def acquire_multiple_locks(self, *levels: LockLevel) -> Generator[None, None, None]:
        """Захватить несколько блокировок в правильном порядке."""
        # Сортируем уровни по приоритету для предотвращения deadlock
        sorted_levels = sorted(set(levels))

        # Захватываем блокировки в порядке приоритета
        acquired_locks = []
        try:
            for level in sorted_levels:
                lock = self._locks[level]
                lock.acquire()
                acquired_locks.append(lock)

            yield

        finally:
            # Освобождаем в обратном порядке
            for lock in reversed(acquired_locks):
                lock.release()


# Глобальный экземпляр менеджера блокировок
_lock_manager = LockManager()


# Удобные функции для использования
def acquire_global_lock():
    """Контекстный менеджер для глобальной блокировки."""
    return _lock_manager.acquire_lock(LockLevel.GLOBAL)


def acquire_cache_lock():
    """Контекстный менеджер для блокировки кэша."""
    return _lock_manager.acquire_lock(LockLevel.CACHE)


def acquire_metrics_lock():
    """Контекстный менеджер для блокировки метрик."""
    return _lock_manager.acquire_lock(LockLevel.METRICS)


def acquire_lru_lock():
    """Контекстный менеджер для блокировки LRU."""
    return _lock_manager.acquire_lock(LockLevel.LRU)


def acquire_multiple_locks(*levels: LockLevel):
    """Контекстный менеджер для множественных блокировок."""
    return _lock_manager.acquire_multiple_locks(*levels)
