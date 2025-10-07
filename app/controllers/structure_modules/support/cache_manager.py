# app/controllers/structure_modules/cache_manager.py

"""Module for managing structure cache."""

import logging
from typing import Any, Optional

from app.utils.cache.base import InMemoryCache

logger = logging.getLogger(__name__)


class CacheManager:
    """Cache manager for optimizing structure queries.

    Added TTL and LRU limits for universal storage.
    Two compatible "first category" caching modes are supported:
      1) Global key (legacy): "first_category_id"
      2) Per-sphere key:      "first_category_id:{sphere_id}"
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        *,
        ttl: Optional[float] = None,
        max_size: Optional[int] = None,
    ):
        # Maintain backward compatibility: if logger not provided, use module logger
        self.logger = logger or globals().get("logger") or logging.getLogger(__name__)
        # Universal key-based cache storage with TTL/LRU
        # Best practice: use default TTL if not explicitly set
        default_ttl = 600.0 if ttl is None else ttl  # 10 minutes default
        self._cache = InMemoryCache(default_ttl=default_ttl, max_size=max_size)

    def get_first_category_id(self) -> Optional[int]:
        """Get cached first category ID."""
        return self._cache.get("first_category_id")

    def set_first_category_id(self, category_id: Optional[int]) -> None:
        """Set cached first category ID."""
        if category_id is None:
            # Reset key if None
            self._cache.invalidate("first_category_id")
            self.logger.debug("Reset first category ID cache (None)")
            return
        # Use unified cache with default TTL
        self._cache.set("first_category_id", int(category_id))
        self.logger.debug("Cached first category ID: %s", category_id)

    def invalidate_first_category_cache(self) -> None:
        """Invalidate first category cache when categories change."""
        self._cache.invalidate("first_category_id")
        self.logger.debug("Invalidated first category cache")

    # === Per-sphere cache for first category ===
    @staticmethod
    def _first_category_key_for_sphere(sphere_id: int) -> str:
        try:
            sid = int(sphere_id)
        except Exception:
            sid = sphere_id  # best-effort
        return f"first_category_id:{sid}"

    def get_first_category_id_for_sphere(self, sphere_id: int) -> Optional[int]:
        """Return cached first category ID for specific sphere."""
        key = self._first_category_key_for_sphere(sphere_id)
        return self._cache.get(key)

    def set_first_category_id_for_sphere(
        self, sphere_id: int, category_id: Optional[int]
    ) -> None:
        """Save/reset first category ID cache for specific sphere."""
        key = self._first_category_key_for_sphere(sphere_id)
        if category_id is None:
            self._cache.invalidate(key)
            self.logger.debug("Reset first category cache for sphere %s", sphere_id)
            return
        self._cache.set(key, int(category_id))
        self.logger.debug(
            "Cached first category ID for sphere %s: %s", sphere_id, category_id
        )

    def invalidate_first_category_cache_for_sphere(self, sphere_id: int) -> None:
        key = self._first_category_key_for_sphere(sphere_id)
        self._cache.invalidate(key)
        self.logger.debug(
            "Invalidated first category cache for sphere %s", sphere_id
        )

    # =============================
    # Universal caching operations
    # =============================
    def get(self, key: str) -> Optional[Any]:
        """Return value from cache by key or None if missing."""
        return self._cache.get(key)

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        """Save value to cache by key with optional TTL."""
        self._cache.set(key, value, ttl=ttl)
        self.logger.debug("Cache set: %s", key)

    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidate cache by key. If key not specified — clear entire cache."""
        if key is None:
            self._cache.clear()
            self.logger.debug("Cleared entire cache")
            return
        self._cache.invalidate(key)
        self.logger.debug("Invalidated cache: %s", key)

    def clear_all(self) -> None:
        """Clear entire cache."""
        self.invalidate()
