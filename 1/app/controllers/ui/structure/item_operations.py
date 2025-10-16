# app/controllers/structure/item_operations.py

import logging

from PyQt6.QtCore import QObject, pyqtSlot

# Use string literals "section" and "category"
from app.controllers.ui.dialogs.dialog_manager import DialogManager
from app.controllers.ui.structure.item_deletion_service import ItemDeletionService
from app.controllers.ui.structure.item_dialogs_service import ItemDialogService

logger = logging.getLogger(__name__)


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
        self.business.load_structure()
        if item_to_select:
            from app.controllers.ui.state.task_scheduler import (
                schedule_focus,
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
            # Additionally restore focus to the tree
            try:
                schedule_focus(lambda: self.tree.setFocus(), "structure_tree")
            except Exception as e:
                logger.debug("[ItemOperations.load] schedule_focus failed: %s", e)

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
        msg = (
            f"Section '{section_name}' contains {cats_count} categor"
            f"{'y' if cats_count == 1 else 'ies'} and {links_count} link"
            f"{'s' if links_count != 1 else ''}.\n\n"
            "All nested categories and links will be permanently deleted!\n\n"
            "Are you sure you want to continue?"
        )
        return DialogManager.ask_confirmation(
            self.main,
            msg,
            "Delete section",
            informative_text="This action is irreversible. All nested categories and links will be deleted.",
            details=f"section_id={section_data.get('id')}, cats={cats_count}, links={links_count}",
        )

    def _confirm_category_deletion(self, category_data: dict, links_count: int) -> bool:
        category_name = category_data.get("name", "unknown category")
        msg = (
            f"Category '{category_name}' contains {links_count} link"
            f"{'s' if links_count != 1 else ''}.\n\n"
            "All nested links will be permanently deleted!\n\n"
            "Are you sure you want to continue?"
        )
        return DialogManager.ask_confirmation(
            self.main,
            msg,
            "Confirm deletion",
            informative_text="This action is irreversible. All links in the category will be deleted.",
            details=f"category_id={category_data.get('id')}, links={links_count}",
        )

    def handle_edit_category(self, category_id: int) -> None:
        self._dialogs.handle_edit_category(category_id)

    def handle_delete_category(self, category_id: int) -> None:
        if self._is_delete_suppressed():
            return
        self._deleter.handle_delete_category(category_id)

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
