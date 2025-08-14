# app/controllers/structure_modules/cache_manager.py

"""Модуль для управления кэшем структуры."""

import logging
from typing import Optional


class CacheManager:
    """Менеджер кэша для оптимизации запросов к структуре."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._first_category_id_cache: Optional[int] = None
    
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
    
    def clear_all(self) -> None:
        """Очищает весь кэш."""
        self._first_category_id_cache = None
        self.logger.debug("Очищен весь кэш")
