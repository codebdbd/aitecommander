from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from app.controllers.domain.structure.infrastructure.exceptions import handle_exceptions
from app.controllers.domain.structure.compat.types import StructureItemType


class UtilitiesMixin:
    """Миксин вспомогательных методов фасада."""

    @handle_exceptions()
    def get_first_category_id(self) -> Optional[int]:
        """Получает ID первой категории с кэшированием (делегировано UtilityService)."""
        return self.utility_service.get_first_category_id(
            current_sphere_id=self.current_sphere_id,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            cache_get=self.cache_manager.get,
            cache_set=self.cache_manager.set,
        )

    @handle_exceptions()
    def get_target_section_id(self) -> Optional[int]:
        """Получает ID первого доступного раздела в текущей сфере (делегировано UtilityService)."""
        return self.utility_service.get_target_section_id(
            current_sphere_id=self.current_sphere_id,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            cache_get=self.cache_manager.get,
            cache_set=self.cache_manager.set,
        )

    @handle_exceptions()
    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает иерархию для категории (делегировано UtilityService)."""
        return self.utility_service.get_category_hierarchy(
            category_id=category_id,
            get_category_data=self.get_category_data,
            get_section_data=self.get_section_data,
            get_sphere_by_id=self.get_sphere_by_id,
        )

    def get_item_for_editing(
        self, item_id: int, item_type: Union[StructureItemType, str]
    ) -> Optional[Dict[str, Any]]:
        """Универсальный метод получения данных элемента для редактирования."""
        return self.utility_service.get_item_for_editing(
            item_id=item_id,
            item_type=item_type,
            get_section_data=self.get_section_data,
            get_category_data=self.get_category_data,
            logger=self.logger,
        )

    @handle_exceptions(default_return=[])
    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        """DEPRECATED: для обратной совместимости (делегировано UtilityService)."""
        return self.utility_service.get_links(
            model=self.structure_model,
            category_id=category_id,
            logger=self.logger,
        )

    @handle_exceptions(default_return=False)
    def update_item_positions(self, table_name: str, ids_in_order: List[int]) -> bool:
        """Обновляет позиции элементов (делегировано UtilityService)."""
        return self.utility_service.update_item_positions(
            table_name=table_name,
            ids_in_order=ids_in_order,
            model=self.structure_model,
            cache_invalidate=self.cache_manager.invalidate,
            logger=self.logger,
        )
