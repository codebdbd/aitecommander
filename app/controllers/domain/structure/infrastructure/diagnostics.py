from __future__ import annotations

from typing import Any, Dict


class Diagnostics:
    """Инфраструктурные утилиты для диагностики и отладки."""

    @staticmethod
    def get_cache_info(cache_manager) -> Dict[str, Any]:
        """Возвращает краткую информацию о состоянии кэша.
        Ожидается совместимость с CacheManager, использующим _cache и _cache_timestamps.
        """
        try:
            cache = getattr(cache_manager, "_cache", {})
            timestamps = getattr(cache_manager, "_cache_timestamps", {})
            return {
                "cache_size": len(cache),
                "cached_keys": list(cache.keys()),
                "timestamps_count": len(timestamps),
            }
        except Exception:
            # В диагностике важно не падать — возвращаем безопасный минимум
            return {"cache_size": 0, "cached_keys": [], "timestamps_count": 0}
