from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from PyQt6.QtCore import QTimer


class CacheManager:
    """Управление кэшем данных."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}

        # Настройка автоочистки кэша
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._cleanup_expired_cache)
        self.cleanup_timer.start(300000)  # 5 минут

    def get(self, key: str, default=None) -> Any:
        """Получает значение из кэша."""
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Устанавливает значение в кэш."""
        self._cache[key] = value
        import time
        self._cache_timestamps[key] = time.time()

    def invalidate(self, pattern: str = None) -> None:
        """Инвалидирует кэш по паттерну или полностью."""
        if pattern:
            keys_to_remove = [key for key in self._cache.keys() if pattern in key]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()

    def _cleanup_expired_cache(self) -> None:
        """Очищает устаревшие записи кэша."""
        import time
        current_time = time.time()
        expired_keys = [
            key for key, timestamp in self._cache_timestamps.items()
            if current_time - timestamp > 1800  # 30 минут
        ]

        for key in expired_keys:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
