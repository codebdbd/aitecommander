from __future__ import annotations

import logging
from collections.abc import Iterable

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QObject

from app.controllers.ui.dialogs import DialogManager
from app.controllers.ui.undo.commands_structure import (
    BatchDeleteCategoriesCmd,
    DeleteCategoryCmd,
    DeleteSectionCmd,
    DeleteSectionsCmd,
)
from app.utils.ui.qt.roles import get_tree_tuple

logger = logging.getLogger(__name__)

_DELETION_CONTEXT = "StructureDeletion"
_BATCH_DELETE_MESSAGE = QT_TRANSLATE_NOOP(
    _DELETION_CONTEXT,
    "{categories} categor(y/ies) and {links} link(s) will be deleted in total.\n\n"
    "All nested links will be permanently deleted!\n\n"
    "Are you sure you want to continue?",
)
_SECTION_DELETE_MESSAGE = QT_TRANSLATE_NOOP(
    _DELETION_CONTEXT,
    "Section '{section}' contains {categories} categor(y/ies) and {links} link(s).\n\n"
    "All nested categories and links will be permanently deleted!\n\n"
    "Are you sure you want to continue?",
)
_SECTIONS_DELETE_MESSAGE = QT_TRANSLATE_NOOP(
    _DELETION_CONTEXT,
    "Selected sections contain {categories} categor(y/ies) and {links} link(s) in total.\n\n"
    "All nested categories and links will be permanently deleted!\n\n"
    "Are you sure you want to continue?",
)
_CATEGORY_DELETE_MESSAGE = QT_TRANSLATE_NOOP(
    _DELETION_CONTEXT,
    "Category '{category}' contains {links} link(s).\n\n"
    "All nested links will be permanently deleted!\n\n"
    "Are you sure you want to continue?",
)
_CONFIRM_DELETION_TITLE = QT_TRANSLATE_NOOP(_DELETION_CONTEXT, "Confirm deletion")
_DELETE_SECTION_TITLE = QT_TRANSLATE_NOOP(_DELETION_CONTEXT, "Delete section")
_DELETE_SECTION_INFO = QT_TRANSLATE_NOOP(
    _DELETION_CONTEXT,
    "This action is irreversible. All nested categories and links will be deleted.",
)
_DELETE_CATEGORY_INFO = QT_TRANSLATE_NOOP(
    _DELETION_CONTEXT,
    "This action is irreversible. All links in the category will be deleted.",
)


