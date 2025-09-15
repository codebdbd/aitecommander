import warnings
from typing import Callable, Optional

from app.controllers.structure_modules.validation_result import ValidationResult
from app.controllers.structure_services.validation import ValidationService

_service = ValidationService()


def validate_section_data(
    data: dict,
    *,
    section_id: Optional[int] = None,
    get_sections: Callable[[int], list],
) -> ValidationResult:
    """Валидация раздела через ValidationService. Возвращает ValidationResult."""
    return _service.validate_section_data(
        data=data, section_id=section_id, get_sections=get_sections
    )


def validate_category_data(
    data: dict,
    *,
    category_id: Optional[int] = None,
    has_duplicate_category: Callable[[int, str, Optional[int]], bool],
) -> ValidationResult:
    """Валидация категории через ValidationService. Возвращает ValidationResult."""
    return _service.validate_category_data(
        data=data,
        category_id=category_id,
        has_duplicate_category=has_duplicate_category,
    )


# Универсальные проверки для имён сущностей структуры (оставляем как утилиты)
def is_non_empty_name(name: str) -> bool:
    """Имя не пустое после trim."""
    return isinstance(name, str) and name.strip() != ""


def is_name_length_ok(name: str, max_len: int = 255) -> bool:
    """Имя не превышает ограничение длины."""
    try:
        return len(name) <= max_len
    except Exception:
        return False


def has_no_forbidden_chars(name: str, forbidden: str = '\\/:*?"<>|') -> bool:
    """Имя не содержит запрещённых символов для Windows-путей и файлов."""
    return not any(ch in name for ch in forbidden)


# Совместимость: устаревшие bool-валидаторы
def validate_section_ok_bool(*args, **kwargs) -> bool:  # pragma: no cover
    warnings.warn(
        "validate_section_ok_bool устарел. Используйте validate_section_data (ValidationResult)",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        vr = validate_section_data(*args, **kwargs)
        return vr.is_valid
    except Exception:
        return False


def validate_category_ok_bool(*args, **kwargs) -> bool:  # pragma: no cover
    warnings.warn(
        "validate_category_ok_bool устарел. Используйте validate_category_data (ValidationResult)",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        vr = validate_category_data(*args, **kwargs)
        return vr.is_valid
    except Exception:
        return False
