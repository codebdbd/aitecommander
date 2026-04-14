"""Tests for BulkOperationService atomic batch behavior."""

import unittest
from unittest.mock import Mock

from app.services.batch_operation_base import (
    BulkOperationValidationError,
    ERROR_CODE_BATCH_SIZE,
)
from app.services.bulk_operation_service import BulkOperationService


class TestBulkOperationService(unittest.TestCase):
    """Validate that bulk service does not split operations into chunks."""

    def setUp(self) -> None:
        self.db = Mock()
        self.db.categories = Mock()
        self.db.sections = Mock()
        self.db.links = Mock()

    def test_move_categories_bulk_calls_repo_once_within_limit(self) -> None:
        self.db.categories.move_categories_to_section_bulk.return_value = [3, 1, 2]
        service = BulkOperationService(self.db, max_batch_size=10)

        moved = service.move_categories_bulk([3, 1, 2], target_section_id=9, base_row=4)

        self.assertEqual(moved, [3, 1, 2])
        self.db.categories.move_categories_to_section_bulk.assert_called_once_with(
            [3, 1, 2], 9, 4
        )

    def test_move_categories_bulk_rejects_payload_over_limit(self) -> None:
        service = BulkOperationService(self.db, max_batch_size=2)

        with self.assertRaises(BulkOperationValidationError) as ctx:
            service.move_categories_bulk([1, 2, 3], target_section_id=5, base_row=0)

        self.assertEqual(ctx.exception.code, ERROR_CODE_BATCH_SIZE)
        self.db.categories.move_categories_to_section_bulk.assert_not_called()

    def test_delete_sections_bulk_rejects_payload_over_limit(self) -> None:
        service = BulkOperationService(self.db, max_batch_size=2)

        with self.assertRaises(BulkOperationValidationError) as ctx:
            service.delete_sections_bulk([10, 11, 12])

        self.assertEqual(ctx.exception.code, ERROR_CODE_BATCH_SIZE)
        self.db.sections.delete_sections_bulk.assert_not_called()


if __name__ == "__main__":
    unittest.main()
