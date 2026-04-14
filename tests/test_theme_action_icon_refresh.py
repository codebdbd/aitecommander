from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.controllers.ui.action_controller import ActionController
from app.controllers.ui.theme_controller import ThemeController


def test_action_controller_refresh_action_icons_updates_global_and_undo_redo() -> None:
    settings = SimpleNamespace(get_theme=Mock(return_value="dark"))
    main_window = SimpleNamespace(
        settings=settings,
        shown=SimpleNamespace(connect=Mock()),
        actions=lambda: [],
        addAction=Mock(),
        undo_action=Mock(),
        redo_action=Mock(),
    )
    controller = ActionController(main_window)
    controller._global_actions_ready = True
    deferred_action = Mock()
    controller._deferred_action_icons = [(deferred_action, "cut")]

    with patch(
        "app.controllers.ui.action_controller.icon_cache.get_icon",
        side_effect=lambda name, theme, source=None: f"{theme}:{name}",
    ):
        controller.refresh_action_icons()

    deferred_action.setIcon.assert_called_once_with("dark:cut")
    main_window.undo_action.setIcon.assert_called_once_with("dark:undo")
    main_window.redo_action.setIcon.assert_called_once_with("dark:redo")


def test_theme_controller_perform_ui_updates_refreshes_action_icons_first() -> None:
    theme_controller = ThemeController(settings=SimpleNamespace())
    action_controller = SimpleNamespace(refresh_action_icons=Mock())
    menu_controller = SimpleNamespace(rebuild_after_theme_change=Mock())
    structure = SimpleNamespace(reload_icons=Mock())
    main_window = SimpleNamespace(
        action_controller=action_controller,
        menu_controller=menu_controller,
        structure=structure,
        _topbar_refresh_requested=False,
    )
    top_panels_controller = SimpleNamespace(request_refresh=Mock())
    theme_controller.top_panels_controller = top_panels_controller

    theme_controller._perform_ui_updates(main_window)

    action_controller.refresh_action_icons.assert_called_once_with()
    menu_controller.rebuild_after_theme_change.assert_called_once_with()
    structure.reload_icons.assert_called_once_with()
    top_panels_controller.request_refresh.assert_called_once_with(150)
