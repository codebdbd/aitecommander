from __future__ import annotations

import logging
import time
from typing import Final

from PyQt6.QtCore import QModelIndex, QObject, QTimer

from app.config_data.runtime_config import get_tree_quiet_first_selection
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
        self._deferred_select_first_pending = False

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
        t0 = time.perf_counter()
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
        # During tree snapshot apply, updates are disabled and setCurrentIndex can be
        # surprisingly expensive. Defer first selection to the next event-loop tick
        # so the tree becomes visible first, then apply selection/tiles.
        try:
            if hasattr(self._tree, "updatesEnabled") and not self._tree.updatesEnabled():
                if not self._deferred_select_first_pending:
                    self._deferred_select_first_pending = True

                    def _deferred() -> None:
                        self._deferred_select_first_pending = False
                        self.select_first_item_if_needed()

                    QTimer.singleShot(0, _deferred)
                logger.info(
                    "[Perf] SelectionWorkflow.select_first_item_if_needed deferred_while_tree_updates_disabled elapsed=%.2fms",
                    (time.perf_counter() - t0) * 1000.0,
                )
                return
        except Exception:
            logger.debug(
                "SelectionWorkflowService.select_first_item_if_needed: updatesEnabled probe failed",
                exc_info=True,
            )
        try:
            t_set0 = time.perf_counter()
            try:
                quiet_first_select = get_tree_quiet_first_selection(True)
            except Exception:
                quiet_first_select = True

            manual_handle_ms = 0.0
            if quiet_first_select:
                handler = self.parent()
                tree_signals_blocked = False
                sel_signals_blocked = False
                try:
                    try:
                        self._tree.blockSignals(True)
                        tree_signals_blocked = True
                    except Exception:
                        tree_signals_blocked = False
                    try:
                        selection_model.blockSignals(True)
                        sel_signals_blocked = True
                    except Exception:
                        sel_signals_blocked = False
                    selection_model.setCurrentIndex(
                        first_index, selection_model.SelectionFlag.ClearAndSelect
                    )
                finally:
                    try:
                        if sel_signals_blocked:
                            selection_model.blockSignals(False)
                    except Exception:
                        logger.debug(
                            "SelectionWorkflowService.select_first_item_if_needed: failed to unblock selection_model",
                            exc_info=True,
                        )
                    try:
                        if tree_signals_blocked:
                            self._tree.blockSignals(False)
                    except Exception:
                        logger.debug(
                            "SelectionWorkflowService.select_first_item_if_needed: failed to unblock tree signals",
                            exc_info=True,
                        )

                t_set1 = time.perf_counter()
                self._actions.focus_tree()
                t_focus1 = time.perf_counter()
                if handler is not None and hasattr(handler, "_handle_item_selection"):
                    t_handle0 = time.perf_counter()
                    try:
                        handler._handle_item_selection(first_index)  # type: ignore[attr-defined]
                    except Exception:
                        logger.debug(
                            "SelectionWorkflowService.select_first_item_if_needed: manual selection handling failed",
                            exc_info=True,
                        )
                    t_handle1 = time.perf_counter()
                    manual_handle_ms = (t_handle1 - t_handle0) * 1000.0
                    t_focus1 = t_handle1
                logger.info(
                    "[Perf] SelectionWorkflow.select_first_item_if_needed setCurrentIndex=%.2fms focus_tree=%.2fms manual_handle=%.2fms quiet=%s total=%.2fms",
                    (t_set1 - t_set0) * 1000.0,
                    max(0.0, (t_focus1 - t_set1) * 1000.0 - manual_handle_ms),
                    manual_handle_ms,
                    quiet_first_select,
                    (t_focus1 - t0) * 1000.0,
                )
            else:
                selection_model.setCurrentIndex(
                    first_index, selection_model.SelectionFlag.ClearAndSelect
                )
                t_set1 = time.perf_counter()
                self._actions.focus_tree()
                t_focus1 = time.perf_counter()
                logger.info(
                    "[Perf] SelectionWorkflow.select_first_item_if_needed setCurrentIndex=%.2fms focus_tree=%.2fms total=%.2fms",
                    (t_set1 - t_set0) * 1000.0,
                    (t_focus1 - t_set1) * 1000.0,
                    (t_focus1 - t0) * 1000.0,
                )
        except Exception:
            logger.debug(
                "SelectionWorkflowService.select_first_item_if_needed: setCurrentIndex or focus failed",
                exc_info=True,
            )

    def handle_item_selection(
        self, index: QModelIndex, last_handled: tuple[str, int] | None
    ) -> tuple[str, int] | None:
        t0 = time.perf_counter()
        self._actions.clear_table_selection()
        t1 = time.perf_counter()
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
                t_act0 = time.perf_counter()
                self._actions.refresh_tiles(item_id)
                t_act1 = time.perf_counter()
            elif item_type == "category":
                t_act0 = time.perf_counter()
                self._actions.load_category_via_ui_state(
                    item_id, source="SelectionHandling._handle_item_selection"
                )
                t_act1 = time.perf_counter()
            else:
                logger.warning("Unknown item type: %s", item_type)
                return last_handled

            logger.info(
                "[Perf] SelectionWorkflow.handle_item_selection type=%s id=%s clear_table=%.2fms action=%.2fms total=%.2fms",
                item_type,
                item_id,
                (t1 - t0) * 1000.0,
                (t_act1 - t_act0) * 1000.0,
                (t_act1 - t0) * 1000.0,
            )

            return (item_type, item_id)
        except Exception:
            logger.exception(
                "SelectionWorkflowService.handle_item_selection: unexpected error"
            )
            return last_handled

    def restore_selection_after_load(
        self, item_type: str, item_id: int
    ) -> QModelIndex | None:
        t0 = time.perf_counter()
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
        self._actions.focus_tree(use_scheduler=False)
        logger.info(
            "[Perf] SelectionWorkflow.restore_selection_after_load type=%s id=%s total=%.2fms",
            item_type,
            item_id,
            (time.perf_counter() - t0) * 1000.0,
        )
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
        self._actions.focus_tree(use_scheduler=False)
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
        self._actions.focus_tree(use_scheduler=False)
        return index
