from __future__ import annotations

from typing import Any, Dict, List, Optional


class AsyncCompatMixin:
    """Миксин асинхронных заглушек (совместимость)."""

    def load_spheres_async(self) -> None:
        self.async_wrappers.load_spheres_async(
            get_spheres=self.get_spheres,
            emit_spheres_loaded=self.spheres_loaded.emit,
        )

    def load_structure_async(self, sphere_id: Optional[int] = None) -> None:
        self.async_wrappers.load_structure_async(
            load_structure=self.load_structure,
            sphere_id=sphere_id,
        )

    def load_sections_async(self, sphere_id: int) -> None:
        self.async_wrappers.load_sections_async(
            get_sections=self.get_sections,
            sphere_id=sphere_id,
        )

    def load_categories_async(self, section_id: int) -> None:
        self.async_wrappers.load_categories_async(
            get_categories=self.get_categories,
            section_id=section_id,
        )

    def create_section_async(self, data: Dict[str, Any]) -> None:
        # Используем реальный асинхронный слой (TaskScheduler + воркеры)
        # чтобы не блокировать UI
        if hasattr(self, 'async_operations'):
            self.async_operations.create_section_async(data)
        else:
            # Fallback на синхронную совместимость, если по каким-то причинам
            # async_operations недоступен (напр., в тестовом окружении)
            self.async_wrappers.create_section_async(
                create_section=self.create_section,
                data=data,
            )

    def create_category_async(self, data: Dict[str, Any]) -> None:
        self.async_wrappers.create_category_async(
            create_category=self.create_category,
            data=data,
        )

    def update_section_async(self, section_id: int, data: Dict[str, Any]) -> None:
        self.async_wrappers.update_section_async(
            update_section=self.update_section,
            section_id=section_id,
            data=data,
        )

    def update_category_async(self, category_id: int, data: Dict[str, Any]) -> None:
        self.async_wrappers.update_category_async(
            update_category=self.update_category,
            category_id=category_id,
            data=data,
        )

    def delete_section_async(self, section_id: int) -> None:
        self.async_wrappers.delete_section_async(
            delete_section=self.delete_section,
            section_id=section_id,
        )

    def delete_category_async(self, category_id: int) -> None:
        self.async_wrappers.delete_category_async(
            delete_category=self.delete_category,
            category_id=category_id,
        )

    def count_nested_objects_async(self, section_id: int) -> None:
        self.async_wrappers.count_nested_objects_async(
            get_categories=self.get_categories,
            section_id=section_id,
        )

    def get_first_category_id_async(self) -> None:
        self.async_wrappers.get_first_category_id_async(
            get_first_category_id=self.get_first_category_id,
            logger=self.logger,
        )
