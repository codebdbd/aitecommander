# app/utils/db/__init__.py
"""Утилиты для безопасного и единообразного запуска БД-операций в потоках.

Современный API:
- run_db: запуск функции БД в пуле потоков с обработкой ошибок и блокировкой
- get_thread_pool/set_thread_pool: управление пулом потоков (для тестов)

Совместимость:
- Старый модуль db_workers.py остаётся, но рекомендуется переход на run_db.
"""
from __future__ import annotations

from app.utils.db.api import run_db
from app.utils.db.executors.pool import get_thread_pool, set_thread_pool

__all__ = [
    "run_db",
    "get_thread_pool",
    "set_thread_pool",
]
