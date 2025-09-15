from PyQt6.QtGui import QIcon

import app.controllers.ui.structure.icon_handling as ih_mod
from app.controllers.ui.structure.icon_handling import IconHandling


class _DummyIndex:
    def __init__(self, typ, _id, children=None):
        self.typ = typ
        self.id = _id
        self.children = children or []

    def isValid(self):
        return True


class _DummyModel:
    def __init__(self):
        # root: two sections (ids 1,2) with categories
        self.root = [
            _DummyIndex("section", 1, children=[_DummyIndex("category", 101), _DummyIndex("category", 102)]),
            _DummyIndex("section", 2, children=[_DummyIndex("category", 201)]),
        ]
        self.set_calls = []

    def rowCount(self, parent_index):
        if getattr(parent_index, "_is_root", False):
            return len(self.root)
        if isinstance(parent_index, _DummyIndex):
            return len(parent_index.children)
        # Treat unknown parent as root
        return len(self.root)

    def index(self, r, c, parent_index):
        if getattr(parent_index, "_is_root", False):
            return self.root[r]
        if isinstance(parent_index, _DummyIndex):
            return parent_index.children[r]
        # Root case
        return self.root[r]

    def setData(self, idx, icon, role):
        # Capture only decoration role writes
        self.set_calls.append((idx.typ, idx.id, isinstance(icon, QIcon), role))


class _DummyTree:
    def __init__(self, model):
        self._model = model

    def model(self):
        return self._model


class _DummyController:
    def __init__(self, model):
        self.tree = _DummyTree(model)
        self.business = object()


def test_gather_ids_collects_section_and_category_ids(monkeypatch):
    model = _DummyModel()
    ctrl = _DummyController(model)
    ih = IconHandling(ctrl)

    # Patch get_tree_tuple to read from DummyIndex
    monkeypatch.setattr(
        ih_mod,
        "get_tree_tuple",
        lambda idx, _col: (getattr(idx, "typ", None), getattr(idx, "id", None)),
    )

    # Patch QModelIndex used as root marker to a simple object marked as root
    class _Root:
        _is_root = True

    # _gather_ids uses QModelIndex() constructor internally; patch module symbol to our Root
    monkeypatch.setattr(ih_mod, "QModelIndex", _Root)

    sec_ids, cat_ids = ih._gather_ids(model)
    assert sec_ids == {1, 2}
    assert cat_ids == {101, 102, 201}


def test_apply_resolved_icons_sets_decoration_role(monkeypatch):
    model = _DummyModel()
    ctrl = _DummyController(model)
    ih = IconHandling(ctrl)

    # Patch get_tree_tuple
    monkeypatch.setattr(
        ih_mod,
        "get_tree_tuple",
        lambda idx, _col: (getattr(idx, "typ", None), getattr(idx, "id", None)),
    )

    # Patch QModelIndex for root
    class _Root:
        _is_root = True

    monkeypatch.setattr(ih_mod, "QModelIndex", _Root)

    # Patch QTimer to run immediately
    class _QTimer:
        @staticmethod
        def singleShot(_ms, func):
            func()

    monkeypatch.setattr(ih_mod, "QTimer", _QTimer)

    # Patch create_icon_from_path to always return QIcon
    monkeypatch.setattr(ih_mod, "create_icon_from_path", lambda _p: QIcon())

    sec_icon_path = {1: "path-sec-1", 2: "path-sec-2"}
    cat_icon_path = {101: "path-cat-101", 201: "path-cat-201"}

    ih._apply_resolved_icons(0, sec_icon_path, cat_icon_path)

    # Expect setData calls for all items: 2 sections + 3 categories = 5 writes
    # Each call should have (typ, id, is_qicon, role)
    types_ids = {(t, i) for (t, i, _is_icon, _role) in model.set_calls}
    assert ("section", 1) in types_ids
    assert ("section", 2) in types_ids
    assert ("category", 101) in types_ids
    assert ("category", 102) in types_ids
    assert ("category", 201) in types_ids

    # Ensure QIcon objects were passed
    assert all(isinstance(c[2], bool) and c[2] for c in model.set_calls)
