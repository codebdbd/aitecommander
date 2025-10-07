# app/controllers/structure_modules/validators.py

"""Runtime validation for structure_modules - PyQt6 Best Practices.

This module provides runtime validation for all TypedDict structures
and input data. Uses built-in Python capabilities without external
dependencies for maximum compatibility.
"""

import logging
from typing import Any, Dict

from ..models.types import StructureItemType
from .validation_api import (
    validate_create_data, validate_update_data,
    validate_and_raise, safe_validate
)

logger = logging.getLogger(__name__)


# Export public API for backward compatibility
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

# Import classes for backward compatibility
from .validation_types import (
    ValidationError, ValidationSeverity, ValidationIssue, DetailedValidationResult
)
from .validation_core import TypeValidator
from .validation_rules import StructureDataValidator
