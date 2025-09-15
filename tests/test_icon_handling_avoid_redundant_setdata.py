from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtGui import QIcon

import types

from app.controllers.ui.structure import icon_handling as ih_mod
from app.controllers.ui.structure.icon_handling import IconHandling


class FakeIndex:
    def __init__(self, item_type: str, item_id: int):
        self._type = item_type
        self._id = item_id

    def isValid(self):
        return True


class FakeModel:
    def __init__(self):
        self.calls = []  # list of tuples (id, value)
        self._root_count = 2
        self._ids = [1, 2]

    def rowCount(self, parent: QModelIndex = QModelIndex()):
        # Only top-level sections, no children
        if not parent or not getattr(parent, 'isValid', lambda: False)():
            return self._root_count
        return 0

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()):
        if column != 0:
            return QModelIndex()
        if not parent or not getattr(parent, 'isValid', lambda: False)():
            if 0 <= row < self._root_count:
                return FakeIndex('section', self._ids[row])
        return QModelIndex()

    def setData(self, index, value, role):
        # Only record DecorationRole
        if role == Qt.ItemDataRole.DecorationRole and hasattr(index, '_id'):
            self.calls.append((index._id, isinstance(value, QIcon)))
        return True


class FakeTree:
    def __init__(self, model):
        self._model = model

    def model(self):
        return self._model


class FakeController:
    def __init__(self, tree):
        self.tree = tree
        self.business = types.SimpleNamespace()


def test_apply_resolved_icons_skips_unchanged(monkeypatch):
    # Arrange: monkeypatch helpers used inside icon_handling
    # get_tree_tuple -> use FakeIndex internals
    def _fake_get_tree_tuple(idx, _col):
        return (idx._type, idx._id) if hasattr(idx, '_type') else None

    monkeypatch.setattr(ih_mod, 'get_tree_tuple', _fake_get_tree_tuple)

    # create_icon_from_path -> return empty QIcon without FS
    monkeypatch.setattr(ih_mod, 'create_icon_from_path', lambda p: QIcon())

    # QTimer.singleShot -> call immediately to execute synchronously
    class _ImmediateQTimer:
        @staticmethod
        def singleShot(_ms, fn):
            fn()
    monkeypatch.setattr(ih_mod, 'QTimer', _ImmediateQTimer)

    model = FakeModel()
    tree = FakeTree(model)
    ctrl = FakeController(tree)
    handler = IconHandling(ctrl)

    # Act 1: initial apply with two distinct paths
    token = 1
    sec_paths = {1: 'p/a', 2: 'p/b'}
    cat_paths = {}
    handler._apply_resolved_icons(token, sec_paths, cat_paths)

    # Both items should be set once
    assert model.calls == [(1, True), (2, True)]

    # Clear calls and apply again: only id=2 changes
    model.calls.clear()
    sec_paths2 = {1: 'p/a', 2: 'p/b2'}
    handler._apply_resolved_icons(token, sec_paths2, cat_paths)

    # Only one update for changed item 2
    assert model.calls == [(2, True)]
