from types import SimpleNamespace

from PyQt6.QtCore import QItemSelectionModel

from app.controllers.ui.action_controller import ActionController
from app.views.widgets.link.links_model import LinksTableModel
from app.views.windows.main_window import MainWindow


class CountingLinksModel(LinksTableModel):
    flag_reads = 0

    def flags(self, index):
        self.flag_reads += 1
        return super().flags(index)


def test_select_all_action_state_does_not_enumerate_rows(qapp):
    """Exercise the selection signal using the real application table model."""
    from PyQt6.QtWidgets import QTableView

    model = CountingLinksModel()
    model._links = [{"id": row} for row in range(30_000)]
    table = QTableView()
    table.setModel(model)
    window = SimpleNamespace(table=table)
    controller = SimpleNamespace(main_window=window)
    states = []
    table.selectionModel().selectionChanged.connect(
        lambda *_: states.append(ActionController._table_has_selection(controller))
    )
    model.flag_reads = 0

    MainWindow.select_all_links(window)

    assert states == [True]
    assert model.flag_reads < 100
    ranges = table.selectionModel().selection()
    assert len(ranges) == 1
    assert ranges[0].top() == 0
    assert ranges[0].bottom() == 29_999
    table.clearSelection()
    assert states == [True, False]
    table.close()


def test_tiles_action_state_does_not_fetch_selected_ids():
    model = CountingLinksModel()
    model._links = [{"id": row} for row in range(30_000)]
    selection = QItemSelectionModel(model)
    view = SimpleNamespace(selectionModel=lambda: selection)
    controller = SimpleNamespace(_get_tiles_view=lambda: view)
    assert not ActionController._tiles_has_selection(controller)
    selection.select(model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
    model.flag_reads = 0
    assert ActionController._tiles_has_selection(controller)
    assert model.flag_reads < 100
    selection.clearSelection()
    assert not ActionController._tiles_has_selection(controller)


def test_collect_bulk_rows_avoids_per_cell_flag_checks(qapp):
    from PyQt6.QtWidgets import QTableView

    from app.utils.ui.qt.roles import get_selected_rows
    from app.utils.ui.qt.row_selection import select_rows

    model = CountingLinksModel()
    model._links = [{"id": row} for row in range(30_000)]
    table = QTableView()
    table.setModel(model)
    select_rows(table, range(30_000))
    model.flag_reads = 0
    assert get_selected_rows(table) == list(range(30_000))
    assert model.flag_reads == 0
    table.close()


def test_restore_bulk_selection_emits_once_and_preserves_current(qapp, monkeypatch):
    from PyQt6.QtCore import Qt

    from app.utils.ui.qt.roles import get_selected_rows
    from app.views.widgets.link.base_table import LinksTableView

    table = LinksTableView()
    model = table.model()
    model.set_links([{"id": row, "name": str(row)} for row in range(5000)])
    monkeypatch.setattr(
        model, "find_row_by_id",
        lambda *_: (_ for _ in ()).throw(AssertionError("Repeated linear lookup")),
    )
    changes = []
    table.selectionModel().selectionChanged.connect(lambda *_: changes.append(True))
    ids = [4000, *range(1000), 4000, -1]
    table._restore_ui_state(ids, 0, -1, Qt.SortOrder.AscendingOrder)
    assert get_selected_rows(table) == [*range(1000), 4000]
    assert table.currentIndex().row() == 4000
    assert len(table.selectionModel().selection()) == 2
    assert len(changes) == 1
    table.close()
