from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.controllers.ui.state.ui_state_manager import UIStateManager


def _build_main() -> SimpleNamespace:
    stack = Mock()
    stack.currentIndex.return_value = 0
    stack.count.return_value = 2
    return SimpleNamespace(
        stack=stack,
        current_category_id=None,
        links_table_controller=SimpleNamespace(reload=Mock()),
        tiles=SimpleNamespace(set_categories=Mock()),
    )


def test_load_category_switches_to_table_after_data_is_applied() -> None:
    main = _build_main()
    manager = UIStateManager(main)

    with (
        patch(
            "app.controllers.ui.state.ui_state_manager.get_table_stack_index",
            return_value=1,
        ),
        patch(
            "app.controllers.ui.state.ui_state_manager.get_tiles_stack_index",
            return_value=0,
        ),
    ):
        assert manager.load_category(42)
        main.links_table_controller.reload.assert_called_once_with(42)
        main.stack.setCurrentIndex.assert_not_called()

        manager.on_category_loaded(42)

    main.stack.setCurrentIndex.assert_called_once_with(1)


def test_switching_to_tiles_cancels_pending_table_switch() -> None:
    main = _build_main()
    manager = UIStateManager(main)

    with (
        patch(
            "app.controllers.ui.state.ui_state_manager.get_table_stack_index",
            return_value=1,
        ),
        patch(
            "app.controllers.ui.state.ui_state_manager.get_tiles_stack_index",
            return_value=0,
        ),
    ):
        assert manager.load_category(42)
        manager.switch_to_category_tiles([{"id": 7}], force_show_when_empty=True)
        manager.on_category_loaded(42)

    main.stack.setCurrentIndex.assert_not_called()
