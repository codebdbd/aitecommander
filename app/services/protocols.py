"""
Protocols for service layer.

✅ NEW FILE: Strict typing of dependencies through Protocol.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol, TypeAlias

from app.models.types.category_types import BulkInsertResult, CategoryDict
from app.models.types.link_types import LinkInput

StructureRow: TypeAlias = dict[str, object]
StructureList: TypeAlias = list[StructureRow]
StructureExport: TypeAlias = dict[str, list[StructureRow]]
ImportStats: TypeAlias = dict[str, int]
FinishedCallback: TypeAlias = Callable[[StructureExport], None]
ImportFinishedCallback: TypeAlias = Callable[[ImportStats], None]
ErrorCallback: TypeAlias = Callable[[Exception, str], None]
ProgressCallback: TypeAlias = Callable[[int, int, str], None]


class DatabaseProtocol(Protocol):
    """Protocol for Database with necessary attributes for services.

    ✅ FIX: Replaces Any with specific Protocol for type safety.
    """

    # Repositories/models
    spheres: object
    sections: object
    categories: object
    links: object

    # Transaction methods
    def transaction(self) -> AbstractContextManager[None]:
        """Transaction context manager."""
        ...

    def commit(self) -> None:
        """Commits transaction."""
        ...

    def rollback(self) -> None:
        """Rolls back transaction."""
        ...

    # Import/export methods
    def get_full_structure(self) -> StructureList:
        """Returns full data structure."""
        ...

    def export_full_structure(self) -> StructureExport:
        """Exports structure."""
        ...

    def export_full_structure_async(
        self,
        on_finished: FinishedCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Asynchronous structure export."""
        ...

    def import_full_structure(self, data: StructureList) -> None:
        """Imports structure."""
        ...

    def import_full_structure_async(
        self,
        data: StructureList,
        on_finished: ImportFinishedCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Asynchronous structure import."""
        ...

    def export_section_tree(self, section_id: int) -> StructureRow:
        """Exports section."""
        ...

    def import_section_tree(self, tree: StructureRow) -> None:
        """Imports section."""
        ...

    def export_category_tree(self, category_id: int) -> StructureRow:
        """Exports category."""
        ...

    def import_category_tree(self, tree: StructureRow) -> None:
        """Imports category."""
        ...

    def import_category_trees_bulk(self, trees: list[StructureRow]) -> None:
        """Imports multiple categories."""
        ...


class CategoryRepositoryProtocol(Protocol):
    """Protocol for category repository used by bulk operations."""

    def insert_categories_bulk(self, items: list[CategoryDict]) -> BulkInsertResult:
        ...

    def update_categories_bulk(self, updates: list[CategoryDict]) -> int:
        ...

    def delete_categories_bulk(self, category_ids: list[int]) -> int:
        ...

    def move_categories_to_section_bulk(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        ...


class LinkRepositoryProtocol(Protocol):
    """Protocol for link repository used by bulk operations."""

    def batch_upsert_links(self, links_data: list[LinkInput]) -> list[int]:
        ...

    def batch_update_links(self, links_data: list[LinkInput]) -> bool:
        ...

    def batch_delete_links(self, link_ids: list[int]) -> int:
        ...

    def move_links_bulk(self, link_ids: list[int], target_category_id: int) -> int:
        ...


class SectionRepositoryProtocol(Protocol):
    """Protocol for section repository used by bulk operations."""

    def delete_sections_bulk(self, section_ids: list[int]) -> int:
        ...


class BulkDatabaseProtocol(Protocol):
    """Database protocol for bulk operation service."""

    sections: SectionRepositoryProtocol
    categories: CategoryRepositoryProtocol
    links: LinkRepositoryProtocol


__all__ = [
    "BulkDatabaseProtocol",
    "CategoryRepositoryProtocol",
    "DatabaseProtocol",
    "LinkRepositoryProtocol",
    "SectionRepositoryProtocol",
]
