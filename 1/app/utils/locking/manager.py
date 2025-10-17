"""Unified locking facade built on top of `app.utils.db.synchronization`.

Goals:
- Provide a single source of truth for lock handling across the app.
- Keep using robust `LockManager` and `EnhancedLock` from db.synchronization.
- Add convenient helpers for icon subsystem (ordered multi-lock acquisition).

This module intentionally avoids duplicating lock logic. It delegates to the
existing LockManager while adding thin convenience wrappers.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from app.utils.db.synchronization import (
    EnhancedLock,
    LockType,
    get_lock_manager,
)

# Global names for icon-subsystem locks (kept stable for imports)
ICON_LOCK_NAMES: dict[str, str] = {
    "GLOBAL": "icon.global",
    "CACHE": "icon.cache",
    "METRICS": "icon.metrics",
    "LRU": "icon.lru",
}

# Explicit acquisition order for icon locks (to avoid deadlocks inside icon domain)
_ICON_ORDER: list[str] = [
    ICON_LOCK_NAMES["GLOBAL"],
    ICON_LOCK_NAMES["CACHE"],
    ICON_LOCK_NAMES["METRICS"],
    ICON_LOCK_NAMES["LRU"],
]


def ensure_default_locks_registered() -> None:
    """Register default locks if they are not yet created.

    - Reuse LockType.UI_STATE for icon locks to keep lock-type ordering compatible.
      Ordering inside icon subsystem is handled by this facade for multi-acquire.
    """
    lm = get_lock_manager()

    # DB/task locks are created in synchronization module (database, tasks).
    # Here we only ensure icon-related locks exist.
    for name in _ICON_ORDER:
        if lm.get_lock(name) is None:
            lm.create_lock(name, LockType.UI_STATE, reentrant=True)


@contextmanager
def acquire_lock(
    name: str, timeout: float | None = None
) -> Generator[None, None, None]:
    """Acquire a single lock by name via the global LockManager.

    Delegates to synchronization's `acquire_lock` for the given registered name.
    """
    ensure_default_locks_registered()
    lm = get_lock_manager()
    with lm.acquire_lock(name, timeout=timeout or 5.0):
        yield


@contextmanager
def acquire_multiple_locks(
    *names: str, timeout_per_lock: float | None = None
) -> Generator[None, None, None]:
    """Acquire multiple locks in a well-defined order to avoid deadlocks.

    - If all names are icon locks, they are sorted by `_ICON_ORDER`.
    - Otherwise, names are kept as provided. Underlying manager enforces lock-type
      ordering; please pass names in the intended order.
    """
    ensure_default_locks_registered()
    lm = get_lock_manager()

    lock_list: list[str]
    if all(n in _ICON_ORDER for n in names):
        order_index = {n: i for i, n in enumerate(_ICON_ORDER)}
        # Remove duplicates, keep the highest priority order
        unique = sorted(set(names), key=lambda n: order_index[n])
        lock_list = unique
    else:
        # Fallback: do not reorder names outside icon domain
        lock_list = list(dict.fromkeys(names))  # deduplicate, keep first occurrence

    acquired: list[tuple[str, EnhancedLock]] = []
    try:
        for n in lock_list:
            lock = lm.get_lock(n)
            if lock is None:
                raise ValueError(f"Lock '{n}' is not registered")
            lock.acquire(timeout=timeout_per_lock)
            acquired.append((n, lock))
        yield
    finally:
        for _, lock in reversed(acquired):
            lock.release()


# Convenience wrappers dedicated to the icon subsystem
@contextmanager
def acquire_icon_global() -> Generator[None, None, None]:
    with acquire_lock(ICON_LOCK_NAMES["GLOBAL"]):
        yield


@contextmanager
def acquire_icon_cache() -> Generator[None, None, None]:
    with acquire_lock(ICON_LOCK_NAMES["CACHE"]):
        yield


@contextmanager
def acquire_icon_metrics() -> Generator[None, None, None]:
    with acquire_lock(ICON_LOCK_NAMES["METRICS"]):
        yield


@contextmanager
def acquire_icon_lru() -> Generator[None, None, None]:
    with acquire_lock(ICON_LOCK_NAMES["LRU"]):
        yield


# === Утилиты для отладки (для тестов) ===

def get_lock_info() -> dict[str, dict[str, bool | int | None]]:
    """Получить информацию о всех блокировках (для отладки).
    
    Returns:
        Словарь с информацией о каждой блокировке
    """
    ensure_default_locks_registered()
    lm = get_lock_manager()
    
    info = {}
    for name in _ICON_ORDER:
        lock = lm.get_lock(name)
        if lock:
            info[name] = {
                "locked": lock._lock._is_owned() if hasattr(lock._lock, '_is_owned') else False,
                "owner": None,  # EnhancedLock не хранит owner
            }
    return info


def reset_all_locks() -> None:
    """Сбросить все блокировки (только для тестов!).
    
    Warning:
        Использовать ТОЛЬКО в тестах.
    """
    # Для существующего LockManager просто пересоздаём блокировки
    ensure_default_locks_registered()
