from __future__ import annotations

from unittest.mock import patch

from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QApplication

from app.controllers.ui.undo.commands_structure import SaveCategoryCmd
from app.views.models.structure_tree_model import StructureTreeModel


def test_save_category_cmd_invalidates_only_changed_icons():
    cmd = SaveCategoryCmd.__new__(SaveCategoryCmd)
    cmd.skip_reload = False
    cmd.old_data = {"id": 1, "name": "Fonts", "icon_path": "old.png"}

    with (
        patch("app.utils.ui.icon.cache_manager.invalidate_icon") as mock_inv,
        patch("app.utils.ui.icon.cache_manager.clear_icon_cache") as mock_clear,
    ):
        cmd._maybe_clear_icon_cache({"id": 1, "name": "Fonts", "icon_path": "new.png"})

        assert mock_clear.call_count == 0
        assert mock_inv.call_count == 2
        mock_inv.assert_any_call("old.png")
        mock_inv.assert_any_call("new.png")


def test_save_category_cmd_no_invalidation_when_icon_unchanged():
    cmd = SaveCategoryCmd.__new__(SaveCategoryCmd)
    cmd.skip_reload = False
    cmd.old_data = {"id": 1, "name": "Fonts", "icon_path": "same.png"}

    with (
        patch("app.utils.ui.icon.cache_manager.invalidate_icon") as mock_inv,
        patch("app.utils.ui.icon.cache_manager.clear_icon_cache") as mock_clear,
    ):
        cmd._maybe_clear_icon_cache({"id": 1, "name": "Fonts", "icon_path": "same.png"})

        assert mock_clear.call_count == 0
        assert mock_inv.call_count == 0


def test_update_item_preserves_existing_icon_when_icon_loading_pending():
    _ = QApplication.instance() or QApplication([])
    model = StructureTreeModel()
    try:
        model.insert_sections(0, [{"id": 1, "name": "Section"}])
        model.insert_categories(
            1,
            0,
            [{"id": 2, "name": "Category", "icon_path": "category.png"}],
        )
        node = model._category_by_id[2]
        existing_icon = QIcon()
        pm = QPixmap(16, 16)
        existing_icon.addPixmap(pm)
        node.icon = existing_icon

        with (
            patch.object(model, "_get_cached_icon", return_value=None),
            patch.object(model, "_load_icon_immediately_if_safe", return_value=None),
            patch.object(model, "_start_icon_loading") as mock_start,
        ):
            model.update_item(
                "category",
                2,
                {"id": 2, "name": "Category Renamed", "icon_path": "pending_async.png"},
            )

            assert node.icon == existing_icon
            assert not node.icon.isNull()
            mock_start.assert_called_once()
    finally:
        model.cleanup()
