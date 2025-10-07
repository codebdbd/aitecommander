from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from app.controllers.structure_modules import ValidationResult

# Module logger for diagnostic messages
logger = logging.getLogger(__name__)


class ValidationService:
    """Structure data validation service."""

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
            result.add_error("Section name is required")

        sphere_id = data.get("sphere_id")
        if not sphere_id:
            result.add_error("Sphere ID is required")

        if name and len(name) > 100:
            result.add_error("Section name cannot be longer than 100 characters")

        if name and sphere_id:
            sections = get_sections(sphere_id) or []
            for section in sections:
                if (
                    section.get("name", "").lower() == name.lower()
                    and section.get("id") != section_id
                ):
                    result.add_error(
                        "Section with this name already exists in this sphere"
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
            result.add_error("Category name is required")

        section_id = data.get("section_id")
        if not section_id:
            result.add_error("Section ID is required")

        if name and len(name) > 100:
            result.add_error("Category name cannot be longer than 100 characters")

        if name and section_id:
            if has_duplicate_category(section_id, name, category_id):
                result.add_error(
                    "Category with this name already exists in this section"
                )

        return result
