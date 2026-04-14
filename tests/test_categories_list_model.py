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


if __name__ == "__main__":
    unittest.main()
