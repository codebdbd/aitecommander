from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Union

from app.models.structure_model import StructureModel


class UtilityService:
    """Вспомогательные и совместимые операции для структуры."""

    def get_links(
        self,
        model: StructureModel,
        category_id: int,
        logger: Optional[logging.Logger] = None,
    ) -> List[Dict[str, Any]]:
        try:
            links = model.get_links(category_id)
            return links or []
        except Exception as e:
            if logger:
                logger.error(
                    f"Ошибка получения ссылок для категории {category_id}: {e}"
                )
            return []

    def get_item_for_editing(
        self,
        item_id: int,
        item_type: Union[str, Any],
        get_section_data: Callable[[int], Optional[Dict[str, Any]]],
        get_category_data: Callable[[int], Optional[Dict[str, Any]]],
        logger: Optional[logging.Logger] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            if not isinstance(item_type, str) and hasattr(item_type, "value"):
                item_type = item_type.value
            if item_type == "section":
                return get_section_data(item_id)
            if item_type == "category":
                return get_category_data(item_id)
            return None
        except Exception as e:
            if logger:
                logger.error(
                    f"Ошибка получения данных элемента {item_id} типа {item_type}: {e}"
                )
            return None

    def get_category_hierarchy(
        self,
        category_id: int,
        get_category_data: Callable[[int], Optional[Dict[str, Any]]],
        get_section_data: Callable[[int], Optional[Dict[str, Any]]],
        get_sphere_by_id: Callable[[int], Optional[Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        category_data = get_category_data(category_id)
        if not category_data:
            return None
        section_id = category_data.get("section_id")
        if not section_id:
            return None
        section_data = get_section_data(section_id)
        if not section_data:
            return None
        sphere_id = section_data.get("sphere_id")
        sphere_data = get_sphere_by_id(sphere_id) if sphere_id else None
        return {
            "category": category_data,
            "section": section_data,
            "sphere": sphere_data,
            "sphere_id": sphere_id,
        }

    def get_target_section_id(
        self,
        current_sphere_id: Optional[int],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        cache_get: Callable[[str], Any],
        cache_set: Callable[[str, Any], None],
    ) -> Optional[int]:
        if current_sphere_id is None:
            return None
        cache_key = f"first_category_{current_sphere_id}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
        sections = get_sections(current_sphere_id)
        for section in sections:
            categories = get_categories(section["id"])
            if categories:
                first_category_id = categories[0]["id"]
                cache_set(cache_key, first_category_id)
                return first_category_id
        cache_set(cache_key, None)
        return None

    def get_first_category_id(
        self,
        current_sphere_id: Optional[int],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        cache_get: Callable[[str], Any],
        cache_set: Callable[[str, Any], None],
    ) -> Optional[int]:
        # Логика идентична get_target_section_id
        return self.get_target_section_id(
            current_sphere_id,
            get_sections,
            get_categories,
            cache_get,
            cache_set,
        )

    def update_item_positions(
        self,
        table_name: str,
        ids_in_order: List[int],
        model: StructureModel,
        cache_invalidate: Callable[[str], None],
        logger: Optional[logging.Logger] = None,
    ) -> bool:
        try:
            for i, item_id in enumerate(ids_in_order):
                if table_name == "sections":
                    model.update_section(item_id, {"position": i + 1})
                elif table_name == "categories":
                    model.update_category(item_id, {"position": i + 1})
            cache_invalidate(table_name)
            return True
        except Exception as e:
            if logger:
                logger.error(f"Ошибка обновления позиций в {table_name}: {e}")
            return False
