# app/controllers/ui/structure/item_operations.py

from __future__ import annotations

import logging
import time

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QObject, pyqtSlot

from app.controllers.ui.dialogs.dialog_manager import DialogManager
from app.controllers.ui.structure.item_deletion_service import ItemDeletionService
from app.controllers.ui.structure.item_dialogs_service import ItemDialogService
from app.utils.ui.focus import get_focus_manager

logger = logging.getLogger(__name__)

_ITEM_OPS_CONTEXT = "ItemOperations"
_IO_DELETE_SECTION_MSG = QT_TRANSLATE_NOOP(
    _ITEM_OPS_CONTEXT,
    "Section '{section}' contains {categories} categor(y/ies) and {links} link(s).\n\n"
    "All nested categories and links will be permanently deleted!\n\n"
    "Are you sure you want to continue?",
)
_IO_DELETE_CATEGORY_MSG = QT_TRANSLATE_NOOP(
    _ITEM_OPS_CONTEXT,
    "Category '{category}' contains {links} link(s).\n\n"
    "All nested links will be permanently deleted!\n\n"
    "Are you sure you want to continue?",
)
_IO_TITLE_DELETE_SECTION = QT_TRANSLATE_NOOP(
    _ITEM_OPS_CONTEXT, "Delete section"
)
_IO_TITLE_CONFIRM_DELETE = QT_TRANSLATE_NOOP(
    _ITEM_OPS_CONTEXT, "Confirm deletion"
)
_IO_INFO_DELETE_SECTION = QT_TRANSLATE_NOOP(
    _ITEM_OPS_CONTEXT,
    "This action is irreversible. All nested categories and links will be deleted.",
)
_IO_INFO_DELETE_CATEGORY = QT_TRANSLATE_NOOP(
    _ITEM_OPS_CONTEXT,
    "This action is irreversible. All links in the category will be deleted.",
)


def _tr_item_ops(text: str) -> str:
    return QCoreApplication.translate(_ITEM_OPS_CONTEXT, text)

