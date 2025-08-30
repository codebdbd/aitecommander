# app/controllers/structure_modules/cache_manager.py

"""Модуль для управления кэшем структуры."""

import logging
from typing import Any, Dict, Optional

from app.utils.cache.base import InMemoryCache

logger = logging.getLogger(__name__)


class CacheManager:
    """Менеджер кэша для оптимизации запросов к структуре.

    Добавлены TTL и LRU-лимиты для универсального хранилища.
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        *,
        ttl: Optional[float] = None,
        max_size: Optional[int] = None,
    ):
        # Поддерживаем обратную совместимость: если логгер не передан, используем модульный
        self.logger = logger or globals().get("logger") or logging.getLogger(__name__)
        self._first_category_id_cache: Optional[int] = None
        # Универсальное хранилище кэша по ключам с TTL/LRU
        self._cache = InMemoryCache(default_ttl=ttl, max_size=max_size)

    def get_first_category_id(self) -> Optional[int]:
        """Получает кэшированный ID первой категории."""
        return self._first_category_id_cache

    def set_first_category_id(self, category_id: Optional[int]) -> None:
        """Устанавливает кэшированный ID первой категории."""
        self._first_category_id_cache = category_id
        if category_id is not None:
            self.logger.debug(f"Кэширован ID первой категории: {category_id}")

    def invalidate_first_category_cache(self) -> None:
        """Инвалидирует кэш первой категории при изменениях в категориях."""
        if self._first_category_id_cache is not None:
            self.logger.debug("Инвалидирован кэш первой категории")
            self._first_category_id_cache = None

    # =============================
    # Универсальные операции кэширования
    # =============================
    def get(self, key: str) -> Optional[Any]:
        """Возвращает значение из кэша по ключу или None, если отсутствует."""
        return self._cache.get(key)

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        """Сохраняет значение в кэш по ключу с опциональным TTL."""
        self._cache.set(key, value, ttl=ttl)
        self.logger.debug(f"Кэш установлен: {key}")

    def invalidate(self, key: Optional[str] = None) -> None:
        """Инвалидирует кэш по ключу. Если key не указан — очищает весь кэш."""
        if key is None:
            self._cache.clear()
            self.logger.debug("Очищен весь кэш")
            return
        self._cache.invalidate(key)
        self.logger.debug(f"Инвалидирован кэш: {key}")

    def clear_all(self) -> None:
        """Очищает весь кэш."""
        self._first_category_id_cache = None
        self.invalidate()
