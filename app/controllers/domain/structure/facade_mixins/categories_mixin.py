from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.controllers.domain.structure.infrastructure.exceptions import handle_exceptions
from app.controllers.domain.structure.validation.result import ValidationResult


class CategoriesMixin:
    """Миксин с операциями по категориям (CRUD, выбор, загрузка)."""

    # ===== CRUD =====
    @handle_exceptions(default_return=False)
    def create_category(self, data: Dict[str, Any]) -> bool:
        validation: ValidationResult = self._validate_category_data(data)
        if not validation.is_valid:
            self._emit_error("Ошибка валидации", "; ".join(validation.errors))
            return False

        category_data = self.crud_service.create_category(self.structure_model, data, self.logger)
        if category_data:
            section_id = data.get('section_id')
            self._invalidate_categories_cache(section_id)
            parent_id = section_id or 0
            self.item_added.emit("category", parent_id, category_data)
            return True
        return False

    @handle_exceptions(default_return=False)
    def update_category(self, category_id: int, data: Dict[str, Any]) -> bool:
        validation: ValidationResult = self._validate_category_data(data, category_id)
        if not validation.is_valid:
            self._emit_error("Ошибка валидации", "; ".join(validation.errors))
            return False

        updated_data = self.crud_service.update_category(self.structure_model, category_id, data, self.logger)
        if updated_data:
            section_id = data.get('section_id') or updated_data.get('section_id')
            self._invalidate_categories_cache(section_id)
            self.item_updated.emit("category", category_id, updated_data)
            return True
        return False

    @handle_exceptions(default_return=(False, {}, 0))
    def delete_category(self, category_id: int) -> Tuple[bool, Dict[str, Any], int]:
        category_data = self.structure_model.get_category_data(category_id)
        if not category_data:
            return False, {}, 0

        success, category_data, _ = self.crud_service.delete_category(self.structure_model, category_id, self.logger)
        if success:
            section_id = category_data.get('section_id')
            self._invalidate_categories_cache(section_id)
            self.item_deleted.emit("category", category_id)
        return success, category_data, 0

    # ===== Selection & loading =====
    @handle_exceptions(default_return=[])
    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        cache_key = f"categories_{section_id}"
        cached_categories = self.cache_manager.get(cache_key)
        if cached_categories is not None:
            return cached_categories
        categories = self.selection_service.get_categories(self.structure_model, section_id, self.logger)
        result = categories or []
        self.cache_manager.set(cache_key, result)
        return result

    @handle_exceptions()
    def select_category(self, category_id: int) -> None:
        self.category_selected.emit(category_id)
        self.logger.debug(f"Выбрана категория {category_id}")

    @handle_exceptions()
    def get_category_data(self, category_id: int) -> Optional[Dict[str, Any]]:
        return self.structure_model.get_category_data(category_id)
