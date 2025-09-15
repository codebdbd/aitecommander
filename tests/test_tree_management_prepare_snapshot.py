import types

import app.controllers.ui.structure.tree_management as tm_mod
from app.controllers.ui.structure.tree_management import TreeManagement


class _DummyModel:
    def insert_sections(self, row, items):
        pass

    def insert_categories(self, sid, row, items):
        pass

    def update_item(self, typ, _id, data):
        pass


class _DummyTree:
    def model(self):
        return _DummyModel()


class _DummyTiles:
    def clear(self):
        pass

    def refresh(self, _sid: int):
        pass


class _DummyController:
    def __init__(self):
        self.tree = _DummyTree()
        self.icon_handler = object()


def test_prepare_snapshot_sorts_and_calls_prepare_icons_snapshot(monkeypatch):
    ctrl = _DummyController()
    tm = TreeManagement(ctrl, category_tiles_controller=_DummyTiles())

    captured = {}

    def _stub_prepare_icons_snapshot(data):
        # capture input for assertions, return as-is
        captured["received"] = list(data)
        return data

    # Monkeypatch the module-level imported function used by TreeManagement
    monkeypatch.setattr(tm_mod, "prepare_icons_snapshot", _stub_prepare_icons_snapshot)

    src = [
        {"name": "work"},
        {"name": "Zeta"},
        {"name": "alpha"},
        {"name": "Beta"},
    ]

    result = tm._prepare_snapshot(src)

    # Ensure sorting is case-insensitive: alpha, Beta, work, Zeta
    received = captured.get("received")
    assert received is not None, "prepare_icons_snapshot must be invoked"
    names = [d.get("name") for d in received]
    assert names == ["alpha", "Beta", "work", "Zeta"]

    # The result should be what stub returned (same list object values order)
    assert [d.get("name") for d in result] == names
