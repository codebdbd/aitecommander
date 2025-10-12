from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QModelIndex, QObject

from app.controllers.ui.state.task_scheduler import (
    schedule_focus,
    schedule_selection_restore,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from .tree_management import TreeManagement


class TreeUpdateService(QObject):
    """Encapsulates insert/update/delete operations for tree items."""

    def __init__(self, manager: TreeManagement, tree, model) -> None:
        parent = manager if isinstance(manager, QObject) else None
        super().__init__(parent=parent)
        self._manager = manager
        self._tree = tree
        self._model = model

    # --- Public API -----------------------------------------------------
    def handle_item_added(self, item_type: str, parent_id: int, data: dict[str, Any]) -> None:
        if item_type == "section":
            self._insert_section(data)
        elif item_type == "category":
            self._insert_category(parent_id, data)
        else:
            return
        self._focus_on_new_item(item_type, data.get("id"))

    def handle_item_updated(self, item_type: str, item_id: int, data: dict[str, Any]) -> None:
        try:
            self._model.update_item(item_type, item_id, data or {})
        except (ValueError, RuntimeError):
            logger.exception(
                "TreeUpdateService.handle_item_updated: model update failed for %s #%s",
                item_type,
                item_id,
            )
            raise
        if item_type == "category" and isinstance(item_id, int):
            schedule_selection_restore(
                lambda: self._manager.controller.selection_handler._restore_category_selection(  # noqa: SLF001
                    item_id
                ),
                f"restore_cat_{item_id}",
            )
            self._schedule_focus()

    def handle_item_deleted(self, item_type: str, item_id: int) -> None:
        try:
            if item_type == "section":
                self._model.remove_sections([int(item_id)])
            elif item_type == "category":
                self._model.remove_categories([int(item_id)])
        except Exception:
            logger.exception(
                "TreeUpdateService.handle_item_deleted: remove failed for %s #%s",
                item_type,
                item_id,
            )
        finally:
            self._post_delete_updates(item_type, item_id)
            self._schedule_focus()

    # --- Helpers --------------------------------------------------------
    def _insert_section(self, data: dict[str, Any]) -> None:
        row = data.get("row")
        row_index = int(row) if isinstance(row, int) else -1
        try:
            self._model.insert_sections(row_index, [data])
        except (ValueError, RuntimeError):
            logger.exception(
                "TreeUpdateService._insert_section: model insert failed"
            )
            raise

    def _insert_category(self, parent_id: int, data: dict[str, Any]) -> None:
        row = data.get("row")
        row_index = int(row) if isinstance(row, int) else -1
        try:
            self._model.insert_categories(parent_id, row_index, [data])
        except (ValueError, RuntimeError):
            logger.exception(
                "TreeUpdateService._insert_category: model insert failed"
            )
            raise
        if not bool(data.get("__from_undo__")):
            self._manager.refresh_section_tiles(parent_id)

    def _focus_on_new_item(self, item_type: str, item_id: Any) -> None:
        if not isinstance(item_id, int):
            return
        selection_handler = self._manager.controller.selection_handler
        schedule_selection_restore(
            lambda: selection_handler._set_focus_on_new_item_by_id(item_type, item_id),  # noqa: SLF001
            f"new_{item_type}_{item_id}",
        )
        self._schedule_focus()

    def _schedule_focus(self) -> None:
        try:
            schedule_focus(lambda: self._tree.setFocus(), "structure_tree")
        except Exception:
            logger.debug(
                "TreeUpdateService._schedule_focus: schedule_focus failed",
                exc_info=True,
            )

    def _post_delete_updates(self, item_type: str, item_id: int) -> None:
        if item_type == "category":
            try:
                self._manager.refresh_tiles_for_current_selection()
            except Exception:
                logger.exception(
                    "TreeUpdateService._post_delete_updates: tiles refresh after category delete failed"
                )
        elif item_type == "section":
            try:
                model = self._tree.model()
                if model and hasattr(model, "rowCount"):
                    if int(model.rowCount(QModelIndex())) == 0:
                        self._manager.clear_tiles()
                    else:
                        self._manager.refresh_tiles_for_current_selection()
            except Exception:
                logger.exception(
                    "TreeUpdateService._post_delete_updates: tiles refresh after section delete failed"
                )
