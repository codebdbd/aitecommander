from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.controllers.ui.dialogs.link_operations_controller import (
    LinkOperationsController,
)


def _build_controller() -> tuple[LinkOperationsController, SimpleNamespace]:
    undo_stack = SimpleNamespace(macro=lambda _text: nullcontext(), push=Mock())
    main_window = SimpleNamespace()
    controller = LinkOperationsController(db=Mock(), undo_stack=undo_stack, main_window=main_window)
    return controller, undo_stack


@patch("app.controllers.ui.dialogs.link_operations_controller.BatchDeleteLinksCmd")
@patch("app.controllers.ui.dialogs.link_operations_controller.DialogManager.ask_confirmation")
def test_batch_delete_requires_confirmation(
    ask_confirmation: Mock, batch_delete_cmd: Mock
) -> None:
    controller, undo_stack = _build_controller()
    ask_confirmation.return_value = False

    controller.delete_links_with_confirmation(
        [{"id": 1, "category_id": 10}, {"id": 2, "category_id": 10}]
    )

    ask_confirmation.assert_called_once()
    batch_delete_cmd.assert_not_called()
    undo_stack.push.assert_not_called()


@patch("app.controllers.ui.dialogs.link_operations_controller.BatchDeleteLinksCmd")
@patch("app.controllers.ui.dialogs.link_operations_controller.DialogManager.ask_confirmation")
def test_batch_delete_pushes_command_after_confirmation(
    ask_confirmation: Mock, batch_delete_cmd: Mock
) -> None:
    controller, undo_stack = _build_controller()
    ask_confirmation.return_value = True
    batch_delete_cmd.return_value = Mock()

    controller.delete_links_with_confirmation(
        [{"id": 1, "category_id": 10}, {"id": 2, "category_id": 10}]
    )

    ask_confirmation.assert_called_once()
    batch_delete_cmd.assert_called_once()
    undo_stack.push.assert_called_once_with(batch_delete_cmd.return_value)


@patch("app.controllers.ui.dialogs.link_operations_controller.DeleteLinkCmd")
@patch("app.controllers.ui.dialogs.link_operations_controller.DialogManager.ask_confirmation")
def test_single_delete_skips_confirmation(
    ask_confirmation: Mock, delete_link_cmd: Mock
) -> None:
    controller, undo_stack = _build_controller()
    delete_link_cmd.return_value = Mock()

    controller.delete_links_with_confirmation([{"id": 1, "category_id": 10}])

    ask_confirmation.assert_not_called()
    delete_link_cmd.assert_called_once()
    undo_stack.push.assert_called_once_with(delete_link_cmd.return_value)