def _tr_deletion(text: str) -> str:
    return QCoreApplication.translate(_DELETION_CONTEXT, text)


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
            if self._delete_multiple_sections(selected_indexes):
                return
            if self._delete_multiple_categories(selected_indexes):
                return
        current = self._current_tree_index()
        if current and current.isValid():
            self.delete_item(current)

    def handle_delete_category(self, category_id: int) -> None:
        try:
            cid = int(category_id)
        except Exception:
            return
        if cid <= 0:
            return
        self._delete_category(cid)

    def handle_delete_categories(self, category_ids: Iterable[int]) -> None:
        """Delete multiple categories by IDs with a single confirmation dialog."""
        ids: list[int] = []
        seen: set[int] = set()
        for raw in category_ids or []:
            try:
                cid = int(raw)
            except Exception:
                continue
            if cid <= 0 or cid in seen:
                continue
            seen.add(cid)
            ids.append(cid)
        if not ids:
            return
        if len(ids) == 1:
            self.handle_delete_category(ids[0])
            return
        totals = self._count_links_for_categories(ids)
        if totals == 0:
            self._delete_categories_without_confirmation(ids)
            return
        message = _tr_deletion(_BATCH_DELETE_MESSAGE).format(
            categories=len(ids), links=totals
        )
        if DialogManager.ask_confirmation(
            self._main,
            message,
            _tr_deletion(_CONFIRM_DELETION_TITLE),
        ):
            self._delete_categories_without_confirmation(ids)
        # cancel = handled, no fallback here

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
        message = _tr_deletion(_BATCH_DELETE_MESSAGE).format(
            categories=len(category_ids), links=totals
        )
        if DialogManager.ask_confirmation(
            self._main,
            message,
            _tr_deletion(_CONFIRM_DELETION_TITLE),
        ):
            self._delete_categories_without_confirmation(category_ids)
            return True
        # User explicitly cancelled the batch delete; treat as handled
        # so caller does not fall back to single-item deletion and show
        # a second confirmation dialog.
        return True

    def _delete_multiple_sections(self, indexes: Iterable) -> bool:
        section_ids = []
        for index in indexes:
            meta = get_tree_tuple(index, 0)
            if meta and meta[0] == "section" and isinstance(meta[1], int):
                section_ids.append(meta[1])
        if len(section_ids) < 2:
            return False
        total_categories = 0
        total_links = 0
        for section_id in section_ids:
            cats_count, links_count = self._count_nested_objects(section_id)
            total_categories += int(cats_count)
            total_links += int(links_count)
        message = _tr_deletion(_SECTIONS_DELETE_MESSAGE).format(
            categories=total_categories, links=total_links
        )
        if not DialogManager.ask_confirmation(
            self._main,
            message,
            _tr_deletion(_DELETE_SECTION_TITLE),
            informative_text=_tr_deletion(_DELETE_SECTION_INFO),
            details=f"sections={len(section_ids)}, cats={total_categories}, links={total_links}",
        ):
            return True
        sections_payload = [
            self._business.get_section_data(section_id)
            for section_id in section_ids
        ]
        sections_payload = [s for s in sections_payload if s]
        if not sections_payload:
            return True
        cmd = DeleteSectionsCmd(
            sections_payload,
            self._main,
            business=self._business,
            undo_manager=self._undo_stack,
        )
        logger.debug(
            "[BatchDeleteSections] queued sections=%s", len(sections_payload)
        )
        self._undo_stack.push(cmd)
        return True

    def _delete_categories_without_confirmation(
        self, category_ids: Iterable[int]
    ) -> None:
        try:
            categories_payload = [
                self._business.get_category_data(cid) for cid in category_ids
            ]
            categories_payload = [c for c in categories_payload if c]
            if not categories_payload:
                return
            cmd = BatchDeleteCategoriesCmd(
                categories_payload,
                self._main,
                business=self._business,
                undo_manager=self._undo_stack,
            )
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
            return self._business.db.sections.count_nested_objects_for_section(
                section_id
            )
        except Exception:  # pragma: no cover - stats not critical
            categories = self._business.get_categories(section_id) or []
            return len(categories), 0

    def _count_links_for_category(self, category_id: int) -> int:
        try:
            return int(
                self._business.db.links.count_links_by_category(category_id)
            )
        except Exception:  # pragma: no cover - stats not critical
            return 0

    def _count_links_for_categories(self, category_ids: Iterable[int]) -> int:
        try:
            counts_map = self._business.db.links.count_links_by_categories(
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
        message = _tr_deletion(_SECTION_DELETE_MESSAGE).format(
            section=section_name,
            categories=cats_count,
            links=links_count,
        )
        return DialogManager.ask_confirmation(
            self._main,
            message,
            _tr_deletion(_DELETE_SECTION_TITLE),
            informative_text=_tr_deletion(_DELETE_SECTION_INFO),
            details=f"section_id={section_data.get('id')}, cats={cats_count}, links={links_count}",
        )

    def _confirm_category_deletion(self, category_data: dict, links_count: int) -> bool:
        category_name = category_data.get("name", "unknown category")
        message = _tr_deletion(_CATEGORY_DELETE_MESSAGE).format(
            category=category_name, links=links_count
        )
        return DialogManager.ask_confirmation(
            self._main,
            message,
            _tr_deletion(_CONFIRM_DELETION_TITLE),
            informative_text=_tr_deletion(_DELETE_CATEGORY_INFO),
            details=f"category_id={category_data.get('id')}, links={links_count}",
        )

    # ------------- Direct operations of undo commands -------------
    def _push_section_delete(self, section_data: dict) -> None:
        try:
            cmd = DeleteSectionCmd(
                section_data,
                self._main,
                business=self._business,
                undo_manager=self._undo_stack,
            )
            if cmd:
                self._undo_stack.push(cmd)
        except Exception:  # pragma: no cover - UI protection
            logger.exception("Section deletion error")

    def _push_category_delete(self, category_data: dict) -> None:
        try:
            cmd = DeleteCategoryCmd(
                category_data,
                self._main,
                business=self._business,
                undo_manager=self._undo_stack,
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
