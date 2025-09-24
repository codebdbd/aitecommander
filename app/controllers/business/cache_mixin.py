# app/controllers/business/cache_mixin.py
from typing import Any, Dict
from functools import lru_cache

class CacheMixin:
    """Миксин для кэширования результатов и lru_cache методов."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache: Dict[str, Any] = {}

    def _invalidate_cache(self):
        """Инвалидация кэша после обновлений."""
        self._cache.clear()
        if hasattr(self, '_get_all_links_safe'):
            self._get_all_links_safe.cache_clear()
