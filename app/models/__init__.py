# app/models/__init__.py

from .entities import CategoryModel, LinkModel, SectionModel, SphereModel, StructureModel
from .db import Database

# Export base classes and types for convenience
from .base import DatabaseBase, DatabaseError, ValidationError, db_lock
from .types import LinkType

# Export workers for async operations
from .workers import (
    DatabaseWorker,
    WorkerSignals,
    ImportStructureWorker,
    ExportStructureWorker,
    BackupWorker,
    InitializationWorker,
)

__all__ = [
    # Core
    "Database",
    # Models
    "StructureModel",
    "SphereModel",
    "SectionModel",
    "CategoryModel",
    "LinkModel",
    # Base
    "DatabaseBase",
    "DatabaseError",
    "ValidationError",
    "db_lock",
    # Types
    "LinkType",
    # Workers (async operations)
    "DatabaseWorker",
    "WorkerSignals",
    "ImportStructureWorker",
    "ExportStructureWorker",
    "BackupWorker",
    "InitializationWorker",
]
