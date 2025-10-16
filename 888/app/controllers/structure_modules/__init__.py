# app/controllers/structure_modules/__init__.py

"""Модульная архитектура для бизнес-логики структуры."""

from .async_operations import AsyncOperations, AsyncSignalHandlers
from .base import StructureItemType
from .validators import ValidationError
from .cache_manager import CacheManager
from .category_operations import CategoryOperations
from .exceptions import handle_exceptions
from .normalization import normalize_rows

# LinkOperations удален - используйте LinksBusinessLogic
from .positioning_operations import PositioningOperations
from .section_operations import SectionOperations
from .sphere_operations import SphereOperations

# Избегаем раннего импорта validation.py, чтобы не создавать цикл зависимостей
from .validation_result import ValidationResult

__all__ = [
    # Base classes and constants
    "StructureItemType",
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
    "SphereOperations",
    "SectionOperations",
    "CategoryOperations",
    "PositioningOperations",
    "AsyncOperations",
    "AsyncSignalHandlers",
]


# Lazy import to avoid circular import during package initialization
def __getattr__(name):
    if name in ("validate_category_data", "validate_section_data"):
        from .validation import (
            validate_category_data,
            validate_section_data,
        )  # local import to break cycle

        return {
            "validate_category_data": validate_category_data,
            "validate_section_data": validate_section_data,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
