from __future__ import annotations

import pytest

from app.controllers.ui.action_controller import ActionController


class MWBase:
    def __init__(self):
        # минимально необходимые заглушки для методов, которые не зависят от Qt
        self.structure = type("S", (), {"edit_selected_item": lambda self: None, "delete_selected_item": lambda self: None})()
        self.links_actions = type(
            "LA",
            (),
            {
                "get_selected_rows": lambda self: [],
                "get_selected_links": lambda self: [],
                "edit_selected_link": lambda self: False,
                "delete_links_with_confirmation": lambda self, _links: None,
            },
        )()
        self.table = type("T", (), {"hasFocus": lambda self: False})()
        self.tree = type(
            "Tree",
            (),
            {
                "currentIndex": lambda self: type("Idx", (), {"isValid": lambda self: False})(),
                "hasFocus": lambda self: False,
            },
        )()
        self.stack = type("Stack", (), {"currentIndex": lambda self: -1})()
        self.tiles = None
        self._fw = object()

    def focusWidget(self):
        return self._fw


def test_ctor_raises_when_missing_dependencies():
    mw = MWBase()
    # удалим по очереди атрибуты и проверим, что конструктор валидирует
    for attr in ("tree", "links_actions", "table", "stack", "tiles"):
        mw2 = MWBase()
        delattr(mw2, attr)
        with pytest.raises(ValueError):
            ActionController(mw2)


def test_helpers_raise_when_methods_missing():
    mw = MWBase()
    ctrl = ActionController(mw)

    # tree missing currentIndex
    mw_bad_tree = MWBase()
    mw_bad_tree.tree = object()
    with pytest.raises(ValueError):
        ActionController(mw_bad_tree)._has_tree_selection()

    # table missing hasFocus
    mw_bad_table = MWBase()
    mw_bad_table.table = object()
    with pytest.raises(ValueError):
        ActionController(mw_bad_table)._is_table_focused()

    # stack missing currentIndex
    mw_bad_stack = MWBase()
    mw_bad_stack.stack = object()
    with pytest.raises(ValueError):
        ActionController(mw_bad_stack)._is_table_stack_active()

    # links_actions missing get_selected_rows
    mw_bad_la = MWBase()
    mw_bad_la.links_actions = object()
    with pytest.raises(ValueError):
        ActionController(mw_bad_la)._table_has_selection()
