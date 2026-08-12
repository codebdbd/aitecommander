from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtGui import QStandardItemModel

from app.views.windows.main_window import MainWindow


class _ViewportStub:
    def __init__(self) -> None:
        self.updated = False

    def update(self) -> None:
        self.updated = True


class _TableStub:
    def __init__(self, model: QStandardItemModel) -> None:
        self._model = model
        self._selection_model = QItemSelectionModel(model)
        self._viewport = _ViewportStub()
        self.updates_enabled: list[bool] = []
        self.select_all_called = False

    def model(self) -> QStandardItemModel:
        return self._model

    def selectionModel(self) -> QItemSelectionModel:
        return self._selection_model

    def setUpdatesEnabled(self, value: bool) -> None:
        self.updates_enabled.append(value)

    def viewport(self) -> _ViewportStub:
        return self._viewport

    def selectAll(self) -> None:
        self.select_all_called = True


def test_select_all_links_uses_single_row_range_selection() -> None:
    model = QStandardItemModel(100, 4)
    table = _TableStub(model)
    main_window = SimpleNamespace(table=table)

    MainWindow.select_all_links(main_window)

    assert table.select_all_called is False
    assert table.updates_enabled == [False, True]
    assert table.viewport().updated is True
    assert len(table.selectionModel().selectedRows()) == 100
