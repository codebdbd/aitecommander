from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.controllers.ui.structure.tree_update_service import TreeUpdateService


class TestTreeUpdateServiceSortPolicy(unittest.TestCase):
    def _build_service(self):
        manager = SimpleNamespace(controller=SimpleNamespace(business=SimpleNamespace()))
        tree = Mock()
        model = Mock()
        return TreeUpdateService(manager, tree, model), manager, model

    @patch("app.controllers.ui.structure.tree_update_service.is_tree_alphabetical_sort_enabled")
    def test_should_use_alphabetical_insert_enabled_without_suppress(self, cfg_mock: Mock) -> None:
        cfg_mock.return_value = True
        svc, manager, _model = self._build_service()
        manager.controller.business._suppress_tree_sort_once = False
        self.assertTrue(svc._should_use_alphabetical_insert())

    @patch("app.controllers.ui.structure.tree_update_service.is_tree_alphabetical_sort_enabled")
    def test_should_use_alphabetical_insert_disabled_when_suppressed(self, cfg_mock: Mock) -> None:
        cfg_mock.return_value = True
        svc, manager, _model = self._build_service()
        manager.controller.business._suppress_tree_sort_once = True
        self.assertFalse(svc._should_use_alphabetical_insert())

    @patch("app.controllers.ui.structure.tree_update_service.is_tree_alphabetical_sort_enabled")
    def test_insert_section_prefers_sorted_row_when_alpha_enabled(self, cfg_mock: Mock) -> None:
        cfg_mock.return_value = True
        svc, manager, model = self._build_service()
        manager.controller.business._suppress_tree_sort_once = False
        svc._sorted_insert_row = Mock(return_value=2)  # type: ignore[method-assign]
        svc._positioned_insert_row = Mock(return_value=1)  # type: ignore[method-assign]
        svc._build_payload = Mock(return_value={"id": 5, "name": "Beta"})  # type: ignore[method-assign]

        svc._insert_section({"id": 5, "name": "Beta", "position": 99})

        svc._sorted_insert_row.assert_called_once()
        svc._positioned_insert_row.assert_not_called()
        model.insert_sections.assert_called_once_with(2, [{"id": 5, "name": "Beta"}])

    @patch("app.controllers.ui.structure.tree_update_service.is_tree_alphabetical_sort_enabled")
    def test_insert_section_prefers_position_when_alpha_suppressed(self, cfg_mock: Mock) -> None:
        cfg_mock.return_value = True
        svc, manager, model = self._build_service()
        manager.controller.business._suppress_tree_sort_once = True
        svc._sorted_insert_row = Mock(return_value=2)  # type: ignore[method-assign]
        svc._positioned_insert_row = Mock(return_value=1)  # type: ignore[method-assign]
        svc._build_payload = Mock(return_value={"id": 5, "name": "Beta"})  # type: ignore[method-assign]

        svc._insert_section({"id": 5, "name": "Beta", "position": 99})

        svc._positioned_insert_row.assert_called_once()
        svc._sorted_insert_row.assert_not_called()
        model.insert_sections.assert_called_once_with(1, [{"id": 5, "name": "Beta"}])


class TestTreeUpdateServiceBatchDeleteRefresh(unittest.TestCase):
    def _build_service(self):
        business = SimpleNamespace(get_categories=Mock())
        manager = SimpleNamespace(controller=SimpleNamespace(business=business))
        tree = Mock()
        model = Mock()
        return TreeUpdateService(manager, tree, model), business, model

    def test_batch_delete_categories_replaces_touched_sections_from_business(self) -> None:
        svc, business, model = self._build_service()
        model.section_ids_for_categories.return_value = [487]
        business.get_categories.return_value = [{"id": 1, "section_id": 487, "name": "Rest"}]
        svc.replace_section_categories = Mock()  # type: ignore[method-assign]

        svc.handle_items_batch_deleted("category", [1001, 1002])

        business.get_categories.assert_called_once_with(487)
        svc.replace_section_categories.assert_called_once_with(
            487, [{"id": 1, "section_id": 487, "name": "Rest"}]
        )
        model.remove_categories.assert_not_called()

    def test_batch_delete_categories_falls_back_to_remove_when_section_lookup_missing(self) -> None:
        svc, business, model = self._build_service()
        model.section_ids_for_categories.return_value = []

        svc.handle_items_batch_deleted("category", [1001, 1002])

        business.get_categories.assert_not_called()
        model.remove_categories.assert_called_once_with([1001, 1002])


