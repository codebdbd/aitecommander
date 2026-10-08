from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QMenu, QToolBar, QToolButton

from app.controllers.ui.links.links_actions import LinksActions
from app.views.main_components.ui.topbar.toolbar_adapters import LinksToolbarAdapter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_links_toolbar_adapter_context_menu_policy(qapp: QApplication) -> None:
    toolbar = QToolBar()
    adapter = LinksToolbarAdapter(
        toolbar,
        insert_before=None,
        button_object_name="favoriteButton",
        group_name="fav",
    )
    link_data = {"id": 10, "name": "Docs", "url": "https://docs.python.org", "type": "url"}
    adapter.set_data([link_data])

    assert len(adapter._link_actions) == 1
    action = adapter._link_actions[0]
    btn = toolbar.widgetForAction(action)
    assert isinstance(btn, QToolButton)
    assert btn.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_links_toolbar_adapter_context_menu_actions(qapp: QApplication) -> None:
    toolbar = QToolBar()
    adapter = LinksToolbarAdapter(
        toolbar,
        insert_before=None,
        button_object_name="favoriteButton",
        group_name="fav",
    )
    link_data = {"id": 42, "name": "GitHub", "url": "https://github.com", "type": "url"}
    adapter.set_data([link_data])

    captured_emits = []
    adapter.actionRequested.connect(lambda payload: captured_emits.append(payload))

    # Test _show_context_menu without blocking GUI event loop via mocking QMenu.exec
    with patch("PyQt6.QtWidgets.QMenu.exec") as mock_exec:
        adapter._show_context_menu(QPoint(100, 100), link_data)
        assert mock_exec.called

    # Directly verify actions created by _show_context_menu
    menu_actions = []
    with patch("PyQt6.QtWidgets.QMenu.addAction", side_effect=lambda act: menu_actions.append(act)):
        with patch("PyQt6.QtWidgets.QMenu.exec"):
            adapter._show_context_menu(QPoint(0, 0), link_data)

    assert len(menu_actions) == 2
    edit_act, del_act = menu_actions

    # Trigger Edit
    edit_act.trigger()
    assert len(captured_emits) == 1
    assert captured_emits[0]["type"] == "edit_link"
    assert captured_emits[0]["link"]["id"] == 42

    # Trigger Remove from Favorites
    del_act.trigger()
    assert len(captured_emits) == 2
    assert captured_emits[1]["type"] == "remove_favorite"
    assert captured_emits[1]["link"]["id"] == 42


def test_links_toolbar_adapter_context_menu_real_signal_flow(qapp: QApplication) -> None:
    toolbar = QToolBar()
    adapter = LinksToolbarAdapter(
        toolbar,
        insert_before=None,
        button_object_name="favoriteButton",
        group_name="fav",
    )
    link_data = {"id": 105, "name": "Python Docs", "url": "https://python.org", "type": "url"}
    adapter.set_data([link_data])

    captured = []
    adapter.actionRequested.connect(lambda p: captured.append(p))

    btn = toolbar.widgetForAction(adapter._link_actions[0])
    assert isinstance(btn, QToolButton)

    # Intercept QMenu.exec to inspect the active menu created via real Qt signal dispatch
    exec_menus: list[QMenu] = []
    with patch.object(QMenu, "exec", autospec=True, side_effect=lambda menu, *args, **kwargs: exec_menus.append(menu)):
        btn.customContextMenuRequested.emit(QPoint(10, 10))

    assert len(exec_menus) == 1
    active_menu = exec_menus[0]
    actions = active_menu.actions()
    assert len(actions) == 2

    # Trigger edit action
    actions[0].trigger()
    assert len(captured) == 1 and captured[0]["type"] == "edit_link"

    # Trigger remove action
    actions[1].trigger()
    assert len(captured) == 2 and captured[1]["type"] == "remove_favorite"


def test_links_actions_on_action_requested_edit_and_remove() -> None:
    main_window = MagicMock()
    links = MagicMock()
    link_ops = MagicMock()
    links_actions = LinksActions(main_window, links, link_ops)
    links_actions.show_link_dialog = MagicMock(return_value=True)
    links_actions.toggle_link_favorite = MagicMock()

    test_link = {"id": 99, "name": "Test Link"}

    # Test edit_link
    links_actions.on_action_requested({"type": "edit_link", "link": test_link})
    links_actions.show_link_dialog.assert_called_once_with(link=test_link)
    main_window.update_statusbar.assert_called_once()

    # Test remove_favorite
    links_actions.on_action_requested({"type": "remove_favorite", "link": test_link})
    links_actions.toggle_link_favorite.assert_called_once_with(link=test_link)
