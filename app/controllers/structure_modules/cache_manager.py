# app/controllers/structure_modules/cache_manager.py

"""Модуль для управления кэшем структуры."""

import logging
from typing import Any, Optional

from app.utils.cache.base import InMemoryCache

logger = logging.getLogger(__name__)


class CacheManager:
    """Менеджер кэша для оптимизации запросов к структуре.

    Добавлены TTL и LRU-лимиты для универсального хранилища.
    Поддерживаются два совместимых режима кэширования "первой категории":
      1) Глобальный ключ (legacy): "first_category_id"
      2) Пер-сфера ключ:        "first_category_id:{sphere_id}"
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
        # Универсальное хранилище кэша по ключам с TTL/LRU
        # Best practice: используем дефолтный TTL, если не задан явно
        default_ttl = 600.0 if ttl is None else ttl  # 10 минут по умолчанию
        self._cache = InMemoryCache(default_ttl=default_ttl, max_size=max_size)

    def get_first_category_id(self) -> Optional[int]:
        """Получает кэшированный ID первой категории."""
        return self._cache.get("first_category_id")

    def set_first_category_id(self, category_id: Optional[int]) -> None:
        """Устанавливает кэшированный ID первой категории."""
        if category_id is None:
            # Сбрасываем ключ, если None
            self._cache.invalidate("first_category_id")
            self.logger.debug("Сброшен кэш ID первой категории (None)")
            return
        # Используем единый кэш с дефолтным TTL
        self._cache.set("first_category_id", int(category_id))
        self.logger.debug("Кэширован ID первой категории: %s", category_id)

    def invalidate_first_category_cache(self) -> None:
        """Инвалидирует кэш первой категории при изменениях в категориях."""
        self._cache.invalidate("first_category_id")
        self.logger.debug("Инвалидирован кэш первой категории")

    # === Пер-сфера кэш для первой категории ===
    @staticmethod
    def _first_category_key_for_sphere(sphere_id: int) -> str:
        try:
            sid = int(sphere_id)
        except Exception:
            sid = sphere_id  # best-effort
        return f"first_category_id:{sid}"

    def get_first_category_id_for_sphere(self, sphere_id: int) -> Optional[int]:
        """Возвращает кэшированный ID первой категории для конкретной сферы."""
        key = self._first_category_key_for_sphere(sphere_id)
        return self._cache.get(key)

    def set_first_category_id_for_sphere(
        self, sphere_id: int, category_id: Optional[int]
    ) -> None:
        """Сохраняет/сбрасывает кэш ID первой категории для конкретной сферы."""
        key = self._first_category_key_for_sphere(sphere_id)
        if category_id is None:
            self._cache.invalidate(key)
            self.logger.debug("Сброшен кэш первой категории для сферы %s", sphere_id)
            return
        self._cache.set(key, int(category_id))
        self.logger.debug(
            "Кэширован ID первой категории для сферы %s: %s", sphere_id, category_id
        )

    def invalidate_first_category_cache_for_sphere(self, sphere_id: int) -> None:
        key = self._first_category_key_for_sphere(sphere_id)
        self._cache.invalidate(key)
        self.logger.debug(
            "Инвалидирован кэш первой категории для сферы %s", sphere_id
        )

    # =============================
    # Универсальные операции кэширования
    # =============================
    def get(self, key: str) -> Optional[Any]:
        """Возвращает значение из кэша по ключу или None, если отсутствует."""
        return self._cache.get(key)

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        """Сохраняет значение в кэш по ключу с опциональным TTL."""
        self._cache.set(key, value, ttl=ttl)
        self.logger.debug("Кэш установлен: %s", key)

    def invalidate(self, key: Optional[str] = None) -> None:
        """Инвалидирует кэш по ключу. Если key не указан — очищает весь кэш."""
        if key is None:
            self._cache.clear()
            self.logger.debug("Очищен весь кэш")
            return
        self._cache.invalidate(key)
        self.logger.debug("Инвалидирован кэш: %s", key)

    def clear_all(self) -> None:
        """Очищает весь кэш."""
        self.invalidate()
