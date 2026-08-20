"""
Application service layer.

This package contains the application's business logic encapsulated in service classes.
Services provide an abstraction layer between data stores (models) and views.

Key components:
- LinksService: manages links and their categories
- StructureService: handles application data structure
- UnitOfWork: Unit of Work pattern for transaction management
- DatabaseProtocol: interface for database operations
"""

__version__ = "1.1.4"

from .bulk_operation_service import BulkOperationService
from .links_service import LinksService
from .protocols import DatabaseProtocol
from .structure_context_service import StructureContextService
from .structure_service import StructureService
from .structure_share_service import StructureShareService
from .theme_import_service import ThemeImportService
from .theme_registry import ThemeRegistry
from .theme_stylesheet_service import ThemeStylesheetService
from .uow import UnitOfWork

__all__ = [
    "BulkOperationService",
    "DatabaseProtocol",
    "LinksService",
    "StructureContextService",
    "StructureService",
    "StructureShareService",
    "ThemeImportService",
    "ThemeRegistry",
    "ThemeStylesheetService",
    "UnitOfWork",
]
