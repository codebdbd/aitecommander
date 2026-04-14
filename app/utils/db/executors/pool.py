"""Thread pool helpers for database/background tasks."""

from __future__ import annotations

from PyQt6.QtCore import QThreadPool

__all__ = ["get_thread_pool", "set_thread_pool"]

# Dedicated DB pool override for tests / special cases.
_CUSTOM_POOL: QThreadPool | None = None
_DB_POOL: QThreadPool | None = None


def set_thread_pool(pool: QThreadPool | None) -> None:
    """Set custom thread pool (e.g., for tests).

    Pass ``None`` to revert to the dedicated DB pool.
    """
    global _CUSTOM_POOL
    _CUSTOM_POOL = pool


def get_thread_pool() -> QThreadPool:
    """Return dedicated thread pool used for locked DB tasks."""
    global _DB_POOL
    if _CUSTOM_POOL is not None:
        return _CUSTOM_POOL
    if _DB_POOL is None:
        pool = QThreadPool()
        pool.setMaxThreadCount(1)
        pool.setExpiryTimeout(-1)
        _DB_POOL = pool
    return _DB_POOL
