# app/controllers/structure/selection_handling.py
import logging
from typing import Optional

from PyQt6.QtCore import QModelIndex, QObject, pyqtSlot

from app.controllers.ui.types import (
    CategoryTilesControllerProtocol,
)
from app.utils.db.synchronization import signal_guard
from app.utils.ui.qt.roles import get_tree_tuple

from .selection_actions import SelectionActions
from .selection_workflow_service import SelectionWorkflowService

# Use string literals "section" and "category"

logger = logging.getLogger(__name__)


class SelectionHandling(QObject):
    def __init__(self, controller, category_tiles_controller=None):
        parent = controller if isinstance(controller, QObject) else None
        super().__init__(parent=parent)
        self.controller = controller
        self.tree = controller.tree
        self.main = controller.main
        self.business = controller.business
        if category_tiles_controller is None:
            raise ValueError(
                "SelectionHandling requires a category_tiles_controller dependency"
            )
        if not isinstance(
            category_tiles_controller, CategoryTilesControllerProtocol
        ):
            raise TypeError(
                "category_tiles_controller must implement CategoryTilesControllerProtocol"
            )
        self.tiles_controller: CategoryTilesControllerProtocol = category_tiles_controller
        self._last_handled: Optional[tuple[str, int]] = None
        self._suppress_counter = 0
        self._actions = SelectionActions(
            controller=controller,
            tree=self.tree,
            tiles_controller=self.tiles_controller,
            main_window=self.main,
        )
        self._workflow = SelectionWorkflowService(
            handler=self, tree=self.tree, actions=self._actions
        )

    # --- Централизованное подавление обработки выбора ---
    def begin_suppress_selection(self) -> None:
        try:
            self._suppress_counter += 1
            logger.debug(
                "Selection handling suppressed (level=%s)", self._suppress_counter
            )
        except Exception:
            logger.debug(
                "SelectionHandling.begin_suppress_selection: failed to update counter",
                exc_info=True,
            )
            self._suppress_counter = max(1, getattr(self, "_suppress_counter", 0))

    def end_suppress_selection(self) -> None:
        try:
            self._suppress_counter = max(0, self._suppress_counter - 1)
            logger.debug(
                "Selection handling resumed (level=%s)", self._suppress_counter
            )
        except Exception:
            logger.debug(
                "SelectionHandling.end_suppress_selection: failed to update counter",
                exc_info=True,
            )
            self._suppress_counter = 0

    def is_suppressed(self) -> bool:
        return bool(self._suppress_counter > 0)

    @pyqtSlot(int)
    def _on_section_selected(self, section_id: int) -> None:
        self._actions.refresh_tiles(section_id)

    @pyqtSlot(int)
    def _on_category_selected(self, category_id: int) -> None:
        self._actions.load_category_via_ui_state(
            category_id, source="SelectionHandling._on_category_selected"
        )

    @pyqtSlot(str, str)
    def _on_error_occurred(self, title: str, message: str) -> None:
        from app.controllers.ui.dialogs import DialogManager

        DialogManager.show_warning(
            self.main,
            title or "Warning",
            message,
            informative_text="Check the correctness of actions and try again.",
        )

    def _select_first_item_if_needed(self) -> None:
        self._workflow.select_first_item_if_needed()

    @pyqtSlot(QModelIndex, QModelIndex)
    @signal_guard()
    def _on_current_changed(self, current: QModelIndex, _prev: QModelIndex) -> None:
        if self.is_suppressed():
            logger.debug("Selection changed while suppressed - ignoring event")
            return
        if not current or not current.isValid():
            logger.debug(
                "Selection changed to None - skip clearing tiles during reload"
            )
            return
        try:
            meta = get_tree_tuple(current, 0)
            if meta:
                item_type, item_id = meta
                logger.debug("Selection changed to %s #%s", item_type, item_id)
            else:
                logger.debug("Selection changed to item without data")
        except Exception as exc:
            logger.warning(
                "Could not get item data for logging: %s", exc, exc_info=True
            )
        self._handle_item_selection(current)

    @pyqtSlot(QModelIndex, int)
    def _on_single_click(self, index: QModelIndex, _col: int = 0) -> None:
        try:
            current = self.tree.currentIndex()
        except Exception:
            current = QModelIndex()
        if index == current:
            return
        self._handle_item_selection(index)

    @pyqtSlot(QModelIndex)
    @signal_guard()
    def _handle_item_selection(self, index: QModelIndex) -> None:
        if self.is_suppressed():
            logger.debug("Handle selection while suppressed - skip")
            return
        result = self._workflow.handle_item_selection(index, self._last_handled)
        if result:
            self._last_handled = result

    def _restore_selection_after_load(self, item_type: str, item_id: int) -> None:
        index = self._workflow.restore_selection_after_load(item_type, item_id)
        if index:
            self._handle_item_selection(index)

    def _set_focus_on_new_item_by_id(self, item_type: str, item_id: int) -> None:
        self._workflow.set_focus_on_new_item_by_id(item_type, item_id)

    def _select_category_without_stack_switch(self, category_id: int) -> None:
        self._actions.reload_links_without_stack_switch(category_id)

    def _restore_category_selection(self, category_id: int) -> None:
        index = self._workflow.restore_category_selection(category_id)
        if index:
            self._handle_item_selection(index)
