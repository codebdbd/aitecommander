# inflight.py
"""Light helpers for deduplication of parallel loads (in-flight).

Using in sync/async code ensures that for a single key
no more than one real load will be performed, and other waiters
will get the result from the cache.
"""

import asyncio
import threading

# Sync: key -> Event
_sync_lock = threading.RLock()
_sync_events: dict[tuple[str, str], threading.Event] = {}

# Async: key -> Future
_async_lock = threading.RLock()
_async_futures: dict[tuple[str, str], asyncio.Future] = {}


def enter_sync(key: tuple[str, str]) -> tuple[bool, threading.Event]:
    """Enter critical section for sync loading.
    Returns (leader, event). Leader=True means the current thread should perform the load.
    Others wait for event.set().
    """
    with _sync_lock:
        ev = _sync_events.get(key)
        if ev is None:
            ev = threading.Event()
            _sync_events[key] = ev
            return True, ev
        else:
            return False, ev


def leave_sync(key: tuple[str, str]) -> None:
    """Finish sync loading: wake up waiters and remove key."""
    with _sync_lock:
        ev = _sync_events.pop(key, None)
        if ev is not None:
            ev.set()


def enter_async(key: tuple[str, str]) -> tuple[bool, asyncio.Future]:
    """Enter critical section for async loading.
    Returns (leader, future). Leader=True means the current coroutine should perform the load
    and set the future result. Others just await this future.
    """
    loop = asyncio.get_event_loop()
    with _async_lock:
        fut: asyncio.Future | None = _async_futures.get(key)
        if fut is None:
            fut = loop.create_future()
            _async_futures[key] = fut
            return True, fut
        else:
            return False, fut


def leave_async_success(key: tuple[str, str], result) -> None:
    """Set successful result and clear key."""
    with _async_lock:
        fut = _async_futures.pop(key, None)
        if fut is not None and not fut.done():
            fut.set_result(result)


def leave_async_error(key: tuple[str, str], exc: Exception | None = None) -> None:
    """Set error or empty result and clear key."""
    with _async_lock:
        fut = _async_futures.pop(key, None)
        if fut is not None and not fut.done():
            if exc is not None:
                fut.set_exception(exc)
            else:
                fut.set_result(None)
