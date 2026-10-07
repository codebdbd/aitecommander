"""Runtime-path tests for DnD move commands used by MoveOperationsHandler."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.utils.ui.dnd.categories_command import (
    MergeCategoriesCommand,
    MoveCategoriesCommand,
)
from app.utils.ui.dnd.category_command import MoveCategoryCommand
from app.utils.ui.dnd.commands import (
    MoveCategoriesCommand as LegacyMoveCategoriesCommand,
)
from app.utils.ui.dnd.commands import MoveCategoryCommand as LegacyMoveCategoryCommand
from app.utils.ui.dnd.commands import MoveLinksCommand as LegacyMoveLinksCommand
from app.utils.ui.dnd.links_command import MoveLinksCommand


class TestDndMoveCommands(unittest.TestCase):
    def test_legacy_commands_module_reexports_current_classes(self) -> None:
        self.assertIs(LegacyMoveLinksCommand, MoveLinksCommand)
        self.assertIs(LegacyMoveCategoryCommand, MoveCategoryCommand)
        self.assertIs(LegacyMoveCategoriesCommand, MoveCategoriesCommand)

    def _build_main_with_structure(self) -> SimpleNamespace:
        tree_model = Mock()
        tree = Mock()
        tree.model.return_value = tree_model
        selection_handler = Mock()
        structure = SimpleNamespace(tree=tree, selection_handler=selection_handler)
        return SimpleNamespace(structure=structure)

    def test_move_category_command_redo_undo(self) -> None:
        main = self._build_main_with_structure()
        sb = Mock()
        sb.get_category_data.return_value = {
            "id": 11,
            "name": "Cat",
            "section_id": 2,
            "position": 0,
            "icon_path": "",
        }
        sb.get_categories_by_ids.return_value = [sb.get_category_data.return_value]
        sb.has_duplicate_category.return_value = False
        sb.move_categories_batch.return_value = [11]
        main.structure_business = sb

        cmd = MoveCategoryCommand(11, 3, main)
        cmd.redo()
        cmd.undo()

        self.assertGreaterEqual(sb.move_categories_batch.call_count, 2)

    def test_reorder_links_command_redo_undo(self) -> None:
        from app.utils.ui.dnd.links_command import ReorderLinksCommand

        main = Mock()
        links_business = Mock()
        links_business.get_links.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
        main.links_business = links_business
        main.links_table_controller = Mock()

        cmd = ReorderLinksCommand(category_id=10, new_order=[3, 1, 2], main_window=main)
        self.assertEqual(cmd.old_order, [1, 2, 3])
        self.assertEqual(cmd.new_order, [3, 1, 2])

        # Redo 1 (first redo from DnD drop): writes new_order without reload
        cmd.redo()
        links_business.update_link_order.assert_called_with([3, 1, 2])
        main.links_table_controller.reload.assert_not_called()

        # Undo: writes old_order and reloads table
        cmd.undo()
        links_business.update_link_order.assert_called_with([1, 2, 3])
        main.links_table_controller.reload.assert_called_with(10)

        # Redo 2 (subsequent redo): writes new_order and reloads table
        main.links_table_controller.reload.reset_mock()
        cmd.redo()
        links_business.update_link_order.assert_called_with([3, 1, 2])
        main.links_table_controller.reload.assert_called_with(10)

    def test_move_categories_command_redo_calls_batch_move(self) -> None:
        main = self._build_main_with_structure()
        event_service = Mock()
        sb = Mock()
        sb.event_service = event_service
        sb.get_category_data.side_effect = [
            {"id": 1, "name": "A", "section_id": 10, "position": 0, "icon_path": ""},
            {"id": 2, "name": "B", "section_id": 10, "position": 1, "icon_path": ""},
        ]
        sb.get_categories_by_ids.return_value = [
            {"id": 1, "name": "A", "section_id": 10, "position": 0, "icon_path": ""},
            {"id": 2, "name": "B", "section_id": 10, "position": 1, "icon_path": ""},
        ]
        sb.has_duplicate_category.return_value = False
        sb.move_categories_batch.return_value = [1, 2]
        main.structure_business = sb

        cmd = MoveCategoriesCommand([1, 2], 20, 0, main)
        cmd.redo()

        sb.begin_batch.assert_called_once()
        sb.end_batch.assert_called_once()
        sb.move_categories_batch.assert_called()

    def test_move_links_command_redo_calls_batch_update(self) -> None:
        main = self._build_main_with_structure()
        links_repo = Mock()
        links_repo.get_link_by_id.return_value = {
            "id": 7,
            "name": "N",
            "url": "https://example.com",
            "args": "",
            "category_id": 1,
            "position": 0,
        }
        links_repo.batch_update.return_value = True
        links_business = Mock()
        links_business.links = links_repo
        links_business.get_next_position.return_value = 0
        links_business.get_links.return_value = []
        main.links_business = links_business
        main.structure_business = Mock()
        main.links_actions = Mock()

        cmd = MoveLinksCommand([7], 2, main)
        cmd.redo()

        links_repo.batch_update.assert_called()

    def test_move_links_command_refresh_ui_undo_focuses_old_category(self) -> None:
        main = self._build_main_with_structure()
        links_repo = Mock()
        links_business = Mock()
        links_business.links = links_repo
        main.links_business = links_business
        main.links_actions = Mock()

        structure_business = Mock()
        main.structure_business = structure_business

        tree_model = Mock()
        tree_model.index_for.return_value = Mock(isValid=Mock(return_value=False))
        main.structure.tree.model.return_value = tree_model

        cmd = MoveLinksCommand([7], 2, main)
        cmd._old_states = [{"id": 7, "category_id": 11}]
        cmd.old_category_id = 11
        cmd._old_category_ids = {11}
        cmd._last_operation = "undo"
        cmd.link_ids = [7]

        cmd._refresh_ui()

        structure_business.select_category.assert_called_with(11)

    def test_move_categories_command_refresh_ui_undo_uses_old_target(self) -> None:
        main = self._build_main_with_structure()
        main.structure_business = Mock()

        cmd = MoveCategoriesCommand([1], 20, 0, main)
        cmd._new_states = [{"id": 1, "section_id": 20}]
        cmd._old_states = [{"id": 1, "section_id": 10}]
        cmd._last_operation = "undo"

        cmd._maybe_schedule_tree_focus = Mock()

        cmd._refresh_ui()

        cmd._maybe_schedule_tree_focus.assert_called_once()
        _tree, focus_id, section_id = cmd._maybe_schedule_tree_focus.call_args.args
        self.assertEqual(focus_id, 1)
        self.assertEqual(section_id, 10)

    def test_merge_categories_command_attributes_and_refresh_ui_redo(self) -> None:
        main = self._build_main_with_structure()
        sb = Mock()
        main.structure_business = sb
        facade = Mock()
        main._facade = facade

        cmd = MergeCategoriesCommand(10, 20, main)
        cmd._source_section_id = 100
        cmd._target_section_id = 200
        cmd._last_operation = "redo"

        # Verify attributes exist and no AttributeError is raised
        self.assertEqual(cmd._source_category_id, 10)
        self.assertEqual(cmd._target_category_id, 20)
        self.assertEqual(cmd.source_id, 10)
        self.assertEqual(cmd.target_id, 20)

        cmd._refresh_ui()

        sb._invalidate_categories_cache.assert_any_call(100)
        sb._invalidate_categories_cache.assert_any_call(200)
        facade.refresh_structure_after_import.assert_called_once_with(sb, 200)
        main.structure.selection_handler._restore_category_selection.assert_called_once_with(
            20, target_section_id=200
        )

    def test_merge_categories_command_attributes_and_refresh_ui_undo(self) -> None:
        main = self._build_main_with_structure()
        sb = Mock()
        main.structure_business = sb
        facade = Mock()
        main._facade = facade

        cmd = MergeCategoriesCommand(10, 20, main)
        cmd._source_section_id = 100
        cmd._target_section_id = 200
        cmd._last_operation = "undo"

        cmd._refresh_ui()

        facade.refresh_structure_after_import.assert_called_once_with(sb, 100)
        main.structure.selection_handler._restore_category_selection.assert_called_once_with(
            10, target_section_id=100
        )


if __name__ == "__main__":
    unittest.main()
