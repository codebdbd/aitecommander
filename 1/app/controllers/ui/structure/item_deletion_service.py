from __future__ import annotations

import logging
from collections.abc import Iterable

from PyQt6.QtCore import QObject

from app.controllers.ui.dialogs import DialogManager
from app.controllers.ui.undo.commands_structure import (
    DeleteCategoriesBatchCmd,
    DeleteCategoryCmd,
    DeleteSectionCmd,
)
from app.utils.ui.qt.roles import get_tree_tuple

logger = logging.getLogger(__name__)


class ItemDeletionService(QObject):
    """Encapsulates deletion scenarios for sections and categories."""

    def __init__(self, *, controller, tree, business, main_window, undo_stack):
        parent = controller if isinstance(controller, QObject) else None
        super().__init__(parent=parent)
        self._controller = controller
        self._tree = tree
        self._business = business
        self._main = main_window
        self._undo_stack = undo_stack

    # ------------- Public scenarios -------------
    def delete_item(self, item) -> None:
        if not item:
            return
        meta = get_tree_tuple(item, 0)
        if not meta:
            return
        item_type, item_id = meta
        if item_type == "section":
            self._delete_section(item_id)
        elif item_type == "category":
            self._delete_category(item_id)

    def delete_selected_item(self) -> None:
        selected_indexes = self._selected_tree_indexes()
        if selected_indexes and len(selected_indexes) > 1:
            if self._delete_multiple_categories(selected_indexes):
                return
        current = self._current_tree_index()
        if current and current.isValid():
            self.delete_item(current)

    def handle_delete_category(self, category_id: int) -> None:
        item = self._controller.tree_manager._find_item_by_id("category", category_id)
        if item:
            self.delete_item(item)

    # ------------- Helper methods -------------
    def _delete_multiple_categories(self, indexes: Iterable) -> bool:
        category_ids = []
        for index in indexes:
            meta = get_tree_tuple(index, 0)
            if meta and meta[0] == "category" and isinstance(meta[1], int):
                category_ids.append(meta[1])
        if not category_ids:
            return False
        totals = self._count_links_for_categories(category_ids)
        if totals == 0:
            self._delete_categories_without_confirmation(category_ids)
            return True
        message = (
            f"{len(category_ids)} categor(y/ies) and {totals} link(s) will be deleted in total.\n\n"
            "All nested links will be permanently deleted!\n\n"
            "Are you sure you want to continue?"
        )
        if DialogManager.ask_confirmation(
            self._main,
            message,
            "Confirm deletion",
        ):
            self._delete_categories_without_confirmation(category_ids)
            return True
        return False

    def _delete_categories_without_confirmation(
        self, category_ids: Iterable[int]
    ) -> None:
        try:
            categories_payload = [
                self._business.get_category_data(cid) for cid in category_ids
            ]
            categories_payload = [c for c in categories_payload if c]
            if categories_payload:
                cmd = DeleteCategoriesBatchCmd(categories_payload, self._main)
                self._undo_stack.push(cmd)
        except Exception:  # pragma: no cover - UI protection
            logger.exception("Batch category deletion error")

    def _delete_section(self, section_id: int) -> None:
        section_data = self._business.get_section_data(section_id)
        if not section_data:
            return
        cats_count, links_count = self._count_nested_objects(section_id)
        if links_count == 0:
            self._push_section_delete(section_data)
            return
        if self._confirm_section_deletion(section_data, cats_count, links_count):
            self._push_section_delete(section_data)

    def _delete_category(self, category_id: int) -> None:
        category_data = self._business.get_category_data(category_id)
        if not category_data:
            return
        links_count = self._count_links_for_category(category_id)
        if links_count == 0:
            self._push_category_delete(category_data)
            return
        if self._confirm_category_deletion(category_data, links_count):
            self._push_category_delete(category_data)

    # ------------- Counters -------------
    def _count_nested_objects(self, section_id: int) -> tuple[int, int]:
        try:
            return self._business.structure_model.count_nested_objects_for_section(
                section_id
            )
        except Exception:  # pragma: no cover - stats not critical
            categories = self._business.get_categories(section_id) or []
            return len(categories), 0

    def _count_links_for_category(self, category_id: int) -> int:
        try:
            return int(
                self._business.structure_model.count_links_by_category(category_id)
            )
        except Exception:  # pragma: no cover - stats not critical
            return 0

    def _count_links_for_categories(self, category_ids: Iterable[int]) -> int:
        try:
            counts_map = self._business.structure_model.count_links_by_categories(
                category_ids
            )
        except Exception:  # pragma: no cover - stats not critical
            counts_map = {}
        return sum(int(value) for value in (counts_map or {}).values())

    # ------------- Confirmations -------------
    def _confirm_section_deletion(
        self, section_data: dict, cats_count: int, links_count: int
    ) -> bool:
        section_name = section_data.get("name", "unknown section")
        message = (
            f"Section '{section_name}' contains {cats_count} categor"
            f"{'y' if cats_count == 1 else 'ies'} and {links_count} link"
            f"{'s' if links_count != 1 else ''}.\n\n"
            "All nested categories and links will be permanently deleted!\n\n"
            "Are you sure you want to continue?"
        )
        return DialogManager.ask_confirmation(
            self._main,
            message,
            "Delete section",
            informative_text="This action is irreversible. All nested categories and links will be deleted.",
            details=f"section_id={section_data.get('id')}, cats={cats_count}, links={links_count}",
        )

    def _confirm_category_deletion(self, category_data: dict, links_count: int) -> bool:
        category_name = category_data.get("name", "unknown category")
        message = (
            f"Category '{category_name}' contains {links_count} link"
            f"{'s' if links_count != 1 else ''}.\n\n"
            "All nested links will be permanently deleted!\n\n"
            "Are you sure you want to continue?"
        )
        return DialogManager.ask_confirmation(
            self._main,
            message,
            "Confirm deletion",
            informative_text="This action is irreversible. All links in the category will be deleted.",
            details=f"category_id={category_data.get('id')}, links={links_count}",
        )

    # ------------- Direct operations of undo commands -------------
    def _push_section_delete(self, section_data: dict) -> None:
        try:
            cmd = DeleteSectionCmd(section_data, self._main)
            if cmd:
                self._undo_stack.push(cmd)
        except Exception:  # pragma: no cover - UI protection
            logger.exception("Section deletion error")

    def _push_category_delete(self, category_data: dict) -> None:
        try:
            cmd = DeleteCategoryCmd(
                category_data,
                self._main,
                skip_reload=False,
                lightweight_reload=True,
            )
            if cmd:
                self._undo_stack.push(cmd)
        except Exception:  # pragma: no cover - UI protection
            logger.exception("Category deletion error")

    # ------------- Helpers -------------
    def _selected_tree_indexes(self) -> list:
        try:
            if hasattr(self._tree, "selectionModel"):
                selection_model = self._tree.selectionModel()
                if selection_model:
                    return selection_model.selectedRows(0) or []
        except (AttributeError, RuntimeError) as exc:
            logger.debug(
                "[ItemDeletionService._selected_tree_indexes] selectionModel failed: %s",
                exc,
            )
        return []

    def _current_tree_index(self):
        try:
            return (
                self._tree.currentIndex()
                if hasattr(self._tree, "currentIndex")
                else None
            )
        except (AttributeError, RuntimeError) as exc:
            logger.debug(
                "[ItemDeletionService._current_tree_index] currentIndex failed: %s",
                exc,
            )
            return None
