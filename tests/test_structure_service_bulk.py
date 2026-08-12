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
    def test_update_section_invalidates_old_and_new_spheres_when_moved(self) -> None:
        db = _FakeDb()
        db.sections.get_section_by_id.side_effect = [
            {"id": 9, "sphere_id": 1, "name": "Old"},
            {"id": 9, "sphere_id": 2, "name": "Moved"},
        ]
        service = StructureService(db)
        service._model = Mock()
        service._model.update_section.return_value = True

        result = service.update_section(9, {"id": 9, "name": "Moved", "sphere_id": 2})

        self.assertTrue(result.is_success())
        self.assertEqual(
            [(r.scope, r.identifier) for r in result.invalidate_regions],
            [("sections", 1), ("sections", 2), ("structure", None)],
        )

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
