# app/controllers/business/structure_cache.py

from __future__ import annotations

import logging
from typing import Callable, Optional


class StructureCache:
    """Фасад для операций с кэшем структуры.

    Не хранит ссылок на БД/сервисы, работает поверх переданного cache_manager.
    Позволяет изолировать логику инвалидирования и упростить тестирование.
    """

    def __init__(
        self,
        *,
        cache_manager: object,
        get_current_sphere_id: Callable[[], Optional[int]],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._cache = cache_manager
        self._get_current_sphere_id = get_current_sphere_id
        self._logger = logger or logging.getLogger(__name__)

    # Публичные методы для использования из Business-слоя
    def invalidate_structure(self) -> None:
        """Инвалидирует кэш структуры и разделов для текущей сферы."""
        try:
            sphere_id = self._get_current_sphere_id()
            if sphere_id:
                self._cache.invalidate(f"structure_{sphere_id}")
                self._cache.invalidate(f"sections_{sphere_id}")
                self._cache.invalidate(f"first_category_id:{sphere_id}")
        except Exception as e:
            self._logger.debug("StructureCache.invalidate_structure failed: %s", e, exc_info=True)

    def invalidate_categories(self, section_id: Optional[int]) -> None:
        """Инвалидирует кэш категорий раздела и связанную структуру."""
        try:
            if section_id:
                self._cache.invalidate(f"categories_{section_id}")
        finally:
            # Структура зависит от категорий — инвалидируем всегда
            self.invalidate_structure()

    # Утилиты прямого доступа (на случай тестов/расширений)
    def get(self, key: str):  # type: ignore[no-untyped-def]
        return self._cache.get(key)

    def set(self, key: str, value):  # type: ignore[no-untyped-def]
        return self._cache.set(key, value)

    def clear_all(self) -> None:
        try:
            self._cache.invalidate()
        except Exception as e:
            self._logger.debug("StructureCache.clear_all failed: %s", e, exc_info=True)
