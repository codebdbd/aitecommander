# lock_manager.py
"""Compatible layer for icons, delegating to unified `app.utils.locking`.

Preserves public API (LockLevel and acquire_*), but all logic
is implemented through a common locking module to eliminate duplication.
"""

from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from enum import IntEnum

from app.utils.locking import (
    ICON_LOCK_NAMES,
    acquire_icon_cache,
    acquire_icon_global,
    acquire_icon_lru,
    acquire_icon_metrics,
)
from app.utils.locking import (
    acquire_multiple_locks as _acquire_multiple_by_names,
)

logger = logging.getLogger(__name__)


class LockLevel(IntEnum):
    """Lock levels in priority order (API compatibility)."""

    GLOBAL = 1
    CACHE = 2
    METRICS = 3
    LRU = 4


def acquire_lock(level: LockLevel) -> AbstractContextManager[None]:
    """Context manager for single lock (API compatibility)."""
    if level == LockLevel.GLOBAL:
        return acquire_icon_global()
    if level == LockLevel.CACHE:
        return acquire_icon_cache()
    if level == LockLevel.METRICS:
        return acquire_icon_metrics()
    if level == LockLevel.LRU:
        return acquire_icon_lru()
    raise ValueError(f"Unknown LockLevel: {level}")


def acquire_global_lock() -> AbstractContextManager[None]:
    return acquire_icon_global()


def acquire_cache_lock() -> AbstractContextManager[None]:
    return acquire_icon_cache()


def acquire_metrics_lock() -> AbstractContextManager[None]:
    return acquire_icon_metrics()


def acquire_lru_lock() -> AbstractContextManager[None]:
    return acquire_icon_lru()


def acquire_multiple_locks(*levels: LockLevel):
    """Context manager for multiple locks (API compatibility).

    Orders levels by priority and delegates to the common module.
    """
    # Remove duplicates and sort by Enum value
    unique_sorted: list[LockLevel] = sorted(set(levels), key=int)
    names = [
        ICON_LOCK_NAMES["GLOBAL"]
        if lvl == LockLevel.GLOBAL
        else ICON_LOCK_NAMES["CACHE"]
        if lvl == LockLevel.CACHE
        else ICON_LOCK_NAMES["METRICS"]
        if lvl == LockLevel.METRICS
        else ICON_LOCK_NAMES["LRU"]
        for lvl in unique_sorted
    ]
    return _acquire_multiple_by_names(*names)
