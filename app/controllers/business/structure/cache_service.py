"""Cache and data access helpers for structure business logic."""

from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING

try:
    from app.utils.metrics import get_metrics
    _metrics = get_metrics()
except ImportError:
    _metrics = None

if TYPE_CHECKING:  # pragma: no cover - typing only
    from logging import Logger

    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.controllers.structure_modules import CacheManager
    from app.controllers.structure_services.loader import LoaderService
    from app.controllers.structure_services.utilities import UtilityService
    from app.models import StructureModel
    from app.services.structure_service import StructureService


class StructureCacheService:
    """Provides cached access to spheres, sections, and categories."""

    def __init__(
        self,
        owner: 'StructureBusinessLogic',
        cache_manager: CacheManager,
        structure_service: StructureService,
        loader_service: LoaderService,
        utility_service: UtilityService,
        structure_model: StructureModel,
        logger: 'Logger',
    ) -> None:
        self._owner = owner
        self._cache_manager = cache_manager
        self._structure_service = structure_service
        self._loader_service = loader_service
        self._utility_service = utility_service
        self._structure_model = structure_model
        self._logger = logger

    def warm_first_category(self, sphere_id: int, payload: Optional[list[dict[str, Any]]]) -> None:
        """Прогревает кэш первой категории для сферы.
        
        Извлекает ID первой категории из payload и сохраняет в кэш.
        Используется для оптимизации навигации после загрузки структуры.
        
        Args:
            sphere_id: ID сферы для кэширования
            payload: Список разделов с вложенными категориями
        """
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            return
        if not payload:
            return
        for section in payload:
            categories = section.get("categories") if isinstance(section, dict) else None
            if not categories:
                continue
            first = categories[0]
            cid = first.get("id") if isinstance(first, dict) else None
            if isinstance(cid, int) and cid > 0:
                self._cache_manager.set(f"first_category_id:{sphere_id}", cid)
                break

    def schedule_reload(self, delay_ms: int) -> None:
        """Планирует перезагрузку структуры через async сервис владельца.
        
        Args:
            delay_ms: Задержка в миллисекундах перед перезагрузкой
        """
        async_service = getattr(self._owner, "async_service", None)
        if async_service and hasattr(async_service, "schedule_structure_reload"):
            async_service.schedule_structure_reload(delay_ms)

    def load_structure(self, sphere_id: int) -> list[dict[str, Any]]:
        """Load structure for a sphere, synchronize caches, and emit payload to the owner."""
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            self._logger.warning("load_structure called with invalid sphere_id: %s", sphere_id)
            try:
                self._owner.structure_loaded.emit([])
            except Exception:
                pass
            return []

        cache_key = f"structure_{sphere_id}"
        payload = self._cache_manager.get(cache_key)
        if payload is not None:
            if _metrics:
                _metrics.record_cache_hit("structure_cache")
        else:
            if _metrics:
                _metrics.record_cache_miss("structure_cache")
            try:
                payload = self._loader_service.load_structure_from_db(
                    self._structure_model,
                    sphere_id,
                    self._logger,
                ) or []
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.error("Failed to load structure for sphere %s: %s", sphere_id, exc, exc_info=True)
                payload = []
            self._cache_manager.set(cache_key, payload)

        try:
            sections_snapshot: list[dict[str, Any]] = []
            for section in payload or []:
                if not isinstance(section, dict):
                    continue
                section_id = section.get("id")
                if isinstance(section_id, int) and section_id > 0:
                    categories = section.get("categories") or []
                    self._cache_manager.set(f"categories_{section_id}", categories)
                sections_snapshot.append({k: v for k, v in section.items() if k != "categories"})

            if sections_snapshot:
                self._cache_manager.set(f"sections_{sphere_id}", sections_snapshot)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.debug("Failed to prime section/category caches: %s", exc, exc_info=True)

        try:
            self._owner.structure_loaded.emit(payload or [])
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.error("Failed to emit structure_loaded: %s", exc, exc_info=True)

        return payload or []

    def get_spheres(self) -> list[dict[str, Any]]:
        """Получает список всех сфер с кэшированием.
        
        ✅ Метрика кэша: отслеживается hit/miss rate.
        
        Returns:
            Список словарей с данными сфер
        """
        cache_key = "all_spheres"
        cached = self._cache_manager.get(cache_key)
        if cached is not None:
            if _metrics:
                _metrics.record_cache_hit("spheres_cache")
            return cached
        if _metrics:
            _metrics.record_cache_miss("spheres_cache")
        spheres = self._structure_service.get_spheres()
        self._cache_manager.set(cache_key, spheres)
        return spheres or []

    def get_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        """Получает разделы для сферы с кэшированием.
        
        ✅ Метрика кэша: отслеживается hit/miss rate.
        
        Args:
            sphere_id: ID сферы
            
        Returns:
            Список словарей с данными разделов
        """
        cache_key = f"sections_{sphere_id}"
        cached = self._cache_manager.get(cache_key)
        if cached is not None:
            if _metrics:
                _metrics.record_cache_hit("sections_cache")
            return cached
        if _metrics:
            _metrics.record_cache_miss("sections_cache")
        sections = self._structure_service.get_sections(sphere_id)
        self._cache_manager.set(cache_key, sections)
        return sections or []

    def get_categories(self, section_id: int) -> list[dict[str, Any]]:
        """Получает категории для раздела с кэшированием.
        
        ✅ Метрика кэша: отслеживается hit/miss rate.
        
        Args:
            section_id: ID раздела
            
        Returns:
            Список словарей с данными категорий
        """
        cache_key = f"categories_{section_id}"
        cached = self._cache_manager.get(cache_key)
        if cached is not None:
            if _metrics:
                _metrics.record_cache_hit("categories_cache")
            return cached
        if _metrics:
            _metrics.record_cache_miss("categories_cache")
        categories = self._structure_service.get_categories(section_id)
        self._cache_manager.set(cache_key, categories)
        return categories or []

    def get_links(self, category_id: int) -> list[dict[str, Any]]:
        return self._utility_service.get_links(
            self._structure_model, category_id, self._logger
        )

    def get_item_for_editing(
        self, item_id: int, item_type: Any
    ) -> Optional[dict[str, Any]]:
        return self._utility_service.get_item_for_editing(
            item_id=item_id,
            item_type=item_type,
            get_section_data=self._structure_model.get_section_data,
            get_category_data=self._structure_model.get_category_data,
            logger=self._logger,
        )

    def get_target_section_id(self) -> Optional[int]:
        return self._utility_service.get_target_section_id(
            current_sphere_id=self._owner.current_sphere_id,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            cache_get=self._cache_manager.get,
            cache_set=self._cache_manager.set,
        )

    # ------------------------------------------------------------------
    # Cache invalidation helpers
    # ------------------------------------------------------------------
    def invalidate_structure_cache(self, sphere_id: Optional[int] = None) -> None:
        target_sphere = sphere_id if sphere_id is not None else self._owner.current_sphere_id
        if target_sphere:
            self._cache_manager.invalidate(f"structure_{target_sphere}")
            self._cache_manager.invalidate(f"sections_{target_sphere}")
            self._cache_manager.invalidate(f"first_category_id:{target_sphere}")

    def invalidate_sections_cache(self, sphere_id: Optional[int]) -> None:
        if sphere_id:
            self._cache_manager.invalidate(f"sections_{sphere_id}")

    def invalidate_categories_cache(
        self, section_id: Optional[int], sphere_id: Optional[int] = None
    ) -> None:
        if section_id:
            self._cache_manager.invalidate(f"categories_{section_id}")
        self.invalidate_structure_cache(sphere_id)
