"""Integration-style tests for MoveOperationsHandler command wiring."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.utils.ui.dnd.categories_command import MoveCategoriesCommand
from app.utils.ui.dnd.category_command import MoveCategoryCommand
from app.utils.ui.dnd.links_command import MoveLinksCommand
from app.views.widgets.tree_components.move_operations_handler import (
    MoveOperationsHandler,
)


class _TreeWidgetStub:
    def __init__(self, main_window):
        self._main_window = main_window

    def window(self):
        return self._main_window


class _Handler(MoveOperationsHandler):
    def tr(self, text: str) -> str:
        return text


class TestMoveOperationsHandler(unittest.TestCase):
    def _build_handler(self):
        main_window = SimpleNamespace(undo_stack=Mock())
        tree_widget = _TreeWidgetStub(main_window)
        return _Handler(tree_widget), main_window

    def test_execute_move_category_command_pushes_correct_command(self) -> None:
        handler, main_window = self._build_handler()

        handler.execute_move_category_command(7, 11)

        main_window.undo_stack.push.assert_called_once()
        pushed = main_window.undo_stack.push.call_args.args[0]
        self.assertIsInstance(pushed, MoveCategoryCommand)

    def test_execute_move_links_command_pushes_correct_command(self) -> None:
        handler, main_window = self._build_handler()

        handler.execute_move_links_command([1, 2], 9)

        main_window.undo_stack.push.assert_called_once()
        pushed = main_window.undo_stack.push.call_args.args[0]
        self.assertIsInstance(pushed, MoveLinksCommand)

    def test_execute_move_categories_command_pushes_correct_command(self) -> None:
        handler, main_window = self._build_handler()

        result = handler.execute_move_categories_command([3, 4], 15, 2)

        self.assertTrue(result)
        main_window.undo_stack.push.assert_called_once()
        pushed = main_window.undo_stack.push.call_args.args[0]
        self.assertIsInstance(pushed, MoveCategoriesCommand)

    def test_emit_section_selected_handles_suppression_tuple(self) -> None:
        handler, main_window = self._build_handler()
        main_window.structure_business = SimpleNamespace(section_selected=Mock())
        main_window.structure = SimpleNamespace()

        handler._suppress_signals = Mock(return_value=(Mock(), Mock(), True, True))
        handler._restore_signals = Mock()

        handler._emit_section_selected(main_window, 7)

        main_window.structure_business.section_selected.emit.assert_called_once_with(7)
        handler._restore_signals.assert_called_once()


if __name__ == "__main__":
    unittest.main()
