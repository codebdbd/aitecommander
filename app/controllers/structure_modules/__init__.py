# app/controllers/structure_modules/__init__.py

"""Модульная архитектура для бизнес-логики структуры."""

from .models.types import StructureItemType
from .operations.async_operations import AsyncOperations
from .operations.base import StructureOperationError
from .operations.category_operations import CategoryOperations
from .operations.positioning_operations import PositioningOperations
from .operations.section_operations import SectionOperations
from .operations.sphere_operations import SphereOperations
from .signals.handlers import AsyncSignalHandlers
from .signals.signals import StructureSignals
from .support.cache_manager import CacheManager
from .support.exceptions import handle_exceptions
from .support.helpers import process_item
from .support.normalization import normalize_rows
from .validation.validation_result import ValidationResult
from .validation.validators import ValidationError

__all__ = [
    # Base classes and constants
    "StructureItemType",
    "StructureOperationError",
    "ValidationError",
    # Exceptions / results
    "handle_exceptions",
    "ValidationResult",
    # Validation
    "validate_section_data",
    "validate_category_data",
    # Normalization
    "normalize_rows",
    # Core modules
    "CacheManager",
    "process_item",
    "SphereOperations",
    "SectionOperations",
    "CategoryOperations",
    "PositioningOperations",
    "AsyncOperations",
    "AsyncSignalHandlers",
    "StructureSignals",
]


# Lazy import to avoid circular import during package initialization
def __getattr__(name):
    if name in ("validate_category_data", "validate_section_data"):
        from .validation.validation import (
            validate_category_data,
            validate_section_data,
        )  # local import to break cycle

        return {
            "validate_category_data": validate_category_data,
            "validate_section_data": validate_section_data,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
