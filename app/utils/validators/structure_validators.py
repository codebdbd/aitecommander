"""Legacy validators module — use app.controllers.structure_modules.validation instead.

Improvement note: This module now serves as a compatibility layer, re-exporting
validators from the canonical location to avoid breaking existing imports.
"""

import warnings
from typing import TYPE_CHECKING

# Re-export validators from canonical location
from app.controllers.structure_modules.validation.validation import (
    validate_category_data,
    validate_section_data,
)

if TYPE_CHECKING:
    pass


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
