from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from app.controllers.domain.structure.validation.result import ValidationResult


class ValidationService:
    """Сервис валидации данных структуры."""

    def validate_section_data(
        self,
        data: Dict[str, Any],
        section_id: Optional[int],
        *,
        get_sections: Callable[[int], list],
    ) -> ValidationResult:
        result = ValidationResult()

        name = (data.get("name") or "").strip()
        if not name:
            result.add_error("Название раздела обязательно")

        sphere_id = data.get("sphere_id")
        if not sphere_id:
            result.add_error("ID сферы обязателен")

        if name and len(name) > 100:
            result.add_error("Название раздела не может быть длиннее 100 символов")

        if name and sphere_id:
            sections = get_sections(sphere_id) or []
            for section in sections:
                if (
                    section.get("name", "").lower() == name.lower()
                    and section.get("id") != section_id
                ):
                    result.add_error(
                        "Раздел с таким названием уже существует в этой сфере"
                    )
                    break

        return result

    def validate_category_data(
        self,
        data: Dict[str, Any],
        category_id: Optional[int],
        *,
        has_duplicate_category: Callable[[int, str, Optional[int]], bool],
    ) -> ValidationResult:
        result = ValidationResult()

        name = (data.get("name") or "").strip()
        if not name:
            result.add_error("Название категории обязательно")

        section_id = data.get("section_id")
        if not section_id:
            result.add_error("ID раздела обязателен")

        if name and len(name) > 100:
            result.add_error("Название категории не может быть длиннее 100 символов")

        if name and section_id:
            if has_duplicate_category(section_id, name, category_id):
                result.add_error(
                    "Категория с таким названием уже существует в этом разделе"
                )

        return result
