"""Validation module for structure data."""

from .validation import validate_category_data, validate_section_data
from .validation_result import ValidationResult

__all__ = [
    "validate_section_data",
    "validate_category_data",
    "ValidationResult",
]
