# lru_policy.py
"""
LRU caching policy for icons.

Purpose:
- Tracks key usage order.
- Removes least recently used items when overflow occurs.
- Synchronizes with external cache dictionary.

Complies with PEP 8.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from .lock_manager import acquire_lru_lock


class LRUPolicy:
    """Thread-safe implementation of LRU policy."""

    def __init__(self, maxsize: int) -> None:
        self.maxsize = max(1, int(maxsize))  # protection from 0 and negative values
        self.access_order: OrderedDict[str, None] = OrderedDict()
        # Use centralized locking system
        # self._lock replaced with lock_manager

    # --- Access API ---

    def access(self, key: str) -> None:
        """Register key access (move to end)."""
        with acquire_lru_lock():
            self.access_order[key] = None
            self.access_order.move_to_end(key)

    def evict_if_needed(
        self, cache: dict[str, Any], key: str
    ) -> tuple[bool, str | None]:
        """Check for overflow and return key for removal.

        Returns:
            (True, key) — if an element needs to be removed.
            (False, None) — if removal is not required.
        """
        with acquire_lru_lock():
            if len(cache) >= self.maxsize and key not in cache:
                try:
                    old_key, _ = self.access_order.popitem(last=False)
                    return True, old_key
                except KeyError:
                    # desynchronization between cache and access_order
                    return True, None
            return False, None

    def remove(self, key: str) -> None:
        """Remove key from access order."""
        with acquire_lru_lock():
            self.access_order.pop(key, None)

    def sync_with_cache(self, cache: dict[str, Any]) -> None:
        """Synchronize access order with actual cache content."""
        with acquire_lru_lock():
            # remove missing keys
            keys_to_remove = [k for k in self.access_order if k not in cache]
            for k in keys_to_remove:
                self.access_order.pop(k, None)

            # add new keys
            for k in cache:
                if k not in self.access_order:
                    self.access_order[k] = None

    def size(self) -> int:
        """Current number of tracked keys."""
        with acquire_lru_lock():
            return len(self.access_order)
