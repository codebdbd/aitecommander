from __future__ import annotations

import logging

from PyQt6.QtCore import QModelIndex, QObject

from app.utils.ui.qt.roles import get_tree_tuple

logger = logging.getLogger(__name__)


class TreeStateService(QObject):
    """Utilities to save/restore structure tree state."""

    def __init__(self, *, controller, tree, model):
        parent = controller if isinstance(controller, QObject) else None
        super().__init__(parent=parent)
        self._controller = controller
        self._tree = tree
        self._model = model

    # --- Save/restore expansion ---
    def capture_expanded_state(self) -> dict[tuple[str, int], bool]:
        state: dict[tuple[str, int], bool] = {}
        try:
            for index in self._iter_indexes():
                if self._model.rowCount(index) > 0:
                    key = get_tree_tuple(index, 0)
                    if key is not None:
                        state[key] = self._tree.isExpanded(index)
        except Exception:
            logger.exception(
                "TreeStateService.capture_expanded_state: failed to capture expanded state"
            )
        return state

    def restore_expanded_state(self, expanded_state: dict[tuple[str, int], bool]) -> None:
        if not expanded_state:
            return
        try:
            for (item_type, item_id), value in expanded_state.items():
                index = self._model.index_for(item_type, item_id)
                if index and index.isValid():
                    self._tree.setExpanded(index, bool(value))
        except Exception:
            logger.exception(
                "TreeStateService.restore_expanded_state: failed to restore expanded state"
            )

    # --- Selection ---
    def capture_current_selection(self) -> tuple[str, int] | None:
        try:
            current = self._tree.currentIndex()
        except Exception:
            logger.debug(
                "TreeStateService.capture_current_selection: failed to access current index",
                exc_info=True,
            )
            return None
        if current and current.isValid():
            return get_tree_tuple(current, 0)
        return None

    def restore_selection(self, selection: tuple[str, int]) -> None:
        if not selection:
            return
        item_type, item_id = selection
        if item_type not in ("section", "category"):
            return
        try:
            self._controller.selection_handler._restore_selection_after_load(
                item_type, item_id
            )
        except Exception:
            logger.exception(
                "TreeStateService.restore_selection: failed to restore selection %s #%s",
                item_type,
                item_id,
            )

    def select_first_item(self) -> None:
        try:
            self._controller.selection_handler._select_first_item_if_needed()
        except Exception:
            logger.debug(
                "TreeStateService.select_first_item: delegate failed",
                exc_info=True,
            )

    # --- Helper methods ---
    def _iter_indexes(self, parent: QModelIndex | None = None):
        if parent is None:
            parent = QModelIndex()
        rows = self._model.rowCount(parent)
        for row in range(rows):
            index = self._model.index(row, 0, parent)
            if index.isValid():
                yield index
                yield from self._iter_indexes(index)
