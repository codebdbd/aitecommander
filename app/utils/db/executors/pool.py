"""Thread pool for database tasks with override support (useful in tests)."""

from __future__ import annotations

from PyQt6.QtCore import QThreadPool

__all__ = ["get_thread_pool", "set_thread_pool"]

# Store custom pool for tests / special cases
_CUSTOM_POOL: QThreadPool | None = None


def set_thread_pool(pool: QThreadPool | None) -> None:
    """Set custom thread pool (e.g., for tests).

    Pass ``None`` to revert to the global Qt pool.
    """
    global _CUSTOM_POOL
    _CUSTOM_POOL = pool


def get_thread_pool() -> QThreadPool:
    """Return thread pool used for scheduling tasks.

    Defaults to the global Qt pool.
    """
    if _CUSTOM_POOL is not None:
        return _CUSTOM_POOL
    pool = QThreadPool.globalInstance()
    if pool is None:
        raise RuntimeError("QThreadPool.globalInstance() returned None")
    return pool
