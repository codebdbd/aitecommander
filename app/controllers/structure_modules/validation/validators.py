# app/controllers/structure_modules/validators.py

"""Runtime валидация для structure_modules - PyQt6 Best Practices.

Этот модуль предоставляет runtime валидацию для всех TypedDict структур
и входных данных. Использует встроенные возможности Python без внешних
зависимостей для максимальной совместимости.
"""

import logging
from typing import Any, Dict

from ..models.types import StructureItemType
from .validation_api import (
    validate_create_data, validate_update_data,
    validate_and_raise, safe_validate
)

logger = logging.getLogger(__name__)


# Экспорт публичного API для обратной совместимости
__all__ = [
    "validate_create_data",
    "validate_update_data",
    "validate_and_raise",
    "safe_validate",
    "ValidationError",
    "ValidationSeverity",
    "ValidationIssue",
    "DetailedValidationResult",
    "TypeValidator",
    "StructureDataValidator"
]

# Импорт классов для обратной совместимости
from .validation_types import (
    ValidationError, ValidationSeverity, ValidationIssue, DetailedValidationResult
)
from .validation_core import TypeValidator
from .validation_rules import StructureDataValidator
