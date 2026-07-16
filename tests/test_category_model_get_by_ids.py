"""Direct unit tests for CategoryModel.get_categories_by_ids.

Mocks _execute_with_error_handling to avoid real database access.
"""
import unittest
from unittest.mock import MagicMock, patch

from app.models.entities.category_model import CategoryModel


def _make_row(row_id: int, name: str = "Cat", section_id: int = 10,
              position: int = 0, icon_path: str = "") -> dict:
    """Create a dict mimicking sqlite3.Row after row_to_dict."""
    return {"id": row_id, "name": name, "section_id": section_id,
            "position": position, "icon_path": icon_path}


class TestCategoryModelGetByIds(unittest.TestCase):
    """Direct tests for CategoryModel.get_categories_by_ids."""

    def setUp(self):
        self.model = CategoryModel.__new__(CategoryModel)
        self.model._db = MagicMock()

    # --- 1. Empty list: no DB call ---

    @patch.object(CategoryModel, "_execute_with_error_handling")
    def test_empty_list_no_db_call(self, mock_exec):
        result = self.model.get_categories_by_ids([])
        self.assertEqual(result, [])
        mock_exec.assert_not_called()

    @patch.object(CategoryModel, "_execute_with_error_handling")
    def test_none_like_empty(self, mock_exec):
        result = self.model.get_categories_by_ids([])
        self.assertEqual(result, [])
        mock_exec.assert_not_called()

    # --- 2. Order [2, 1] is preserved ---

    @patch("app.models.entities.category_model.row_to_dict")
    @patch.object(CategoryModel, "_ensure_row_list")
    @patch.object(CategoryModel, "_execute_with_error_handling")
    def test_order_preserved(self, mock_exec, mock_ensure, mock_r2d):
        row1 = MagicMock(); row1.__getitem__ = lambda s, k: {"id": 1}[k]
        row2 = MagicMock(); row2.__getitem__ = lambda s, k: {"id": 2}[k]
        mock_exec.return_value = [row2, row1]  # DB returns 2, 1
        mock_ensure.side_effect = lambda r: r

        def r2d(row):
            return {"id": row["id"], "name": f"Cat {row['id']}"}
        mock_r2d.side_effect = r2d

        result = self.model.get_categories_by_ids([2, 1])
        self.assertEqual([r["id"] for r in result], [2, 1])

    # --- 3. Exactly one _execute_with_error_handling call ---

    @patch("app.models.entities.category_model.row_to_dict")
    @patch.object(CategoryModel, "_ensure_row_list")
    @patch.object(CategoryModel, "_execute_with_error_handling")
    def test_single_db_call(self, mock_exec, mock_ensure, mock_r2d):
        row = MagicMock(); row.__getitem__ = lambda s, k: {"id": 1}[k]
        mock_exec.return_value = [row]
        mock_ensure.side_effect = lambda r: r
        mock_r2d.side_effect = lambda r: {"id": r["id"], "name": "Cat"}

        self.model.get_categories_by_ids([1, 2, 3])
        mock_exec.assert_called_once()

    # --- 4. [1, 1] → deduped SQL, two results ---

    @patch("app.models.entities.category_model.row_to_dict")
    @patch.object(CategoryModel, "_ensure_row_list")
    @patch.object(CategoryModel, "_execute_with_error_handling")
    def test_duplicate_ids(self, mock_exec, mock_ensure, mock_r2d):
        row = MagicMock(); row.__getitem__ = lambda s, k: {"id": 1}[k]
        mock_exec.return_value = [row]
        mock_ensure.side_effect = lambda r: r
        mock_r2d.side_effect = lambda r: {"id": r["id"], "name": "Cat"}

        result = self.model.get_categories_by_ids([1, 1])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], 1)
        self.assertEqual(result[1]["id"], 1)
        # SQL should have only one placeholder (deduplicated)
        call_args = mock_exec.call_args
        query = call_args[0][0]
        self.assertEqual(query.count("?"), 1)

    # --- 5. Missing ID skipped ---

    @patch("app.models.entities.category_model.row_to_dict")
    @patch.object(CategoryModel, "_ensure_row_list")
    @patch.object(CategoryModel, "_execute_with_error_handling")
    def test_missing_id_skipped(self, mock_exec, mock_ensure, mock_r2d):
        row = MagicMock(); row.__getitem__ = lambda s, k: {"id": 1}[k]
        mock_exec.return_value = [row]
        mock_ensure.side_effect = lambda r: r
        mock_r2d.side_effect = lambda r: {"id": r["id"], "name": "Cat"}

        result = self.model.get_categories_by_ids([1, 999])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 1)

    # --- 6. No results from DB → empty ---

    @patch.object(CategoryModel, "_ensure_row_list")
    @patch.object(CategoryModel, "_execute_with_error_handling")
    def test_no_db_results(self, mock_exec, mock_ensure):
        mock_exec.return_value = []
        mock_ensure.side_effect = lambda r: r

        result = self.model.get_categories_by_ids([1, 2])
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
