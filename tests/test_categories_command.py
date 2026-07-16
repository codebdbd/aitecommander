
"""Tests for MoveCategoriesCommand and get_categories_by_ids"""
import unittest
from unittest.mock import Mock, MagicMock
from app.utils.ui.dnd.categories_command import MoveCategoriesCommand


class TestCategoriesCommand(unittest.TestCase):
    """Tests for MoveCategoriesCommand and get_categories_by_ids"""

    def test_input_order_preserved(self):
        """Test that the input order is preserved in old_states"""
        main = Mock()
        sb = Mock()
        # Return categories in reverse order
        sb.get_categories_by_ids.return_value = [
            {"id": 2, "name": "Cat 2", "section_id": 10, "position": 1, "icon_path": ""},
            {"id": 1, "name": "Cat 1", "section_id": 10, "position": 0, "icon_path": ""},
        ]
        sb.has_duplicate_category.return_value = False
        main.structure_business = sb

        cmd = MoveCategoriesCommand([2, 1], 20, 0, main)
        cmd._prepare_data()

        # Check that old_states are sorted by position, then id, not by input order
        self.assertEqual(len(cmd._old_states), 2)
        self.assertEqual(cmd._old_states[0]["id"], 1)
        self.assertEqual(cmd._old_states[1]["id"], 2)

    def test_empty_list(self):
        """Test with empty category_ids list"""
        main = Mock()
        sb = Mock()
        sb.get_categories_by_ids.return_value = []
        main.structure_business = sb

        cmd = MoveCategoriesCommand([], 20, 0, main)
        cmd._prepare_data()

        self.assertEqual(len(cmd._old_states), 0)
        self.assertEqual(len(cmd._new_states), 0)

    def test_duplicate_ids(self):
        """Test with duplicate category ids in input (original behavior)"""
        main = Mock()
        sb = Mock()
        sb.get_categories_by_ids.return_value = [
            {"id": 1, "name": "Cat 1", "section_id": 10, "position": 0, "icon_path": ""},
        ]
        sb.has_duplicate_category.return_value = False
        main.structure_business = sb

        cmd = MoveCategoriesCommand([1, 1], 20, 0, main)
        cmd._prepare_data()

        # Original behavior preserves duplicates in old_states before sorting
        self.assertEqual(len(cmd._old_states), 2)
        self.assertEqual(cmd._old_states[0]["id"], 1)
        self.assertEqual(cmd._old_states[1]["id"], 1)

    def test_missing_id(self):
        """Test with an id that doesn't exist"""
        main = Mock()
        sb = Mock()
        sb.get_categories_by_ids.return_value = [
            {"id": 1, "name": "Cat 1", "section_id": 10, "position": 0, "icon_path": ""},
        ]
        sb.has_duplicate_category.return_value = False
        main.structure_business = sb

        cmd = MoveCategoriesCommand([1, 999], 20, 0, main)
        cmd._prepare_data()

        self.assertEqual(len(cmd._old_states), 1)
        self.assertEqual(cmd._old_states[0]["id"], 1)

    def test_single_query(self):
        """Test that only one get_categories_by_ids is called, not get_category_data"""
        main = Mock()
        sb = Mock()
        sb.get_categories_by_ids.return_value = [
            {"id": 1, "name": "Cat 1", "section_id": 10, "position": 0, "icon_path": ""},
            {"id": 2, "name": "Cat 2", "section_id": 10, "position": 1, "icon_path": ""},
        ]
        sb.has_duplicate_category.return_value = False
        main.structure_business = sb

        cmd = MoveCategoriesCommand([1, 2], 20, 0, main)
        cmd._prepare_data()

        sb.get_categories_by_ids.assert_called_once_with([1, 2])
        sb.get_category_data.assert_not_called()


if __name__ == "__main__":
    unittest.main()
