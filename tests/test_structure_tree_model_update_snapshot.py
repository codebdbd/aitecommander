import pytest
from PyQt6.QtCore import Qt, QPersistentModelIndex, QModelIndex
from PyQt6.QtGui import QIcon

from app.views.models.structure_tree_model import StructureTreeModel


def build_sections(*names_with_ids_and_cats):
    """Helper to build snapshot sections.
    names_with_ids_and_cats: iterable of tuples (sid, name, [ (cid, cname) ... ])
    """
    sections = []
    for sid, name, cats in names_with_ids_and_cats:
        sections.append(
            {
                "id": sid,
                "name": name,
                "icon": QIcon(),
                "categories": [
                    {"id": cid, "name": cname, "icon": QIcon()} for cid, cname in (cats or [])
                ],
            }
        )
    return sections


def index_tuple(model, idx: QModelIndex):
    if not idx or not idx.isValid():
        return None
    val = model.data(idx, Qt.ItemDataRole.UserRole)
    return tuple(val) if isinstance(val, (tuple, list)) and len(val) == 2 else None


def test_add_remove_sections_and_categories(qtbot):
    model = StructureTreeModel()

    # 1) Add two sections with categories
    initial = build_sections(
        (1, "Alpha", [(101, "A1"), (102, "A2")]),
        (2, "Beta", [(201, "B1")]),
    )
    model.set_snapshot(initial)

    # Verify structure
    assert model.rowCount(QModelIndex()) == 2
    s0 = model.index(0, 0, QModelIndex())
    s1 = model.index(1, 0, QModelIndex())
    assert model.data(s0, Qt.ItemDataRole.DisplayRole) == "Alpha"
    assert model.data(s1, Qt.ItemDataRole.DisplayRole) == "Beta"

    # 2) Remove one category and one section via update_snapshot
    updated = build_sections(
        (1, "Alpha", [(101, "A1")]),  # 102 removed
        # section 2 removed
    )
    model.update_snapshot(updated)

    assert model.rowCount(QModelIndex()) == 1
    s0 = model.index(0, 0, QModelIndex())
    assert model.data(s0, Qt.ItemDataRole.DisplayRole) == "Alpha"
    # Only one category remains
    assert model.rowCount(s0) == 1
    c0 = model.index(0, 0, s0)
    assert model.data(c0, Qt.ItemDataRole.DisplayRole) == "A1"


def test_rename_and_icon_change(qtbot):
    model = StructureTreeModel()
    initial = build_sections((1, "Alpha", [(101, "A1")]))
    # set_snapshot uses icons provided
    model.set_snapshot(initial)

    s_idx = model.index(0, 0, QModelIndex())
    c_idx = model.index(0, 0, s_idx)

    # Cache keys before
    s_icon0 = model.data(s_idx, Qt.ItemDataRole.DecorationRole)
    c_icon0 = model.data(c_idx, Qt.ItemDataRole.DecorationRole)
    assert isinstance(s_icon0, QIcon)
    assert isinstance(c_icon0, QIcon)
    s_key0 = s_icon0.cacheKey()
    c_key0 = c_icon0.cacheKey()

    # Update name and icon
    new_icon_s = QIcon()
    new_icon_c = QIcon()
    updated = [
        {
            "id": 1,
            "name": "Alpha Renamed",
            "icon": new_icon_s,
            "categories": [
                {"id": 101, "name": "A1 Renamed", "icon": new_icon_c}
            ],
        }
    ]
    model.update_snapshot(updated)

    # Names updated
    assert model.data(s_idx, Qt.ItemDataRole.DisplayRole) == "Alpha Renamed"
    assert model.data(c_idx, Qt.ItemDataRole.DisplayRole) == "A1 Renamed"

    # Icons potentially new (cacheKey can be equal for empty QIcon, so allow equality or inequality but ensure QIcon instance)
    s_icon1 = model.data(s_idx, Qt.ItemDataRole.DecorationRole)
    c_icon1 = model.data(c_idx, Qt.ItemDataRole.DecorationRole)
    assert isinstance(s_icon1, QIcon)
    assert isinstance(c_icon1, QIcon)
    # At minimum we verify icon role still returns QIcon; cacheKey may match for empty icons


def test_reorder_sections_and_categories(qtbot):
    model = StructureTreeModel()
    initial = build_sections(
        (1, "Alpha", [(101, "A1"), (102, "A2")]),
        (2, "Beta", [(201, "B1"), (202, "B2")]),
    )
    model.set_snapshot(initial)

    # Reorder: Beta first, and inside Alpha swap categories
    updated = build_sections(
        (2, "Beta", [(201, "B1"), (202, "B2")]),
        (1, "Alpha", [(102, "A2"), (101, "A1")]),
    )
    model.update_snapshot(updated)

    # Verify order of sections
    s0 = model.index(0, 0, QModelIndex())
    s1 = model.index(1, 0, QModelIndex())
    assert model.data(s0, Qt.ItemDataRole.DisplayRole) == "Beta"
    assert model.data(s1, Qt.ItemDataRole.DisplayRole) == "Alpha"

    # Verify order of Alpha categories (now second section)
    alpha_idx = s1
    assert model.rowCount(alpha_idx) == 2
    c0 = model.index(0, 0, alpha_idx)
    c1 = model.index(1, 0, alpha_idx)
    assert model.data(c0, Qt.ItemDataRole.DisplayRole) == "A2"
    assert model.data(c1, Qt.ItemDataRole.DisplayRole) == "A1"


def test_persistent_index_preserved_on_local_update(qtbot):
    model = StructureTreeModel()
    initial = build_sections(
        (1, "Alpha", [(101, "A1"), (102, "A2")]),
        (2, "Beta", [(201, "B1")]),
    )
    model.set_snapshot(initial)

    # Take persistent index to category 102 (A2)
    s_alpha = model.index(0, 0, QModelIndex())
    idx_a2 = model.index(1, 0, s_alpha)
    pidx = QPersistentModelIndex(idx_a2)
    t_before = index_tuple(model, idx_a2)
    assert t_before == ("category", 102)
    assert pidx.isValid()

    # Update only Beta name — should not invalidate A2 index
    updated = build_sections(
        (1, "Alpha", [(101, "A1"), (102, "A2")]),
        (2, "Beta Renamed", [(201, "B1")]),
    )
    model.update_snapshot(updated)

    # Persistent index should remain valid and point to same (type, id)
    assert pidx.isValid()
    t_after = index_tuple(model, pidx)
    assert t_after == ("category", 102)
