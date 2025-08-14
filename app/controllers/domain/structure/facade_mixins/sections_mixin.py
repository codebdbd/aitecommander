from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.controllers.domain.structure.infrastructure.exceptions import handle_exceptions
from app.controllers.domain.structure.validation.result import ValidationResult


class SectionsMixin:
    """Миксин с операциями по разделам (CRUD, выбор, загрузка)."""

    # ===== CRUD =====
    @handle_exceptions(default_return=False)
    def create_section(self, data: Dict[str, Any]) -> bool:
        validation: ValidationResult = self._validate_section_data(data)
        if not validation.is_valid:
            self._emit_error("Ошибка валидации", "; ".join(validation.errors))
            return False

        section_data = self.crud_service.create_section(self.structure_model, data, self.logger)
        if section_data:
            self._invalidate_structure_cache()
            parent_id = data.get('sphere_id', 0)
            self.item_added.emit("section", parent_id, section_data)
            return True
        return False

    @handle_exceptions(default_return=False)
    def update_section(self, section_id: int, data: Dict[str, Any]) -> bool:
        validation: ValidationResult = self._validate_section_data(data, section_id)
        if not validation.is_valid:
            self._emit_error("Ошибка валидации", "; ".join(validation.errors))
            return False

        updated_data = self.crud_service.update_section(self.structure_model, section_id, data, self.logger)
        if updated_data:
            self._invalidate_structure_cache()
            self.item_updated.emit("section", section_id, updated_data)
            return True
        return False

    @handle_exceptions(default_return=(False, {}, 0, 0))
    def delete_section(self, section_id: int) -> Tuple[bool, Dict[str, Any], int, int]:
        section_data = self.structure_model.get_section_data(section_id)
        if not section_data:
            return False, {}, 0, 0

        categories = self.structure_model.get_categories(section_id)
        category_count = len(categories or [])
        if category_count > 0:
            # Раздел содержит категории - возвращаем информацию без удаления
            return False, section_data, category_count, 0

        success, section_data, _, _ = self.crud_service.delete_section(self.structure_model, section_id, self.logger)
        if success:
            self._invalidate_structure_cache()
            self.item_deleted.emit("section", section_id)
        return success, section_data, category_count, 0

    @handle_exceptions(default_return=False)
    def confirm_delete_section(self, section_id: int) -> bool:
        success = self.structure_model.delete_section(section_id)
        if success:
            self._invalidate_structure_cache()
            self.item_deleted.emit("section", section_id)
            self.logger.info(f"Принудительно удален раздел {section_id}")
        return success

    # ===== Selection & loading =====
    @handle_exceptions(default_return=[])
    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        cache_key = f"sections_{sphere_id}"
        cached_sections = self.cache_manager.get(cache_key)
        if cached_sections is not None:
            return cached_sections
        sections = self.selection_service.get_sections(self.structure_model, sphere_id, self.logger)
        if sections:
            self.cache_manager.set(cache_key, sections)
            return sections
        return []

    @handle_exceptions()
    def select_section(self, section_id: int) -> None:
        categories = self.get_categories(section_id)
        self.section_selected.emit(section_id, categories)
        self.logger.debug(f"Выбран раздел {section_id} с {len(categories)} категориями")

    @handle_exceptions()
    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        return self.structure_model.get_section_data(section_id)
