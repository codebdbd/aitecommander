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


def test_prepare_snapshot_sorts_only_without_icon_preparation(monkeypatch):
    ctrl = _DummyController()
    tm = TreeManagement(ctrl, category_tiles_controller=_DummyTiles())

    # prepare_icons_snapshot больше не вызывается из _prepare_snapshot — проверяем только сортировку

    src = [
        {"name": "work"},
        {"name": "Zeta"},
        {"name": "alpha"},
        {"name": "Beta"},
    ]

    result = tm._prepare_snapshot(src)
    # Ensure sorting is case-insensitive: alpha, Beta, work, Zeta
    names = [d.get("name") for d in result]
    assert names == ["alpha", "Beta", "work", "Zeta"]

