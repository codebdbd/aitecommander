# app/controllers/structure_modules/validation.py

"""Centralized validation helpers delegating to ValidationService.

Return unified ValidationResult.
"""

from typing import Any, Callable, Optional

from app.controllers.structure_services.validation import ValidationService

from .validation_result import ValidationResult

_service = ValidationService()


def validate_section_data(
    data: dict[str, Any],
    *,
    section_id: Optional[int] = None,
    get_sections: Callable[[int], list],
) -> ValidationResult:
    """Validate section data through ValidationService.

    Args:
        data: section data
        section_id: id of section being edited (to exclude self in checks)
        get_sections: callback to get sections by sphere_id

    Returns:
        ValidationResult
    """
    return _service.validate_section_data(
        data=data, section_id=section_id, get_sections=get_sections
    )


def validate_category_data(
    data: dict[str, Any],
    *,
    category_id: Optional[int] = None,
    has_duplicate_category: Callable[[int, str, Optional[int]], bool],
) -> ValidationResult:
    """Validate category data through ValidationService.

    Args:
        data: category data
        category_id: id of category being edited
        has_duplicate_category: callback to check duplicates in section

    Returns:
        ValidationResult
    """
    return _service.validate_category_data(
        data=data,
        category_id=category_id,
        has_duplicate_category=has_duplicate_category,
    )
