import pytest
from PyQt6.QtCore import QItemSelectionModel, QModelIndex, Qt
from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

from app.views.widgets.link.base_table import LinksTableView
from app.views.widgets.link.columns import LinkTableColumn


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _sample_links():
    return [
        {
            "id": 10,
            "name": "Bravo",
            "position": 0,
            "type": "web",
            "url": "https://bravo.example",
            "notes": "notes B",
            "group_launch": False,
        },
        {
            "id": 20,
            "name": "Alpha",
            "position": 1,
            "type": "file",
            "url": "C:/tmp/alpha.txt",
            "notes": "notes A",
            "group_launch": True,
        },
        {
            "id": 30,
            "name": "Charlie",
            "position": 2,
            "type": "folder",
            "url": "C:/tmp/charlie",
            "notes": "notes C",
            "group_launch": False,
        },
    ]


def test_sort_preserves_persistent_indexes(qapp):
    table = LinksTableView()
    table.populate(_sample_links(), mode="normal")
    model = table.model()

    # Link 10 ("Bravo") is initially at row 0
    p_idx = model.index(0, 0)
    # Track as persistent
    persistent = [model.index(0, 0)]
    # In Qt, selecting row creates persistent indexes in selectionModel
    sm = table.selectionModel()
    sm.select(
        p_idx,
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )

    # Sort ascending by Name (column 1): Alpha (20) -> Bravo (10) -> Charlie (30)
    model.sort(int(LinkTableColumn.NAME), Qt.SortOrder.AscendingOrder)

    # Bravo (id 10) must now be at row 1
    selected_rows = sm.selectedRows()
    assert len(selected_rows) == 1
    assert selected_rows[0].row() == 1
    assert model.get_link(1)["id"] == 10


def test_links_equal_detects_all_fields(qapp):
    table = LinksTableView()
    base = {
        "id": 1,
        "name": "Test",
        "url": "https://example.com",
        "path": "",
        "type": "web",
        "chrome_rotation": 0,
        "is_favorite": 0,
        "notes": "",
        "icon_path": "",
        "args": "",
        "last_used": None,
        "is_group_launch": 0,
    }

    # Same
    assert table._links_equal(dict(base), dict(base), "normal") is True

    # Difference in url
    c1 = dict(base)
    c1["url"] = "https://other.com"
    assert table._links_equal(base, c1, "normal") is False

    # Difference in path
    c2 = dict(base)
    c2["path"] = "C:/app.exe"
    assert table._links_equal(base, c2, "normal") is False

    # Difference in type
    c3 = dict(base)
    c3["type"] = "app"
    assert table._links_equal(base, c3, "normal") is False

    # Difference in chrome_rotation
    c4 = dict(base)
    c4["chrome_rotation"] = 1
    assert table._links_equal(base, c4, "normal") is False

    # Difference in group_launch (boolean vs int)
    c5 = dict(base)
    c5["group_launch"] = True
    assert table._links_equal(base, c5, "normal") is False


def test_restore_ui_state_multi_selection(qapp):
    table = LinksTableView()
    table.populate(_sample_links(), mode="normal")

    # Call _restore_ui_state with selection of [10, 30]
    table._restore_ui_state(
        selection=[10, 30],
        scroll_pos=0,
        sort_col=-1,
        sort_order=Qt.SortOrder.AscendingOrder,
    )

    selected_ids = [
        table.model().get_link(idx.row())["id"]
        for idx in table.selectionModel().selectedRows()
    ]
    assert set(selected_ids) == {10, 30}


def test_apply_name_column_elision_preserves_text_for_size_hint(qapp):
    table = LinksTableView()
    delegate = table.delegate

    opt = QStyleOptionViewItem()
    opt.text = "This is a very long text that must not be stripped in initStyleOption"
    delegate._apply_name_column_elision(opt)

    # opt.text must be preserved unelided
    assert opt.text == "This is a very long text that must not be stripped in initStyleOption"
    assert opt.textElideMode == Qt.TextElideMode.ElideRight


def test_group_launch_state(qapp):
    table = LinksTableView()
    table.populate(_sample_links(), mode="normal")
    model = table.model()

    # Initially 1 of 3 is True -> NoChange (tri-state)
    assert model.group_launch_state() == QStyle.StateFlag.State_NoChange

    # Set all False -> State_Off
    model.set_all_group_launch(0)
    assert model.group_launch_state() == QStyle.StateFlag.State_Off

    # Set all True -> State_On
    model.set_all_group_launch(1)
    assert model.group_launch_state() == QStyle.StateFlag.State_On


def test_get_selected_rows_cell_selection_fallback(qapp):
    from app.utils.ui.qt.roles import get_selected_rows

    table = LinksTableView()
    table.populate(_sample_links(), mode="normal")
    model = table.model()
    sm = table.selectionModel()

    # Select only a single cell in column 1 (Name) without Rows flag
    cell_idx = model.index(1, int(LinkTableColumn.NAME))
    sm.select(cell_idx, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    # selectedRows() in Qt is empty for cell selection, but get_selected_rows must resolve row 1
    assert sm.selectedRows() == []
    assert get_selected_rows(table) == [1]