class TestTreeUpdateServiceCategoryMoveOnEdit(unittest.TestCase):
    def _build_service(self):
        business = SimpleNamespace(get_categories=Mock())
        selection_handler = Mock()
        manager = SimpleNamespace(
            controller=SimpleNamespace(
                business=business,
                selection_handler=selection_handler,
            ),
            refresh_section_tiles=Mock(),
        )
        tree = Mock()
        model = Mock()
        return TreeUpdateService(manager, tree, model), business, manager, model

    @patch("app.controllers.ui.structure.tree_update_service.get_focus_manager")
    @patch("app.controllers.ui.structure.tree_update_service.schedule_selection_restore")
    def test_category_update_with_new_section_replaces_source_and_target_sections(
        self,
        schedule_mock: Mock,
        focus_manager_mock: Mock,
    ) -> None:
        svc, business, manager, model = self._build_service()
        model.section_ids_for_categories.return_value = [10]
        business.get_categories.side_effect = [
            [{"id": 1, "section_id": 10, "name": "Old"}],
            [{"id": 42, "section_id": 20, "name": "Moved"}],
        ]
        svc.replace_section_categories = Mock()  # type: ignore[method-assign]

        svc.handle_item_updated(
            "category",
            42,
            {"id": 42, "section_id": 20, "name": "Moved"},
        )

        model.update_item.assert_not_called()
        self.assertEqual(business.get_categories.call_args_list[0].args, (10,))
        self.assertEqual(business.get_categories.call_args_list[1].args, (20,))
        svc.replace_section_categories.assert_any_call(
            10, [{"id": 1, "section_id": 10, "name": "Old"}]
        )
        svc.replace_section_categories.assert_any_call(
            20, [{"id": 42, "section_id": 20, "name": "Moved"}]
        )
        manager.refresh_section_tiles.assert_any_call(10)
        manager.refresh_section_tiles.assert_any_call(20)
        schedule_mock.assert_called_once()
        focus_manager_mock.return_value.set_focus.assert_called_once()

    @patch("app.controllers.ui.structure.tree_update_service.get_focus_manager")
    @patch("app.controllers.ui.structure.tree_update_service.schedule_selection_restore")
    def test_category_update_in_same_section_keeps_in_place_update(
        self,
        _schedule_mock: Mock,
        _focus_manager_mock: Mock,
    ) -> None:
        svc, business, _manager, model = self._build_service()
        model.section_ids_for_categories.return_value = [20]

        svc.handle_item_updated(
            "category",
            42,
            {"id": 42, "section_id": 20, "name": "Renamed"},
        )

        business.get_categories.assert_not_called()
        model.update_item.assert_called_once_with(
            "category", 42, {"id": 42, "section_id": 20, "name": "Renamed"}
        )


class TestTreeUpdateServiceDeletePostUpdates(unittest.TestCase):
    def _build_service(self):
        manager = SimpleNamespace(
            controller=SimpleNamespace(business=SimpleNamespace()),
            refresh_tiles_for_current_selection=Mock(),
            clear_tiles=Mock(),
        )
        tree = Mock()
        model = Mock()
        tree.model.return_value = model
        return TreeUpdateService(manager, tree, model), manager, model

    def test_section_delete_does_not_refresh_tiles_when_tree_not_empty(self) -> None:
        svc, manager, model = self._build_service()
        model.rowCount.return_value = 3

        svc._post_delete_updates("section", 10)

        manager.clear_tiles.assert_not_called()
        manager.refresh_tiles_for_current_selection.assert_not_called()

    def test_section_delete_clears_tiles_when_tree_empty(self) -> None:
        svc, manager, model = self._build_service()
        model.rowCount.return_value = 0

        svc._post_delete_updates("section", 10)

        manager.clear_tiles.assert_called_once()
        manager.refresh_tiles_for_current_selection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
