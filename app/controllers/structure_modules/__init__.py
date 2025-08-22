# app/controllers/structure_modules/__init__.py

"""Модульная архитектура для бизнес-логики структуры."""

from .async_operations import AsyncOperations, AsyncSignalHandlers
from .base import ItemTypes, ItemTypeStr, StructureItemType, ValidationError
from .cache_manager import CacheManager
from .category_operations import CategoryOperations
from .coordination import OperationCoordinator
from .exceptions import handle_exceptions
from .legacy_support import LegacySupport, StructureBusinessLogicLegacy
from .normalization import normalize_row, normalize_rows, row_to_dict

# LinkOperations удален - используйте LinksBusinessLogic
from .positioning_operations import PositioningOperations
from .section_operations import SectionOperations
from .sphere_operations import SphereOperations
from .validation import (
    validate_category_data,
    validate_item_data,
    validate_section_data,
)
from .validation_result import ValidationResult

__all__ = [
    # Base classes and constants
    'StructureItemType',
    'ValidationError', 
    'ItemTypes',
    'ItemTypeStr',
    
    # Exceptions / results
    'handle_exceptions',
    'ValidationResult',
    
    # Validation
    'validate_item_data',
    'validate_section_data',
    'validate_category_data',
    
    # Normalization
    'normalize_row',
    'normalize_rows',
    'row_to_dict',
    
    # Core modules
    'CacheManager',
    'SphereOperations',
    'SectionOperations', 
    'CategoryOperations',
    'PositioningOperations',
    'AsyncOperations',
    'AsyncSignalHandlers',
    'OperationCoordinator',
    
    # Legacy support
    'LegacySupport',
    'StructureBusinessLogicLegacy'
]
