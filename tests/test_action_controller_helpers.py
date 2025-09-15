from __future__ import annotations

import types

from app.controllers.ui.action_controller import ActionController
from app.config_data import app_config


class DummyIndex:
    def __init__(self, valid: bool = True):
        self._valid = valid

    def isValid(self):
        return self._valid


class DummyTree:
    def __init__(self, focused=False, has_sel=False):
        self._focused = focused
        self._has_sel = has_sel

    def currentIndex(self):
        return DummyIndex(valid=self._has_sel)

    def hasFocus(self):
        return bool(self._focused)

    def isAncestorOf(self, _):
        return False


class DummyTable:
    def __init__(self, focused=False):
        self._focused = focused

    def hasFocus(self):
        return bool(self._focused)

    def isAncestorOf(self, _):
        return False


class DummyStack:
    def __init__(self, idx):
        self._idx = idx

    def currentIndex(self):
        return self._idx


class DummyLinksActions:
    def __init__(self, rows=None, links=None):
        self._rows = rows or []
        self._links = links or []
        self._deleted = None

    def get_selected_rows(self):
        return list(self._rows)

    def get_selected_links(self):
        return list(self._links)

    def delete_links_with_confirmation(self, links):
        self._deleted = list(links)


class DummyStructure:
    def __init__(self):
        self.edited = 0
        self.deleted = 0

    def edit_selected_item(self):
        self.edited += 1

    def delete_selected_item(self):
        self.deleted += 1


class DummyMainWindow:
    def __init__(self):
        self.tree = DummyTree()
        self.table = DummyTable()
        self.stack = DummyStack(-1)
        self.tiles = None
        self.links_actions = DummyLinksActions()
        self.structure = DummyStructure()
        self._focused_widget = object()
        self._status_updates = 0

    def focusWidget(self):
        return self._focused_widget

    def update_statusbar(self):
        self._status_updates += 1


def test_edit_current_uses_table_stack_and_selection(monkeypatch):
    mw = DummyMainWindow()
    mw.stack = DummyStack(app_config.ui.get_stack_index_table())
    mw.links_actions = DummyLinksActions(rows=[1])

    ctrl = ActionController(mw)

    called = {"n": 0}

    def _spy_edit_selected_link():
        called["n"] += 1

    # monkeypatch the private method to avoid deeper dependencies
    monkeypatch.setattr(ctrl, "_edit_selected_link", _spy_edit_selected_link, raising=True)

    ctrl.edit_current()

    assert called["n"] == 1


def test_delete_current_table_focus_and_selection(monkeypatch):
    mw = DummyMainWindow()
    mw.table = DummyTable(focused=True)
    mw.links_actions = DummyLinksActions(rows=[0], links=[{"id": 1}])

    ctrl = ActionController(mw)
    ctrl.delete_current()

    # deletion called and status updated
    assert mw.links_actions._deleted == [{"id": 1}]
    assert mw._status_updates == 1


def test_edit_current_tree_focus_and_selection():
    mw = DummyMainWindow()
    mw.tree = DummyTree(focused=True, has_sel=True)

    ctrl = ActionController(mw)
    ctrl.edit_current()

    assert mw.structure.edited == 1


def test_delete_current_tree_focus_and_selection():
    mw = DummyMainWindow()
    mw.tree = DummyTree(focused=True, has_sel=True)

    ctrl = ActionController(mw)
    ctrl.delete_current()

    assert mw.structure.deleted == 1
    assert mw._status_updates == 1
