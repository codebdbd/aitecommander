# app/controllers/structure_modules/queries.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional


class StructureQueries:
    """Фасад чтения данных структуры с кэшированием там, где это уместно.

    Не содержит логики сигналов/асинхронности.
    """

    def __init__(
        self,
        *,
        service,  # StructureService
        model,  # StructureModel
        cache_manager,  # совместимый интерфейс get/set/invalidate
        utility_service,  # UtilityService
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._service = service
        self._model = model
        self._cache = cache_manager
        self._util = utility_service
        self._log = logger or logging.getLogger(__name__)

    def get_spheres(self) -> List[Dict[str, Any]]:
        cache_key = "all_spheres"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        spheres = self._service.get_spheres() or []
        self._cache.set(cache_key, spheres)
        return spheres

    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        cache_key = f"sections_{sphere_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        sections = self._service.get_sections(sphere_id) or []
        self._cache.set(cache_key, sections)
        return sections

    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        cache_key = f"categories_{section_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        categories = self._service.get_categories(section_id) or []
        self._cache.set(cache_key, categories)
        return categories

    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        # Сохранено предыдущее поведение: без кэширования
        return self._util.get_links(self._model, category_id, self._log)

    # ------- Хелперы редактирования и цели -------
    def get_item_for_editing(self, item_id: int, item_type: Any) -> Optional[Dict[str, Any]]:
        return self._util.get_item_for_editing(
            item_id=item_id,
            item_type=item_type,
            get_section_data=self._model.get_section_data,
            get_category_data=self._model.get_category_data,
            logger=self._log,
        )

    def get_first_category_id(self, current_sphere_id: Optional[int]) -> Optional[int]:
        return self._util.get_first_category_id(
            current_sphere_id=current_sphere_id,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            cache_get=self._cache.get,
            cache_set=self._cache.set,
        )

    def get_target_section_id(self, current_sphere_id: Optional[int]) -> Optional[int]:
        return self._util.get_target_section_id(
            current_sphere_id=current_sphere_id,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            cache_get=self._cache.get,
            cache_set=self._cache.set,
        )
