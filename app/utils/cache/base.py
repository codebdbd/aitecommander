"""
Base abstractions for caching.

Unified API:
- get(key) -> Optional[Any]
- set(key, value, *, ttl: Optional[float] = None) -> None
- invalidate(key: Optional[str] = None) -> None
- clear() -> None

Notes:
- TTL (seconds) can be provided per record; implementations may also define a default TTL.
- Implementations must be thread-safe when used in multi-threaded scenarios.
"""

from __future__ import annotations

import abc
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheRecord:
    value: Any
    ts: float
    ttl: Optional[float] = None

    def is_valid(self) -> bool:
        if self.ttl is None:
            return True
        try:
            ttl = float(self.ttl)
        except Exception:
            return False
        if ttl <= 0:
            return False
        return (time.time() - self.ts) < ttl


class BaseCache(abc.ABC):
    """Abstract base class for cache implementations."""

    @abc.abstractmethod
    def get(self, key: str) -> Optional[Any]:  # pragma: no cover - контракт
        raise NotImplementedError

    @abc.abstractmethod
    def set(
        self, key: str, value: Any, *, ttl: Optional[float] = None
    ) -> None:  # pragma: no cover - контракт
        raise NotImplementedError

    @abc.abstractmethod
    def invalidate(
        self, key: Optional[str] = None
    ) -> None:  # pragma: no cover - контракт
        raise NotImplementedError

    def clear(self) -> None:
        """Alias for ``invalidate(None)``."""
        self.invalidate(None)


class InMemoryCache(BaseCache):
    """Thread-safe in-memory cache with optional default TTL and LRU size limit.

    Eviction: when inserting and the cache reaches ``max_size``, the least recently used key is removed.

    Expired record cleanup (TTL):
    - ``get`` lazily removes expired records.
    - ``prune_expired()`` performs a full sweep and removes all expired records at once.
    - To avoid scanning all keys on every call, an opportunistic strategy runs cleanup on ``set``/``invalidate``
      no more often than once per ``_prune_interval_sec`` seconds.
    - Default interval is 60 seconds; it can be adjusted via ``_prune_interval_sec``.
    """

    def __init__(
        self, *, default_ttl: Optional[float] = None, max_size: Optional[int] = None
    ) -> None:
        self._default_ttl = default_ttl
        # Validate ``max_size``: allow None or integer >= 0; negative values raise an error
        if max_size is None:
            self._max_size = None
        else:
            try:
                ms = int(max_size)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("max_size must be an integer or None") from exc
            if ms < 0:
                raise ValueError("max_size must be >= 0 or None")
            self._max_size = ms
        self._lock = threading.RLock()
        # LRU order is stored in OrderedDict: most recent items stay on the right (end)
        # key -> CacheRecord
        self._store: OrderedDict[str, CacheRecord] = OrderedDict()
        # Periodic cleanup parameters
        self._last_prune_ts: float = 0.0
        self._prune_interval_sec: float = 60.0

    def _touch(self, key: str) -> None:
        # Move key to the end to mark it as most recently used
        if key in self._store:
            self._store.move_to_end(key, last=True)

    def _evict_if_needed(self) -> None:
        if self._max_size is None:
            return
        while len(self._store) > self._max_size:
            # Remove the oldest entry (leftmost)
            try:
                self._store.popitem(last=False)
            except KeyError:
                break

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            rec = self._store.get(key)
            if rec is None:
                return None
            if not rec.is_valid():
                # Expired — remove
                self._store.pop(key, None)
                return None
            self._touch(key)
            return rec.value

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        with self._lock:
            rec = CacheRecord(
                value=value,
                ts=time.time(),
                ttl=ttl if ttl is not None else self._default_ttl,
            )
            self._store[key] = rec
            # Move to the end as the most recent entry
            self._store.move_to_end(key, last=True)
            self._evict_if_needed()
            self._maybe_prune_expired_locked()

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                if self._store:
                    self._store.clear()
                # After full cleanup update the last prune timestamp
                self._last_prune_ts = time.time()
                return
            self._store.pop(key, None)
            self._maybe_prune_expired_locked()

    # --- Expired record cleanup ---
    def prune_expired(self) -> int:
        """Remove all expired records (TTL exceeded). Returns the number of removed keys.

        Performs a full sweep under the lock. Safe to call at any time.
        """
        removed = 0
        with self._lock:
            now = time.time()
            # Create a list to avoid mutating the dict while iterating
            for k, rec in list(self._store.items()):
                if rec is None:
                    continue
                try:
                    ttl = rec.ttl if rec.ttl is not None else self._default_ttl
                    if ttl is None:
                        continue
                    ttl_f = float(ttl)
                except Exception:
                    ttl_f = 0.0
                if ttl_f <= 0 or (now - rec.ts) >= ttl_f:
                    self._store.pop(k, None)
                    removed += 1
            self._last_prune_ts = now
        return removed

    def _maybe_prune_expired_locked(self) -> None:
        """Opportunistic cleanup: run ``prune_expired`` at most once per ``_prune_interval_sec`` seconds.

        Requires the caller to hold ``_lock``.
        """
        try:
            now = time.time()
            if (now - self._last_prune_ts) >= self._prune_interval_sec:
                # Call without re-locking because ``_lock`` is already held
                removed = 0
                # Light optimisation: iterate directly when there are few keys
                for k, rec in list(self._store.items()):
                    if rec is None:
                        continue
                    ttl = rec.ttl if rec.ttl is not None else self._default_ttl
                    if ttl is None:
                        continue
                    try:
                        ttl_f = float(ttl)
                    except Exception:
                        ttl_f = 0.0
                    if ttl_f <= 0 or (now - rec.ts) >= ttl_f:
                        self._store.pop(k, None)
                        removed += 1
                self._last_prune_ts = now
        except Exception:
            # Never disrupt user code due to cleanup errors
            pass
