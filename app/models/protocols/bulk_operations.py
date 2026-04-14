"""Protocol for bulk operations on entities.

Defines unified interface for bulk CRUD operations.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class BulkOperations(Protocol[T]):
    """Protocol for bulk operations on entities.
    
    Provides unified interface for bulk create, update, delete operations.
    All implementations should manage transactions internally.
    """

    def insert_bulk(self, items: list[dict[str, Any]]) -> list[T]:
        """Bulk insert entities.
        
        Args:
            items: List of entity dicts to insert
            
        Returns:
            List of created entities with IDs
        """
        ...

    def update_bulk(self, updates: list[dict[str, Any]]) -> int:
        """Bulk update entities.
        
        Args:
            updates: List of entity dicts with 'id' and fields to update
            
        Returns:
            Number of entities updated
        """
        ...

    def delete_bulk(self, ids: list[int]) -> int:
        """Bulk delete entities.
        
        Args:
            ids: List of entity IDs to delete
            
        Returns:
            Number of entities deleted
        """
        ...


class BulkOperationResult:
    """Result of bulk operation with statistics."""

    def __init__(
        self,
        affected_count: int = 0,
        created_ids: list[int] | None = None,
        errors: list[str] | None = None,
        skipped_count: int = 0,
    ):
        """Initialize bulk operation result.
        
        Args:
            affected_count: Number of entities affected
            created_ids: List of created entity IDs
            errors: List of error messages
            skipped_count: Number of items skipped (e.g., duplicates)
        """
        self.affected_count = affected_count
        self.created_ids = created_ids or []
        self.errors = errors or []
        self.skipped_count = skipped_count

    def __repr__(self) -> str:
        return (
            f"BulkOperationResult(affected={self.affected_count}, "
            f"created={len(self.created_ids)}, "
            f"errors={len(self.errors)}, "
            f"skipped={self.skipped_count})"
        )


__all__ = ["BulkOperations", "BulkOperationResult"]
