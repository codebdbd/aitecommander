# app/controllers/structure_modules/validation_api.py

"""Public API for validation system."""

import logging
from typing import Any

from ..models.types import StructureItemType
from .validation_result import ValidationResult
from .validation_rules import StructureDataValidator
from .validation_types import DetailedValidationResult, ValidationError

logger = logging.getLogger(__name__)


# Global validator instance
_validator = StructureDataValidator()


def validate_create_data(
    data: dict[str, Any], item_type: StructureItemType
) -> DetailedValidationResult:
    """Validate data for creating structure element."""
    if item_type == StructureItemType.SPHERE:
        return _validator.validate_sphere_create_data(data)
    elif item_type == StructureItemType.SECTION:
        return _validator.validate_section_create_data(data)
    elif item_type == StructureItemType.CATEGORY:
        return _validator.validate_category_create_data(data)
    else:
        raise ValueError(f"Unsupported item type: {item_type}")


def validate_update_data(
    data: dict[str, Any], item_type: StructureItemType
) -> DetailedValidationResult:
    """Validate data for updating structure element."""
    return _validator.validate_update_data(data, item_type)


def validate_and_raise(
    data: dict[str, Any], item_type: StructureItemType, is_update: bool = False
) -> None:
    """Validate data and raise exception on errors."""
    if is_update:
        result = validate_update_data(data, item_type)
    else:
        result = validate_create_data(data, item_type)

    if not result.is_valid:
        error_messages = [issue.message for issue in result.errors]
        raise ValidationError(
            f"Validation failed for {item_type.value}: {'; '.join(error_messages)}"
        )

    # Log warnings
    if result.warnings:
        warning_messages = [issue.message for issue in result.warnings]
        logger.warning(
            "Validation warnings for %s: %s",
            item_type.value,
            "; ".join(warning_messages),
        )


def safe_validate(
    data: dict[str, Any], item_type: StructureItemType, is_update: bool = False
) -> ValidationResult:
    """Safe validation, returning result without exceptions."""
    try:
        if is_update:
            result = validate_update_data(data, item_type)
        else:
            result = validate_create_data(data, item_type)

        return result.to_simple_result()
    except Exception as e:
        logger.exception("Unexpected error during validation: %s", e)
        return ValidationResult(
            is_valid=False, errors=[f"Validation error: {str(e)}"], warnings=[]
        )
