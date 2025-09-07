from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class SelectionService:
    """Сервис выборок и вычислений на базе модели (без Qt и кэша)."""

    def get_spheres(self, structure_model, logger) -> List[Dict[str, Any]]:
        try:
            spheres = structure_model.get_spheres() or []
            return spheres
        except Exception as e:  # noqa: BLE001
            if logger:
                logger.error("Ошибка получения сфер: %s", e)
            return []

    def get_sections(
        self, structure_model, sphere_id: int, logger
    ) -> List[Dict[str, Any]]:
        try:
            sections = structure_model.get_sections(sphere_id) or []
            return sections
        except Exception as e:  # noqa: BLE001
            if logger:
                logger.error(
                    "Ошибка получения разделов для сферы %s: %s", sphere_id, e
                )
            return []

    def get_categories(
        self, structure_model, section_id: int, logger
    ) -> List[Dict[str, Any]]:
        try:
            categories = structure_model.get_categories(section_id) or []
            return categories
        except Exception as e:  # noqa: BLE001
            if logger:
                logger.error(
                    "Ошибка получения категорий для раздела %s: %s", section_id, e
                )
            return []

    def get_first_category_id(
        self,
        current_sphere_id: Optional[int],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
    ) -> Optional[int]:
        if current_sphere_id is None:
            return None
        sections = get_sections(current_sphere_id) or []
        for section in sections:
            section_id = section.get("id")
            if section_id is None:
                continue
            categories = get_categories(section_id) or []
            if categories:
                return categories[0].get("id")
        return None
