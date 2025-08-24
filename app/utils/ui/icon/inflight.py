# inflight.py
"""Лёгкие helper-ы для дедупликации параллельных загрузок (in-flight).

Использование в sync/async коде позволяет гарантировать, что для одного ключа
будет выполняться не более одной реальной загрузки, а остальные ожидатели
получат результат из кэша.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Dict, Optional, Tuple

# Sync: ключ -> Event
_sync_lock = threading.RLock()
_sync_events: Dict[Tuple[str, str], threading.Event] = {}

# Async: ключ -> Future
_async_lock = threading.RLock()
_async_futures: Dict[Tuple[str, str], asyncio.Future] = {}


def enter_sync(key: Tuple[str, str]) -> tuple[bool, threading.Event]:
    """Войти в критическую секцию для sync-загрузки.
    Возвращает (leader, event). Leader=True означает, что текущий поток должен выполнить загрузку.
    Остальные ждут event.set().
    """
    with _sync_lock:
        ev = _sync_events.get(key)
        if ev is None:
            ev = threading.Event()
            _sync_events[key] = ev
            return True, ev
        else:
            return False, ev


def leave_sync(key: Tuple[str, str]) -> None:
    """Завершить sync-загрузку: разбудить ожидающих и убрать ключ."""
    with _sync_lock:
        ev = _sync_events.pop(key, None)
        if ev is not None:
            ev.set()


def enter_async(key: Tuple[str, str]) -> tuple[bool, asyncio.Future]:
    """Войти в критическую секцию для async-загрузки.
    Возвращает (leader, future). Leader=True означает, что текущая корутина должна выполнить загрузку
    и установить результат future. Остальные просто await этого future.
    """
    loop = asyncio.get_event_loop()
    with _async_lock:
        fut: Optional[asyncio.Future] = _async_futures.get(key)
        if fut is None:
            fut = loop.create_future()
            _async_futures[key] = fut
            return True, fut
        else:
            return False, fut


def leave_async_success(key: Tuple[str, str], result) -> None:
    """Установить успешный результат и очистить ключ."""
    with _async_lock:
        fut = _async_futures.pop(key, None)
        if fut is not None and not fut.done():
            fut.set_result(result)


def leave_async_error(key: Tuple[str, str], exc: Exception | None = None) -> None:
    """Установить ошибку или пустой результат и очистить ключ."""
    with _async_lock:
        fut = _async_futures.pop(key, None)
        if fut is not None and not fut.done():
            if exc is not None:
                fut.set_exception(exc)
            else:
                fut.set_result(None)
