from __future__ import annotations

import logging

from typing import Final

from PyQt6.QtCore import QModelIndex, QObject

from app.utils.ui.qt.roles import get_tree_tuple
from app.views.widgets.protocols import (
    SelectionModelProtocol,
    StructureActionsProtocol,
    StructureTreeModelProtocol,
    StructureTreeViewProtocol,
)

logger = logging.getLogger(__name__)


class SelectionWorkflowService(QObject):
    """Encapsulates complex selection workflows for the structure tree."""

    def __init__(
        self,
        *,
        handler: QObject | None,
        tree: StructureTreeViewProtocol,
        actions: StructureActionsProtocol,
    ) -> None:
        parent = handler if isinstance(handler, QObject) else None
        super().__init__(parent=parent)
        self._tree: Final[StructureTreeViewProtocol] = tree
        self._actions: Final[StructureActionsProtocol] = actions

    # ------------------------------------------------------------------
    # Helper access methods
    def _get_model_and_selection(
        self,
    ) -> tuple[StructureTreeModelProtocol | None, SelectionModelProtocol | None]:
        try:
            model = self._tree.model()
            selection_model = self._tree.selectionModel()
        except Exception:
            logger.debug(
                "SelectionWorkflowService: failed to access tree model/selection",
                exc_info=True,
            )
            return None, None
        return model, selection_model

    @staticmethod
    def _is_valid_index(index: QModelIndex | None) -> bool:
        return bool(index and index.isValid())

    # ------------------------------------------------------------------
    # Public API for SelectionHandling
    def select_first_item_if_needed(self) -> None:
        model, selection_model = self._get_model_and_selection()
        if model is None or selection_model is None:
            return
        try:
            has_selection = selection_model.hasSelection()
        except Exception:
            logger.debug(
                "SelectionWorkflowService.select_first_item_if_needed: hasSelection failed",
                exc_info=True,
            )
            has_selection = True
        if has_selection:
            return
        try:
            if model.rowCount() <= 0:
                return
            first_index = model.index(0, 0)
        except Exception:
            logger.debug(
                "SelectionWorkflowService.select_first_item_if_needed: failed to obtain first index",
                exc_info=True,
            )
            return
        if not self._is_valid_index(first_index):
            return
        try:
            selection_model.setCurrentIndex(
                first_index, selection_model.SelectionFlag.ClearAndSelect
            )
            self._actions.focus_tree()
        except Exception:
            logger.debug(
                "SelectionWorkflowService.select_first_item_if_needed: setCurrentIndex or focus failed",
                exc_info=True,
            )

    def handle_item_selection(
        self, index: QModelIndex, last_handled: tuple[str, int] | None
    ) -> tuple[str, int] | None:
        self._actions.clear_table_selection()
        try:
            meta = get_tree_tuple(index, 0)
            if not meta:
                logger.warning("Invalid item data: None")
                return last_handled

            item_type, item_id = meta
            if item_type not in ("section", "category") or not isinstance(item_id, int):
                logger.warning(
                    "Invalid item data types for selection: %s, %s", item_type, item_id
                )
                return last_handled

            if last_handled == (item_type, item_id):
                logger.debug(
                    "Skip duplicate selection handling for %s #%s", item_type, item_id
                )
                return last_handled
            logger.info("Handling selection: %s #%s", item_type, item_id)

            if item_type == "section":
                self._actions.refresh_tiles(item_id)
            elif item_type == "category":
                self._actions.load_category_via_ui_state(
                    item_id, source="SelectionHandling._handle_item_selection"
                )
            else:
                logger.warning("Unknown item type: %s", item_type)
                return last_handled

            return (item_type, item_id)
        except Exception:
            logger.exception(
                "SelectionWorkflowService.handle_item_selection: unexpected error"
            )
            return last_handled

    def restore_selection_after_load(
        self, item_type: str, item_id: int
    ) -> QModelIndex | None:
        model, selection_model = self._get_model_and_selection()
        if model is None or selection_model is None:
            return None
        try:
            index = model.index_for(item_type, item_id)
        except Exception:
            logger.debug(
                "SelectionWorkflowService.restore_selection_after_load: index_for failed",
                exc_info=True,
            )
            return None
        if not self._is_valid_index(index):
            return None
        assert index is not None
        try:
            self._tree.blockSignals(True)
            selection_model.setCurrentIndex(
                index, selection_model.SelectionFlag.ClearAndSelect
            )
            self._tree.scrollTo(index)
        finally:
            self._tree.blockSignals(False)
        return index

    def set_focus_on_new_item_by_id(
        self, item_type: str, item_id: int
    ) -> QModelIndex | None:
        model, selection_model = self._get_model_and_selection()
        if model is None or selection_model is None:
            return None
        try:
            index = model.index_for(item_type, item_id)
        except Exception:
            logger.debug(
                "SelectionWorkflowService.set_focus_on_new_item_by_id: index_for failed",
                exc_info=True,
            )
            return None
        if not self._is_valid_index(index):
            return None
        assert index is not None
        selection_model.setCurrentIndex(
            index, selection_model.SelectionFlag.ClearAndSelect
        )
        self._tree.scrollTo(index)
        self._actions.focus_tree()
        if item_type == "category":
            self._actions.load_category_via_ui_state(
                item_id, source="SelectionHandling._handle_item_selection"
            )
        return index

    def restore_category_selection(self, category_id: int) -> QModelIndex | None:
        model, selection_model = self._get_model_and_selection()
        if model is None or selection_model is None:
            return None
        try:
            index = model.index_for("category", category_id)
        except Exception:
            logger.debug(
                "SelectionWorkflowService.restore_category_selection: index_for failed",
                exc_info=True,
            )
            return None
        if not self._is_valid_index(index):
            return None
        assert index is not None
        try:
            self._tree.blockSignals(True)
            selection_model.setCurrentIndex(
                index, selection_model.SelectionFlag.ClearAndSelect
            )
            self._tree.scrollTo(index)
        finally:
            self._tree.blockSignals(False)
        self._actions.focus_tree()
        return index
