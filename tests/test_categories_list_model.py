from __future__ import annotations

import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from app.views.models.categories_list_model import CategoriesListModel


class TestCategoriesListModelSyncPrefetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_sync_prefetch_loads_first_rows_immediately(self) -> None:
        categories = [
            {"id": 1, "name": "A", "icon_path": "a.png"},
            {"id": 2, "name": "B", "icon_path": "b.png"},
            {"id": 3, "name": "C", "icon_path": "c.png"},
        ]
        loaded_paths: list[str] = []

        def _fake_get_cached(path: str) -> QIcon:
            loaded_paths.append(path)
            return QIcon()

        with (
            patch(
                "app.views.models.categories_list_model.icon_loading_service.resolve_path",
                side_effect=lambda path, category=True: path,
            ),
            patch(
                "app.views.models.categories_list_model.icon_loading_service.get_path_icon",
                side_effect=lambda path, category=True: _fake_get_cached(path),
            ),
        ):
            model = CategoriesListModel()
            model._sync_prefetch_cap = 2
            model._icon_prefetch = 24
            model._icon_batch_size = 32
            model.set_categories(categories)

        self.assertEqual(["a.png", "b.png"], loaded_paths)
        self.assertIsInstance(model._items[0]["_icon"], QIcon)
        self.assertIsInstance(model._items[1]["_icon"], QIcon)
        self.assertFalse(model._items[0]["_icon_pending"])
        self.assertFalse(model._items[1]["_icon_pending"])
        self.assertTrue(model._items[2]["_icon_pending"])

    def test_set_categories_detects_icon_path_change(self) -> None:
        model = CategoriesListModel()
        model.set_categories([{"id": 1, "name": "A", "icon_path": "old.png"}])
        self.assertEqual(model._items[0]["icon_path"], "old.png")

        # Calling with different icon_path should not be skipped by signature check
        model.set_categories([{"id": 1, "name": "A", "icon_path": "new.png"}])
        self.assertEqual(model._items[0]["icon_path"], "new.png")

    def test_set_categories_skips_when_signature_identical(self) -> None:
        model = CategoriesListModel()
        model.set_categories([{"id": 1, "name": "A", "icon_path": "same.png"}])
        items_before = model._items

        # Calling with identical (id, name, icon_path) should take fast-path
        model.set_categories([{"id": 1, "name": "A", "icon_path": "same.png"}])
        self.assertIs(model._items, items_before)

    def test_update_category_in_place_and_emits_datachanged(self) -> None:
        model = CategoriesListModel([
            {"id": 1, "name": "A", "icon_path": "a.png"},
            {"id": 2, "name": "B", "icon_path": "b.png"},
        ])

        changed_indices: list[tuple[int, int]] = []
        model.dataChanged.connect(
            lambda top, bottom, roles: changed_indices.append((top.row(), bottom.row()))
        )

        with (
            patch(
                "app.views.models.categories_list_model.icon_loading_service.get_path_icon",
                return_value=QIcon(),
            ),
        ):
            res = model.update_category({
                "id": 2,
                "name": "B Renamed",
                "icon_path": "b_updated.png",
            })

        self.assertTrue(res)
        self.assertEqual(model._items[1]["name"], "B Renamed")
        self.assertEqual(model._items[1]["icon_path"], "b_updated.png")
        self.assertEqual(changed_indices, [(1, 1)])

    def test_update_category_returns_false_for_missing_or_invalid_id(self) -> None:
        model = CategoriesListModel([{"id": 1, "name": "A", "icon_path": "a.png"}])
        self.assertFalse(model.update_category({"id": 999, "name": "NonExistent"}))
        self.assertFalse(model.update_category({"name": "NoId"}))
        self.assertFalse(model.update_category({"id": "invalid", "name": "BadId"}))

    def test_update_category_no_change_returns_false(self) -> None:
        model = CategoriesListModel([{"id": 1, "name": "A", "icon_path": "a.png"}])
        # Ensure _icon is populated so it doesn't trigger "is None" check
        model._items[0]["_icon"] = QIcon()
        res = model.update_category({"id": 1, "name": "A", "icon_path": "a.png"})
        self.assertFalse(res)

    def test_category_tiles_widget_update_category(self) -> None:
        from app.views.widgets.tiles.widget import CategoryTiles

        tiles = CategoryTiles()
        tiles.set_categories([{"id": 1, "name": "Cat 1", "icon_path": "old.png"}])

        with patch(
            "app.views.models.categories_list_model.icon_loading_service.get_path_icon",
            return_value=QIcon(),
        ):
            res = tiles.update_category({"id": 1, "name": "Cat 1 Updated", "icon_path": "new.png"})

        self.assertTrue(res)
        self.assertEqual(tiles._model._items[0]["name"], "Cat 1 Updated")
        self.assertEqual(tiles._model._items[0]["icon_path"], "new.png")


if __name__ == "__main__":
    unittest.main()
