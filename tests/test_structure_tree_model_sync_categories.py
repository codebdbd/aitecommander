from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from app.views.models.structure_tree_model import StructureTreeModel


def _names_in_section(model: StructureTreeModel, section_id: int):
    # Helper to fetch ordered category names for a section
    sec_idx = model.index_for("section", section_id)
    assert sec_idx and sec_idx.isValid()
    row_count = model.rowCount(sec_idx)
    names = []
    ids = []
    for r in range(row_count):
        idx = model.index(r, 0, sec_idx)
        t = model.data(idx, Qt.ItemDataRole.UserRole)
        names.append(model.data(idx, Qt.ItemDataRole.DisplayRole))
        ids.append(t[1] if isinstance(t, (tuple, list)) else None)
    return ids, names


def test_sync_categories_insert_delete_update_reorder_single_section(qtbot):
    # Initial snapshot: Sec#1 with cats [A(101), B(102), C(103)]
    model = StructureTreeModel()
    initial = [
        {
            "id": 1,
            "name": "Sec1",
            "icon": QIcon(),
            "categories": [
                {"id": 101, "name": "A"},
                {"id": 102, "name": "B"},
                {"id": 103, "name": "C"},
            ],
        }
    ]
    model.set_snapshot(initial)

    # Update snapshot:
    # - remove B(102)
    # - insert D(104) at position 1
    # - update C(103) name to "C*"
    # - order: A(101), D(104), C(103)
    updated = [
        {
            "id": 1,
            "name": "Sec1",
            "icon": QIcon(),
            "categories": [
                {"id": 101, "name": "A"},
                {"id": 104, "name": "D"},
                {"id": 103, "name": "C*"},
            ],
        }
    ]
    model.update_snapshot(updated)

    ids, names = _names_in_section(model, 1)
    assert ids == [101, 104, 103]
    assert names == ["A", "D", "C*"]

    # B(102) must be removed
    idx_b = model.index_for("category", 102)
    assert not idx_b or not idx_b.isValid()


def test_sync_categories_reorder_only(qtbot):
    # Initial snapshot: Sec#2 with cats [X(201), Y(202)]
    model = StructureTreeModel()
    model.set_snapshot([
        {
            "id": 2,
            "name": "Sec2",
            "categories": [
                {"id": 201, "name": "X"},
                {"id": 202, "name": "Y"},
            ],
        }
    ])

    # New order: [Y(202), X(201)]
    model.update_snapshot([
        {
            "id": 2,
            "name": "Sec2",
            "categories": [
                {"id": 202, "name": "Y"},
                {"id": 201, "name": "X"},
            ],
        }
    ])

    ids, names = _names_in_section(model, 2)
    assert ids == [202, 201]
    assert names == ["Y", "X"]


def test_sync_categories_icon_updates(qtbot):
    # Initial snapshot: icons are None
    model = StructureTreeModel()
    model.set_snapshot([
        {
            "id": 3,
            "name": "Sec3",
            "categories": [
                {"id": 301, "name": "I0"},
            ],
        }
    ])

    # Update snapshot: set QIcon for category 301 and rename
    updated = [
        {
            "id": 3,
            "name": "Sec3",
            "categories": [
                {"id": 301, "name": "I1", "icon": QIcon()},
            ],
        }
    ]
    model.update_snapshot(updated)

    sec_idx = model.index_for("section", 3)
    idx = model.index(0, 0, sec_idx)
    # Check name updated
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "I1"
    # Check icon set
    icon = model.data(idx, Qt.ItemDataRole.DecorationRole)
    assert isinstance(icon, QIcon)


def test_sync_categories_remove_all(qtbot):
    # Initial snapshot with two categories
    model = StructureTreeModel()
    model.set_snapshot([
        {
            "id": 4,
            "name": "Sec4",
            "categories": [
                {"id": 401, "name": "A"},
                {"id": 402, "name": "B"},
            ],
        }
    ])

    # Update snapshot: no categories
    model.update_snapshot([
        {
            "id": 4,
            "name": "Sec4",
            "categories": [],
        }
    ])

    sec_idx = model.index_for("section", 4)
    assert model.rowCount(sec_idx) == 0
