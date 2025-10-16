"""
Negative cache for icon paths, implemented as `NegativeCache` class,
compatible with the common `BaseCache` API.

Module public API:
- object `negative_cache: NegativeCache`
- wrapper functions: `is_negative(key)`, `mark_negative(key)`, `clear()`

`BaseCache` contract:
- get(key) -> Optional[Any]   # returns True if key is negative and still valid; otherwise None
- set(key, value, *, ttl: Optional[float] = None) -> None  # marks key as negative (value is ignored)
- invalidate(key: Optional[str] = None) -> None            # remove mark for key or clear everything
- clear() -> None                                          # synonym for invalidate(None)

Key is formed at the upper level (e.g., f"{theme}:{icon_name.lower()}").
"""

from __future__ import annotations

import heapq
import threading
import time
from typing import Any

from app.config_data import app_config
from app.utils.cache.base import BaseCache

_DEFAULT_TTL: float = 60.0
_MAX_TTL: float = 600.0
_MAX_STRIKES: int = 5  # default in case config is missing
_DEFAULT_MAX_SIZE: int = 1000  # safeguard against unlimited growth


def _base_ttl() -> float:
    try:
        return float(getattr(app_config, "icon_negative_cache_ttl", _DEFAULT_TTL))
    except Exception:
        return _DEFAULT_TTL


def _max_ttl() -> float:
    try:
        return float(getattr(app_config, "icon_negative_cache_ttl_max", _MAX_TTL))
    except Exception:
        return _MAX_TTL


def _max_size() -> int:
    """Maximum size of negative cache.

    Try to get from config if method/attribute
    `get_negative_cache_max_size` or `negative_cache_max_size` is available.
    Otherwise use default.
    """
    try:
        getter = getattr(app_config, "get_negative_cache_max_size", None)
        if callable(getter):
            return max(1, int(getter()))
        raw = getattr(app_config, "negative_cache_max_size", _DEFAULT_MAX_SIZE)
        return max(1, int(raw))
    except Exception:
        return _DEFAULT_MAX_SIZE


def _max_strikes() -> int:
    """Maximum number of accumulated misses (strikes) per key.

    Controls effective TTL growth. Made configurable to
    limit the aggressiveness of negative caching.
    """
    try:
        getter = getattr(app_config, "get_negative_cache_max_strikes", None)
        if callable(getter):
            return max(1, int(getter()))
        raw = getattr(app_config, "negative_cache_max_strikes", _MAX_STRIKES)
        return max(1, int(raw))
    except Exception:
        return _MAX_STRIKES


def get_ttl(strikes: int) -> float:
    base = _base_ttl()
    max_t = _max_ttl()
    # First strike uses base TTL; growth starts from the second
    ttl = base * (2 ** max(0, strikes - 1))
    return min(ttl, max_t)


class NegativeCache(BaseCache):
    """Extensible negative cache, compatible with BaseCache.

    Behavior:
    - set(key, value, ttl=None): marks key as negative; value is ignored.
    - get(key): returns True if key is negative and TTL has not expired; otherwise None.
    - invalidate(key): removes mark from key; invalidate(None)/clear() — clears entire cache.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ts: dict[str, float] = {}  # key -> timestamp of last mark
        self._strikes: dict[str, int] = {}  # key -> number of accumulated misses
        # Generations to prevent "dangling" elements effect in heaps
        self._gen: dict[str, int] = {}  # key -> current version of record
        # Heap by expiration time: (expire_ts, key, gen)
        self._expire_heap: list[tuple[float, str, int]] = []
        # Heap by mark time (for evicting oldest when overflow): (ts, key, gen)
        self._ts_heap: list[tuple[float, str, int]] = []

    # --- Config ---
    @staticmethod
    def base_ttl() -> float:  # for tests and clarity
        return _base_ttl()

    @staticmethod
    def max_ttl() -> float:
        return _max_ttl()

    @staticmethod
    def max_size() -> int:
        return _max_size()

    @staticmethod
    def max_strikes() -> int:
        return _max_strikes()

    @staticmethod
    def calc_ttl(strikes: int) -> float:
        return get_ttl(strikes)

    # --- BaseCache API ---
    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            ts = self._ts.get(key)
            if ts is None:
                return None
            strikes = self._strikes.get(key, 0)
            if now - ts < get_ttl(strikes):
                return True
            # Expired — soft decrement of strike and cleanup of mark
            # Invalidate all scheduled events through bump generation
            self._gen[key] = self._gen.get(key, 0) + 1
            if strikes > 0:
                self._strikes[key] = strikes - 1
            self._ts.pop(key, None)
            return None

    def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        # ttl is ignored: TTL is controlled based on strike and configuration
        now = time.time()
        with self._lock:
            # Incremental cleanup of expired items by expiration heap
            while self._expire_heap:
                exp_ts, k, g = self._expire_heap[0]
                if exp_ts > now:
                    break
                heapq.heappop(self._expire_heap)
                # Check record relevance
                if self._gen.get(k) != g:
                    continue
                # Expired: remove mark and softly decrease strikes
                self._ts.pop(k, None)
                s = self._strikes.get(k, 0)
                if s > 0:
                    self._strikes[k] = s - 1

            # Update current key
            new_gen = self._gen.get(key, 0) + 1
            self._gen[key] = new_gen
            self._ts[key] = now
            self._strikes[key] = min(self._strikes.get(key, 0) + 1, _max_strikes())
            # Schedule expiration time and add to heap
            expire_ts = now + get_ttl(self._strikes[key])
            heapq.heappush(self._expire_heap, (expire_ts, key, new_gen))
            # Add to mark time heap for evicting oldest
            heapq.heappush(self._ts_heap, (now, key, new_gen))

            # Size control: evict oldest by ts when overflow
            max_size = _max_size()
            while len(self._ts) > max_size and self._ts_heap:
                ts_old, k_old, g_old = heapq.heappop(self._ts_heap)
                if self._gen.get(k_old) != g_old:
                    continue  # outdated record in heap
                # Remove key
                # First bump generation to invalidate pending events
                self._gen[k_old] = self._gen.get(k_old, 0) + 1
                self._ts.pop(k_old, None)
                s = self._strikes.get(k_old, 0)
                if s > 0:
                    self._strikes[k_old] = s - 1

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._ts.clear()
                self._strikes.clear()
                self._gen.clear()
                self._expire_heap.clear()
                self._ts_heap.clear()
                return
            # bump generation to invalidate events
            self._gen[key] = self._gen.get(key, 0) + 1
            self._ts.pop(key, None)
            self._strikes.pop(key, None)

    # convenience methods
    def is_negative(self, key: str) -> bool:
        return bool(self.get(key))

    def mark_negative(self, key: str) -> None:
        self.set(key, True)

    def clear(self) -> None:
        self.invalidate(None)


# --- Global instance and wrapper functions ---
negative_cache = NegativeCache()


def is_negative(key: str) -> bool:
    return negative_cache.is_negative(key)


def mark_negative(key: str) -> None:
    negative_cache.mark_negative(key)


def clear() -> None:
    negative_cache.clear()
