"""Tests for StructureService bulk-operation error handling contract."""

import unittest
from contextlib import nullcontext
from unittest.mock import Mock

from app.services.batch_operation_base import BulkOperationValidationError
from app.services.bulk_operation_service import BulkOperationService
from app.services.structure_service import StructureService


class _FakeDb:
    def __init__(self) -> None:
        self.spheres = Mock()
        self.sections = Mock()
        self.categories = Mock()
        self.links = Mock()

    def transaction(self):
        return nullcontext()


class TestStructureServiceBulk(unittest.TestCase):
    def test_delete_sections_bulk_returns_failure_result_on_batch_limit(self) -> None:
        db = _FakeDb()
        db.sections.get_section_by_id.return_value = {"id": 1, "sphere_id": 10}
        service = StructureService(db)
        service._bulk = BulkOperationService(db, max_batch_size=1)

        result = service.delete_sections_bulk([1, 2])

        self.assertTrue(result.is_failure())
        self.assertEqual(result.value, 0)
        self.assertIsInstance(result.error, BulkOperationValidationError)

    def test_move_categories_bulk_returns_failure_result_on_batch_limit(self) -> None:
        db = _FakeDb()
        db.categories.get_category_by_id.side_effect = [
            {"id": 1, "section_id": 100},
            {"id": 2, "section_id": 100},
        ]
        service = StructureService(db)
        service._bulk = BulkOperationService(db, max_batch_size=1)

        result = service.move_categories_to_section_bulk([1, 2], target_section_id=200)

        self.assertTrue(result.is_failure())
        self.assertEqual(result.value, [])
        self.assertIsInstance(result.error, BulkOperationValidationError)


if __name__ == "__main__":
    unittest.main()
