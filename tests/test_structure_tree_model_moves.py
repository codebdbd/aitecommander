from PyQt6.QtCore import Qt

from app.views.models.structure_tree_model import StructureTreeModel


def _section_ids(model: StructureTreeModel):
    root_rows = model.rowCount()
    ids = []
    for r in range(root_rows):
        idx = model.index(r, 0)
        t = model.data(idx, Qt.ItemDataRole.UserRole)
        ids.append(t[1] if isinstance(t, (tuple, list)) else None)
    return ids


def _category_ids(model: StructureTreeModel, section_id: int):
    sidx = model.index_for("section", section_id)
    rows = model.rowCount(sidx)
    ids = []
    for r in range(rows):
        idx = model.index(r, 0, sidx)
        t = model.data(idx, Qt.ItemDataRole.UserRole)
        ids.append(t[1] if isinstance(t, (tuple, list)) else None)
    return ids


def test_move_sections_uses_move_and_preserves_order(qtbot, monkeypatch):
    model = StructureTreeModel()
    model.set_snapshot([
        {"id": 1, "name": "B"},
        {"id": 2, "name": "A"},
        {"id": 3, "name": "C"},
    ])

    # Spy counters
    calls = {"moverows": 0, "insertrows": 0, "removerows": 0}

    def _wrap(fn_name):
        orig = getattr(model, fn_name)
        def _spy(*args, **kwargs):
            calls[fn_name.split('begin')[-1].lower()] += 1
            return orig(*args, **kwargs)
        return _spy

    # Patch beginMoveRows/beginInsertRows/beginRemoveRows
    monkeypatch.setattr(model, 'beginMoveRows', _wrap('beginMoveRows'))
    monkeypatch.setattr(model, 'beginInsertRows', _wrap('beginInsertRows'))
    monkeypatch.setattr(model, 'beginRemoveRows', _wrap('beginRemoveRows'))

    # New order forces reordering: [2,1,3]
    model.update_snapshot([
        {"id": 2, "name": "A"},
        {"id": 1, "name": "B"},
        {"id": 3, "name": "C"},
    ])

    assert _section_ids(model) == [2, 1, 3]
    # Expect at least one move and no remove/insert for reordering existing items
    assert calls["moverows"] >= 1
    assert calls["insertrows"] == 0
    assert calls["removerows"] == 0


def test_move_categories_uses_move_and_preserves_order(qtbot, monkeypatch):
    model = StructureTreeModel()
    model.set_snapshot([
        {
            "id": 1,
            "name": "Sec",
            "categories": [
                {"id": 10, "name": "X"},
                {"id": 20, "name": "Y"},
                {"id": 30, "name": "Z"},
            ],
        }
    ])

    calls = {"moverows": 0, "insertrows": 0, "removerows": 0}

    def _wrap(fn_name):
        orig = getattr(model, fn_name)
        def _spy(*args, **kwargs):
            calls[fn_name.replace('begin', '').lower()] += 1
            return orig(*args, **kwargs)
        return _spy

    monkeypatch.setattr(model, 'beginMoveRows', _wrap('beginMoveRows'))
    monkeypatch.setattr(model, 'beginInsertRows', _wrap('beginInsertRows'))
    monkeypatch.setattr(model, 'beginRemoveRows', _wrap('beginRemoveRows'))

    # Reorder to [30, 10, 20]
    model.update_snapshot([
        {
            "id": 1,
            "name": "Sec",
            "categories": [
                {"id": 30, "name": "Z"},
                {"id": 10, "name": "X"},
                {"id": 20, "name": "Y"},
            ],
        }
    ])

    assert _category_ids(model, 1) == [30, 10, 20]
    assert calls["moverows"] >= 1
    assert calls["insertrows"] == 0
    assert calls["removerows"] == 0
