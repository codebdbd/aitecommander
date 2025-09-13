# app/controllers/structure_modules/validation.py

"""Централизованные хелперы валидации, делегирующие в ValidationService.

Возвращают единый ValidationResult.
"""

from typing import Any, Callable, Dict, Optional

from app.controllers.structure_services.validation import ValidationService

from .validation_result import ValidationResult

_service = ValidationService()


def validate_section_data(
    data: Dict[str, Any],
    *,
    section_id: Optional[int] = None,
    get_sections: Callable[[int], list],
) -> ValidationResult:
    """Валидация данных раздела через ValidationService.

    Args:
        data: данные раздела
        section_id: id редактируемого раздела (для исключения себя при проверках)
        get_sections: коллбек получения разделов по sphere_id

    Returns:
        ValidationResult
    """
    return _service.validate_section_data(
        data=data, section_id=section_id, get_sections=get_sections
    )


def validate_category_data(
    data: Dict[str, Any],
    *,
    category_id: Optional[int] = None,
    has_duplicate_category: Callable[[int, str, Optional[int]], bool],
) -> ValidationResult:
    """Валидация данных категории через ValidationService.

    Args:
        data: данные категории
        category_id: id редактируемой категории
        has_duplicate_category: коллбек проверки дубликатов в разделе

    Returns:
        ValidationResult
    """
    return _service.validate_category_data(
        data=data,
        category_id=category_id,
        has_duplicate_category=has_duplicate_category,
    )