class ItemOperations(QObject):
    def __init__(self, controller):
        parent = controller if isinstance(controller, QObject) else None
        super().__init__(parent=parent)
        self.controller = controller
        self.tree = controller.tree
        self.business = controller.business
        self.main = controller.main
        self.undo_stack = controller.undo_stack
        self._dialogs = ItemDialogService(
            controller=controller,
            tree=self.tree,
            business=self.business,
            main_window=self.main,
            undo_stack=self.undo_stack,
        )
        self._deleter = ItemDeletionService(
            controller=controller,
            tree=self.tree,
            business=self.business,
            main_window=self.main,
            undo_stack=self.undo_stack,
        )

    @pyqtSlot(object)
    def load(self, item_to_select=None) -> None:
        # On structure load, tree_management will automatically save and restore selection
        # if item_to_select is not provided; otherwise the specified selection will be restored
        try:
            self.business.async_service.schedule_structure_reload()
        except Exception as exc:
            logger.warning(
                "[ItemOperations.load] schedule_structure_reload failed: %s",
                exc,
                exc_info=True,
            )
        if item_to_select:
            from app.controllers.ui.state.task_scheduler import (
                schedule_selection_restore,
            )

            item_type, item_id = item_to_select
            # Restore selection after load with a small delay
            schedule_selection_restore(
                lambda: self.controller.selection_handler._restore_selection_after_load(
                    item_type, item_id
                ),
                f"{item_type}_{item_id}",
            )
            # Restore focus to the tree
            try:
                manager = get_focus_manager()
                manager.set_focus(
                    self.tree, widget_name="structure_tree", origin="user_action"
                )
            except Exception as e:
                logger.debug("[ItemOperations.load] set_focus failed: %s", e)

    @pyqtSlot(int)
    def switch_sphere(self, sphere_id: int) -> None:
        """Switch sphere and reload structure.

        Best practice: only async loading via handler
        business.active_sphere_changed, without duplicates or sync fallbacks.
        """
        # Do nothing if sphere doesn't change (e.g., double-click same sphere)
        try:
            current = getattr(self.business, "current_sphere_id", None)
            if isinstance(current, int) and current == int(sphere_id):
                logger.debug(
                    "switch_sphere: same sphere %s selected again; skip clearing and reload",
                    sphere_id,
                )
                return
        except Exception:
            pass

        try:
            if hasattr(self.main, "__dict__"):
                self.main._sphere_switch_started_ms = time.monotonic()
        except Exception:
            pass

        self.business.set_current_sphere(sphere_id)
        # Do not clear the model immediately: wait for structure_loaded to avoid empty tree
        # and artifacts on double clicks/fast switching.
        # Further loading is initiated by business.on_active_sphere_changed handler,
        # which calls load_structure_async(). Nothing else to do here.
        return

    @pyqtSlot()
    def add_new_section(self) -> None:
        self._dialogs.add_new_section()

    @pyqtSlot()
    def add_new_category(self) -> None:
        target_section_id = self._dialogs.ensure_section_for_category()
        if target_section_id is None:
            return
        self._dialogs.add_new_category(target_section_id)

    def edit_item(self, item) -> None:
        self._dialogs.edit_item(item)

    @pyqtSlot()
    def edit_selected_item(self) -> None:
        self._dialogs.edit_selected_item()

    def delete_item(self, item) -> None:
        if self._is_delete_suppressed():
            return
        self._deleter.delete_item(item)

    @pyqtSlot()
    def delete_selected_item(self) -> None:
        if self._is_delete_suppressed():
            return
        self._deleter.delete_selected_item()

    def _is_delete_suppressed(self) -> bool:
        try:
            if hasattr(self.main, "_suppress_deletes") and self.main._suppress_deletes:
                logger.debug(
                    "[DeleteGuard] deletion suppressed by _suppress_deletes flag"
                )
                return True
        except Exception as exc:
            logger.debug(
                "[ItemOperations._is_delete_suppressed] flag check failed: %s", exc
            )
        return False

    def _confirm_section_deletion(
        self, section_data: dict, cats_count: int, links_count: int
    ) -> bool:
        section_name = section_data.get("name", "unknown section")
        msg = _tr_item_ops(_IO_DELETE_SECTION_MSG).format(
            section=section_name,
            categories=cats_count,
            links=links_count,
        )
        return DialogManager.ask_confirmation(
            self.main,
            msg,
            _tr_item_ops(_IO_TITLE_DELETE_SECTION),
            informative_text=_tr_item_ops(_IO_INFO_DELETE_SECTION),
            details=f"section_id={section_data.get('id')}, cats={cats_count}, links={links_count}",
        )

    def _confirm_category_deletion(self, category_data: dict, links_count: int) -> bool:
        category_name = category_data.get("name", "unknown category")
        msg = _tr_item_ops(_IO_DELETE_CATEGORY_MSG).format(
            category=category_name, links=links_count
        )
        return DialogManager.ask_confirmation(
            self.main,
            msg,
            _tr_item_ops(_IO_TITLE_CONFIRM_DELETE),
            informative_text=_tr_item_ops(_IO_INFO_DELETE_CATEGORY),
            details=f"category_id={category_data.get('id')}, links={links_count}",
        )

    def handle_edit_category(self, category_id: int) -> None:
        self._dialogs.handle_edit_category(category_id)

    def handle_delete_category(self, category_id: int) -> None:
        if self._is_delete_suppressed():
            return
        self._deleter.handle_delete_category(category_id)

    def handle_delete_categories(self, category_ids) -> None:
        if self._is_delete_suppressed():
            return
        self._deleter.handle_delete_categories(category_ids)

    def _has_any_items_in_tree(self) -> bool:
        """Return True if the tree (QTreeView) has at least one item."""
        try:
            if hasattr(self.tree, "model"):
                model = self.tree.model()
                if model is not None and hasattr(model, "rowCount"):
                    return (model.rowCount() or 0) > 0
        except (AttributeError, RuntimeError) as e:
            logger.debug(
                "[ItemOperations._has_any_items_in_tree] model access failed: %s", e
            )
        return False
