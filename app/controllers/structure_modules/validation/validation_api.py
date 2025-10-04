# app/controllers/structure_modules/validation_api.py

"""Публичный API для системы валидации."""

import logging
from typing import Any, Dict

from ..models.types import StructureItemType
from .validation_result import ValidationResult
from .validation_types import DetailedValidationResult, ValidationError
from .validation_rules import StructureDataValidator

logger = logging.getLogger(__name__)


# Глобальный экземпляр валидатора
_validator = StructureDataValidator()


def validate_create_data(data: Dict[str, Any], item_type: StructureItemType) -> DetailedValidationResult:
    """Валидирует данные для создания элемента структуры."""
    if item_type == StructureItemType.SPHERE:
        return _validator.validate_sphere_create_data(data)
    elif item_type == StructureItemType.SECTION:
        return _validator.validate_section_create_data(data)
    elif item_type == StructureItemType.CATEGORY:
        return _validator.validate_category_create_data(data)
    else:
        raise ValueError(f"Unsupported item type: {item_type}")


def validate_update_data(data: Dict[str, Any], item_type: StructureItemType) -> DetailedValidationResult:
    """Валидирует данные для обновления элемента структуры."""
    return _validator.validate_update_data(data, item_type)


def validate_and_raise(data: Dict[str, Any], item_type: StructureItemType, is_update: bool = False) -> None:
    """Валидирует данные и выбрасывает исключение при ошибках."""
    if is_update:
        result = validate_update_data(data, item_type)
    else:
        result = validate_create_data(data, item_type)

    if not result.is_valid:
        error_messages = [issue.message for issue in result.errors]
        raise ValidationError(
            f"Validation failed for {item_type.value}: {'; '.join(error_messages)}"
        )

    # Логируем предупреждения
    if result.warnings:
        warning_messages = [issue.message for issue in result.warnings]
        logger.warning(
            "Validation warnings for %s: %s",
            item_type.value,
            "; ".join(warning_messages)
        )


def safe_validate(data: Dict[str, Any], item_type: StructureItemType, is_update: bool = False) -> ValidationResult:
    """Безопасная валидация, возвращающая результат без исключений."""
    try:
        if is_update:
            result = validate_update_data(data, item_type)
        else:
            result = validate_create_data(data, item_type)

        return result.to_simple_result()
    except Exception as e:
        logger.exception("Unexpected error during validation: %s", e)
        return ValidationResult(
            is_valid=False,
            errors=[f"Validation error: {str(e)}"],
            warnings=[]
        )
