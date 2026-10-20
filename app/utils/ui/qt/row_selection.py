"""Apply table row selections with one notification and compact ranges."""

from PyQt6.QtCore import QItemSelection, QItemSelectionModel


def select_rows(view, rows) -> None:
    model = view.model()
    selection_model = view.selectionModel()
    if model is None or selection_model is None:
        return
    rows = list(dict.fromkeys(row for row in rows if 0 <= row < model.rowCount()))
    selection = QItemSelection()
    ordered = sorted(rows)
    if ordered and model.columnCount() > 0:
        start = end = ordered[0]
        for row in ordered[1:]:
            if row == end + 1:
                end = row
            else:
                selection.select(model.index(start, 0), model.index(end, model.columnCount() - 1))
                start = end = row
        selection.select(model.index(start, 0), model.index(end, model.columnCount() - 1))
    selection_model.select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
    if rows:
        selection_model.setCurrentIndex(
            model.index(rows[0], 0), QItemSelectionModel.SelectionFlag.NoUpdate
        )
