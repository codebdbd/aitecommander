# app/utils/db/__init__.py
"""Utilities for safely and consistently running database operations in threads.

Supported API:
- ``run_db``: execute a database callable in the thread pool with error handling and locking
- ``get_thread_pool`` / ``set_thread_pool``: manage the thread pool (useful in tests)
"""

from __future__ import annotations

from app.utils.db.api import run_db
from app.utils.db.executors.pool import get_thread_pool, set_thread_pool

__all__ = [
    "run_db",
    "get_thread_pool",
    "set_thread_pool",
]
