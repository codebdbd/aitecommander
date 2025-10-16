import warnings
from typing import Callable, Optional

from app.controllers.structure_modules import ValidationResult
from app.controllers.structure_services.validation import ValidationService

_service = ValidationService()


def validate_section_data(
    data: dict,
    *,
    section_id: Optional[int] = None,
    get_sections: Callable[[int], list],
) -> ValidationResult:
    """Section validation via ValidationService. Returns ValidationResult."""
    return _service.validate_section_data(
        data=data, section_id=section_id, get_sections=get_sections
    )


def validate_category_data(
    data: dict,
    *,
    category_id: Optional[int] = None,
    has_duplicate_category: Callable[[int, str, Optional[int]], bool],
) -> ValidationResult:
    """Category validation via ValidationService. Returns ValidationResult."""
    return _service.validate_category_data(
        data=data,
        category_id=category_id,
        has_duplicate_category=has_duplicate_category,
    )


# Universal checks for structure entity names (kept as utilities)
def is_non_empty_name(name: str) -> bool:
    """Name is not empty after trim."""
    return isinstance(name, str) and name.strip() != ""


def is_name_length_ok(name: str, max_len: int = 255) -> bool:
    """Name does not exceed length limit."""
    try:
        return len(name) <= max_len
    except Exception:
        return False


def has_no_forbidden_chars(name: str, forbidden: str = '\\/:*?"<>|') -> bool:
    """Name does not contain forbidden characters for Windows paths and files."""
    if not isinstance(name, str):
        return False
    return not any(ch in name for ch in forbidden)


# Compatibility: deprecated bool validators
def validate_section_ok_bool(*args, **kwargs) -> bool:  # pragma: no cover
    warnings.warn(
        "validate_section_ok_bool is deprecated. Use validate_section_data (ValidationResult)",
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
        "validate_category_ok_bool is deprecated. Use validate_category_data (ValidationResult)",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        vr = validate_category_data(*args, **kwargs)
        return vr.is_valid
    except Exception:
        return False
