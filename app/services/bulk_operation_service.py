"""Bulk operation service for sections, categories, and links.

Provides a unified interface for bulk create/update/delete/move operations with
consistent logging, error handling, optional batch size limits, and timing logs.
"""

from __future__ import annotations

import logging

from app.models.types.category_types import CategoryDict
from app.models.types.link_types import LinkInput
from app.services.batch_operation_base import (
    BaseBatchOperation,
    BulkOperationError,
    BulkOperationRepositoryError,
    BulkOperationValidationError,
    ERROR_CODE_BATCH_SIZE,
    ERROR_CODE_REPOSITORY,
    ERROR_CODE_VALIDATION,
)
from app.services.protocols import BulkDatabaseProtocol

logger = logging.getLogger(__name__)


class BulkOperationService(BaseBatchOperation):
    """Service layer wrapper for section/category/link bulk operations.

    Invalid items in bulk payloads are skipped with warnings; invalid
    operation-level parameters raise validation errors.
    """

    def __init__(
        self,
        db: BulkDatabaseProtocol,
        *,
        max_batch_size: int | None = None,
    ) -> None:
        """Initialize bulk operation service.
        
        Args:
            db: Database instance
            max_batch_size: Maximum allowed items per bulk operation; <=0 disables.
                Defaults to limits.bulk_operation_max_batch_size (5000).
        """
        self.db = db
        if max_batch_size is None:
            from app.config_data.runtime_config import runtime_app_config as app_config

            max_batch_size = int(
                app_config.limits.get_bulk_operation_max_batch_size()
            )
        if max_batch_size is not None and max_batch_size > 0:
            self._validate_positive_int(max_batch_size, "max_batch_size", "__init__")
        if max_batch_size is not None and max_batch_size <= 0:
            max_batch_size = None
        super().__init__(logger=logger, max_batch_size=max_batch_size)

    # ========== Category Bulk Operations ==========

    def create_categories_bulk(self, items: list[CategoryDict]) -> list[CategoryDict]:
        """Bulk create categories.
        
        Args:
            items: List of category dicts with 'name', 'section_id', etc.
            
        Returns:
            List of created categories with IDs
        """
        if not items:
            logger.debug("Bulk create categories skipped: empty payload")
            return []
        original_count = len(items)
        items = self._filter_items(
            items,
            required_int_fields=("section_id",),
            required_str_fields=("name",),
            operation="create_categories_bulk",
        )
        if not items:
            logger.warning("create_categories_bulk: no valid items to process")
            return []
        skipped = original_count - len(items)

        def _process(chunk: list[CategoryDict]) -> list[CategoryDict]:
            result = self.db.categories.insert_categories_bulk(chunk)
            return result["inserted"]

        def _combine(results: list[list[CategoryDict]]) -> list[CategoryDict]:
            merged: list[CategoryDict] = []
            for part in results:
                merged.extend(part)
            return merged

        return self._execute_batch(
            operation="create_categories_bulk",
            items=items,
            process_chunk=_process,
            combine_results=_combine,
            empty_result=[],
            skipped=skipped,
            allow_chunking=False,
            error_message="Bulk create categories failed",
        )

    def update_categories_bulk(self, updates: list[CategoryDict]) -> int:
        """Bulk update categories.
        
        Args:
            updates: List of category dicts with 'id' and fields to update
            
        Returns:
            Number of categories updated

        Notes:
            Empty input returns 0 (no-op).
        """
        if not updates:
            logger.debug("Bulk update categories skipped: empty payload")
            return 0
        original_count = len(updates)
        updates = self._filter_items(
            updates,
            required_int_fields=("id",),
            operation="update_categories_bulk",
        )
        if not updates:
            logger.warning("update_categories_bulk: no valid items to process")
            return 0
        skipped = original_count - len(updates)

        def _process(chunk: list[CategoryDict]) -> int:
            return self.db.categories.update_categories_bulk(chunk)

        def _combine(results: list[int]) -> int:
            return sum(results)

        return self._execute_batch(
            operation="update_categories_bulk",
            items=updates,
            process_chunk=_process,
            combine_results=_combine,
            empty_result=0,
            skipped=skipped,
            allow_chunking=False,
            error_message="Bulk update categories failed",
        )

    def delete_categories_bulk(self, category_ids: list[int]) -> int:
        """Bulk delete categories.
        
        Args:
            category_ids: List of category IDs to delete
            
        Returns:
            Number of categories deleted
        """
        if not category_ids:
            logger.debug("Bulk delete categories skipped: empty id list")
            return 0
        original_count = len(category_ids)
        category_ids = self._filter_ids(
            category_ids, operation="delete_categories_bulk"
        )
        if not category_ids:
            logger.warning("delete_categories_bulk: no valid ids to process")
            return 0
        skipped = original_count - len(category_ids)

        def _process(chunk: list[int]) -> int:
            return self.db.categories.delete_categories_bulk(chunk)

        def _combine(results: list[int]) -> int:
            return sum(results)

        return self._execute_batch(
            operation="delete_categories_bulk",
            items=category_ids,
            process_chunk=_process,
            combine_results=_combine,
            empty_result=0,
            skipped=skipped,
            allow_chunking=False,
            error_message="Bulk delete categories failed",
        )

    def move_categories_bulk(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        """Bulk move categories to another section.
        
        Args:
            category_ids: List of category IDs to move
            target_section_id: Target section ID
            base_row: Starting position in target section
            
        Returns:
            List of actually moved category IDs (duplicates skipped)
        """
        if not category_ids:
            logger.debug("Bulk move categories skipped: empty id list")
            return []
        original_count = len(category_ids)
        category_ids = self._filter_ids(
            category_ids, operation="move_categories_bulk"
        )
        if not category_ids:
            logger.warning("move_categories_bulk: no valid ids to process")
            return []
        skipped = original_count - len(category_ids)
        self._validate_positive_int(
            target_section_id, "target_section_id", "move_categories_bulk"
        )
        self._validate_non_negative_int(
            base_row, "base_row", "move_categories_bulk"
        )

        def _process(chunk: list[int]) -> list[int]:
            return self.db.categories.move_categories_to_section_bulk(
                chunk, target_section_id, base_row
            )

        def _combine(results: list[list[int]]) -> list[int]:
            merged: list[int] = []
            seen: set[int] = set()
            for part in results:
                for cid in part:
                    if cid not in seen:
                        seen.add(cid)
                        merged.append(cid)
            return merged

        return self._execute_batch(
            operation="move_categories_bulk",
            items=category_ids,
            process_chunk=_process,
            combine_results=_combine,
            empty_result=[],
            skipped=skipped,
            allow_chunking=False,
            error_message="Bulk move categories failed",
        )

    # ========== Section Bulk Operations ==========

    def delete_sections_bulk(self, section_ids: list[int]) -> int:
        """Bulk delete sections.

        Args:
            section_ids: List of section IDs to delete

        Returns:
            Number of sections deleted
        """
        if not section_ids:
            logger.debug("Bulk delete sections skipped: empty id list")
            return 0
        original_count = len(section_ids)
        section_ids = self._filter_ids(
            section_ids, operation="delete_sections_bulk"
        )
        if not section_ids:
            logger.warning("delete_sections_bulk: no valid ids to process")
            return 0
        skipped = original_count - len(section_ids)

        def _process(chunk: list[int]) -> int:
            return self.db.sections.delete_sections_bulk(chunk)

        def _combine(results: list[int]) -> int:
            return sum(results)

        return self._execute_batch(
            operation="delete_sections_bulk",
            items=section_ids,
            process_chunk=_process,
            combine_results=_combine,
            empty_result=0,
            skipped=skipped,
            allow_chunking=False,
            error_message="Bulk delete sections failed",
        )

    # ========== Link Bulk Operations ==========

    def create_links_bulk(self, links_data: list[LinkInput]) -> list[int]:
        """Bulk create/upsert links.
        
        Args:
            links_data: List of link dicts
            
        Returns:
            List of created link IDs
        """
        if not links_data:
            logger.debug("Bulk create links skipped: empty payload")
            return []
        original_count = len(links_data)
        links_data = self._filter_items(
            links_data,
            required_fields=("category_id",),
            operation="create_links_bulk",
        )
        if not links_data:
            logger.warning("create_links_bulk: no valid items to process")
            return []
        skipped = original_count - len(links_data)

        def _process(chunk: list[LinkInput]) -> list[int]:
            return self.db.links.batch_upsert_links(chunk)

        def _combine(results: list[list[int]]) -> list[int]:
            merged: list[int] = []
            for part in results:
                merged.extend(part)
            return merged

        return self._execute_batch(
            operation="create_links_bulk",
            items=links_data,
            process_chunk=_process,
            combine_results=_combine,
            empty_result=[],
            skipped=skipped,
            allow_chunking=False,
            error_message="Bulk create links failed",
        )

    def update_links_bulk(self, links_data: list[LinkInput]) -> bool:
        """Bulk update links.
        
        Args:
            links_data: List of link dicts with 'id' and fields to update
            
        Returns:
            True if successful

        Notes:
            Empty input returns True (no-op).
        """
        if not links_data:
            logger.debug("Bulk update links skipped: empty payload")
            return True
        original_count = len(links_data)
        links_data = self._filter_items(
            links_data,
            required_int_fields=("id",),
            operation="update_links_bulk",
        )
        if not links_data:
            logger.warning("update_links_bulk: no valid items to process")
            return True
        skipped = original_count - len(links_data)

        def _process(chunk: list[LinkInput]) -> bool:
            return bool(self.db.links.batch_update_links(chunk))

        def _combine(results: list[bool]) -> bool:
            return all(results) if results else True

        return self._execute_batch(
            operation="update_links_bulk",
            items=links_data,
            process_chunk=_process,
            combine_results=_combine,
            empty_result=True,
            skipped=skipped,
            allow_chunking=False,
            error_message="Bulk update links failed",
        )

    def delete_links_bulk(self, link_ids: list[int]) -> int:
        """Bulk delete links.
        
        Args:
            link_ids: List of link IDs to delete
            
        Returns:
            Number of links deleted
        """
        if not link_ids:
            logger.debug("Bulk delete links skipped: empty id list")
            return 0
        original_count = len(link_ids)
        link_ids = self._filter_ids(link_ids, operation="delete_links_bulk")
        if not link_ids:
            logger.warning("delete_links_bulk: no valid ids to process")
            return 0
        skipped = original_count - len(link_ids)

        def _process(chunk: list[int]) -> int:
            return self.db.links.batch_delete_links(chunk)

        def _combine(results: list[int]) -> int:
            return sum(results)

        return self._execute_batch(
            operation="delete_links_bulk",
            items=link_ids,
            process_chunk=_process,
            combine_results=_combine,
            empty_result=0,
            skipped=skipped,
            allow_chunking=False,
            error_message="Bulk delete links failed",
        )

    def move_links_bulk(self, link_ids: list[int], target_category_id: int) -> int:
        """Bulk move links to another category.
        
        Args:
            link_ids: List of link IDs to move
            target_category_id: Target category ID
            
        Returns:
            Number of links moved
        """
        if not link_ids:
            logger.debug("Bulk move links skipped: empty id list")
            return 0
        original_count = len(link_ids)
        link_ids = self._filter_ids(link_ids, operation="move_links_bulk")
        if not link_ids:
            logger.warning("move_links_bulk: no valid ids to process")
            return 0
        skipped = original_count - len(link_ids)
        self._validate_positive_int(
            target_category_id, "target_category_id", "move_links_bulk"
        )

        def _process(chunk: list[int]) -> int:
            return self.db.links.move_links_bulk(chunk, target_category_id)

        def _combine(results: list[int]) -> int:
            return sum(results)

        return self._execute_batch(
            operation="move_links_bulk",
            items=link_ids,
            process_chunk=_process,
            combine_results=_combine,
            empty_result=0,
            skipped=skipped,
            allow_chunking=False,
            error_message="Bulk move links failed",
        )

    def _filter_items(
        self,
        items: list[dict],
        *,
        required_fields: tuple[str, ...] = (),
        required_int_fields: tuple[str, ...] = (),
        required_str_fields: tuple[str, ...] = (),
        operation: str,
    ) -> list[dict]:
        if not isinstance(items, list):
            raise BulkOperationValidationError(
                f"{operation}: expected list, got {type(items).__name__}"
            )
        valid: list[dict] = []
        errors: list[str] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"item {idx} not a dict")
                continue
            if not self._has_required_fields(item, required_fields, idx, errors):
                continue
            if not self._has_required_int_fields(item, required_int_fields, idx, errors):
                continue
            if not self._has_required_str_fields(item, required_str_fields, idx, errors):
                continue
            valid.append(item)
        if errors:
            skipped = len(items) - len(valid)
            preview = "; ".join(errors[:3])
            logger.warning(
                "%s: skipped %d invalid items (%s)", operation, skipped, preview
            )
        return valid

    def _has_required_fields(
        self,
        item: dict,
        required_fields: tuple[str, ...],
        idx: int,
        errors: list[str],
    ) -> bool:
        """Validate presence of required fields in item."""
        for key in required_fields:
            if key not in item:
                errors.append(f"item {idx} missing {key}")
                return False
        return True

    def _has_required_int_fields(
        self,
        item: dict,
        required_int_fields: tuple[str, ...],
        idx: int,
        errors: list[str],
    ) -> bool:
        """Validate required integer fields (positive ints)."""
        for key in required_int_fields:
            value = item.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                errors.append(f"item {idx} invalid {key}")
                return False
        return True

    def _has_required_str_fields(
        self,
        item: dict,
        required_str_fields: tuple[str, ...],
        idx: int,
        errors: list[str],
    ) -> bool:
        """Validate required non-empty string fields."""
        for key in required_str_fields:
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"item {idx} invalid {key}")
                return False
        return True

    def _validate_batch_size(self, count: int, operation: str) -> None:
        if self._max_batch_size is None:
            return
        if count > self._max_batch_size:
            raise BulkOperationValidationError(
                f"{operation}: batch size {count} exceeds limit {self._max_batch_size}",
                code=ERROR_CODE_BATCH_SIZE,
            )

    def _filter_ids(self, ids: list[int], *, operation: str) -> list[int]:
        if not isinstance(ids, list):
            raise BulkOperationValidationError(
                f"{operation}: expected list of ids, got {type(ids).__name__}"
            )
        valid: list[int] = []
        errors: list[str] = []
        for idx, value in enumerate(ids):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                errors.append(f"id {idx} invalid")
                continue
            valid.append(int(value))
        if errors:
            preview = "; ".join(errors[:3])
            logger.warning(
                "%s: skipped %d invalid ids (%s)", operation, len(errors), preview
            )
        return list(dict.fromkeys(valid))

    def _validate_positive_int(
        self, value: object, field_name: str, operation: str, *, idx: int | None = None
    ) -> None:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
        ):
            if idx is None:
                raise BulkOperationValidationError(
                    f"{operation}: invalid {field_name}"
                )
            raise BulkOperationValidationError(
                f"{operation}: item {idx} invalid {field_name}"
            )

    def _validate_non_negative_int(
        self, value: object, field_name: str, operation: str, *, idx: int | None = None
    ) -> None:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            if idx is None:
                raise BulkOperationValidationError(
                    f"{operation}: invalid {field_name}"
                )
            raise BulkOperationValidationError(
                f"{operation}: item {idx} invalid {field_name}"
            )

__all__ = [
    "BulkOperationError",
    "BulkOperationRepositoryError",
    "BulkOperationService",
    "BulkOperationValidationError",
    "ERROR_CODE_BATCH_SIZE",
    "ERROR_CODE_REPOSITORY",
    "ERROR_CODE_VALIDATION",
]
