# app/views/tree_components/move_operations_handler.py

"""Handler for move operations in the structure tree (QTreeView-only)."""

import logging
from typing import Any

from PyQt6.QtWidgets import QMessageBox

from app.utils.db.api import run_db
from app.utils.ui.dnd.base import TreeHandlerBase
from app.utils.ui.dnd.commands import (
    MoveCategoriesCommand,
    MoveCategoryCommand,
    MoveLinksCommand,
)
from app.utils.ui.qt.roles import get_tree_tuple

logger = logging.getLogger(__name__)


class MoveOperationsHandler(TreeHandlerBase):
    """Move operations handler for items in the structure tree."""

    def _show_message(
        self,
        kind: str,
        text: str,
        title: str,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        msg = QMessageBox(self.tree_widget)
        if kind == "info":
            msg.setIcon(QMessageBox.Icon.Information)
        elif kind == "warning":
            msg.setIcon(QMessageBox.Icon.Warning)
        else:
            msg.setIcon(QMessageBox.Icon.Critical)
        msg.setText(text)
        if informative_text:
            msg.setInformativeText(informative_text)
        if details:
            msg.setDetailedText(details)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _show_info(
        self,
        text: str,
        title: str,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        self._show_message("info", text, title, informative_text, details, silent)

    def _show_warning(
        self,
        text: str,
        title: str,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        self._show_message("warning", text, title, informative_text, details, silent)

    def _show_error(
        self,
        text: str,
        title: str,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        self._show_message("error", text, title, informative_text, details, silent)

    def execute_move_category_command(self, category_id: int, target_id: int) -> None:
        """Execute the command to move a category."""
        main_win = self.tree_widget.window()

        if hasattr(main_win, "undo_stack"):
            main_win.undo_stack.push(
                MoveCategoryCommand(category_id, target_id, main_win)
            )
            logger.info(
                "MoveCategoryCommand executed: category %s -> section %s",
                category_id,
                target_id,
            )
        else:
            self._show_warning(
                self.tr("Undo history is unavailable. Move canceled."),
                self.tr("Undo history unavailable"),
                informative_text=self.tr(
                    "Enable undo/redo support or initialize undo_stack in the main window."
                ),
            )
            logger.warning("Undo stack not found for moving a category")

    def execute_move_links_command(
        self, link_ids: list[int], new_category_id: int
    ) -> None:
        """Execute the command to move links."""
        main_win = self.tree_widget.window()

        if hasattr(main_win, "undo_stack"):
            main_win.undo_stack.push(
                MoveLinksCommand(link_ids, new_category_id, main_win)
            )
            logger.info(
                "MoveLinksCommand executed: links %s -> category %s",
                link_ids,
                new_category_id,
            )
        else:
            logger.warning("Undo stack not found for moving links")

    def execute_move_categories_command(
        self, category_ids: list[int], new_section_id: int, base_row: int
    ) -> None:
        """Execute batch command to move categories as a single undo record."""
        main_win = self.tree_widget.window()

        if hasattr(main_win, "undo_stack"):
            main_win.undo_stack.push(
                MoveCategoriesCommand(category_ids, new_section_id, base_row, main_win)
            )
            logger.info(
                "MoveCategoriesCommand executed: categories %s -> section %s, base_row=%s",
                category_ids,
                new_section_id,
                base_row,
            )
        else:
            self._show_warning(
                self.tr("Undo history is unavailable. Batch move canceled."),
                self.tr("Undo history unavailable"),
                informative_text=self.tr(
                    "Enable undo/redo support or initialize undo_stack in the main window."
                ),
            )
            logger.warning("Undo stack not found for batch move of categories")

    def execute_move_categories_batch(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> None:
        """Perform the actual batch move of categories via a single business call.

        Suppresses selection/tree signals during the operation, then updates only
        the target section via a single `select_section(target_section_id)` call.
        """
        if not category_ids or not isinstance(target_section_id, int):
            return

        main_win = self.tree_widget.window()
        if not (
            hasattr(main_win, "structure_business") and main_win.structure_business
        ):
            logger.warning(
                "Structure business logic is not available for batch moving categories"
            )
            return

        sb = main_win.structure_business
        struct = getattr(main_win, "structure", None)
        selection = getattr(struct, "selection_handler", None)
        tree = getattr(struct, "tree", None)

        # Suppress cascade of selection/tree signals during the operation
        try:
            if selection is not None:
                try:
                    selection.begin_suppress_selection()
                except Exception:
                    pass
            if tree is not None:
                try:
                    tree.blockSignals(True)
                except Exception:
                    pass

            # Perform batch move in a single transaction via business logic
            moved_ids = sb.move_categories_batch(
                category_ids, int(target_section_id), int(base_row)
            )
            logger.info(
                "Batch move of categories completed: moved %s of %s to section %s",
                len(moved_ids),
                len(category_ids),
                target_section_id,
            )

            # Final targeted UI update: only the target section
            try:
                sb.section_selected.emit(int(target_section_id))
            except Exception:
                pass
        except Exception as e:
            logger.error("Batch move of categories failed: %s", e)
            self._on_db_error(e)
        finally:
            if tree is not None:
                try:
                    tree.blockSignals(False)
                except Exception:
                    pass
            if selection is not None:
                try:
                    selection.end_suppress_selection()
                except Exception:
                    pass

    def handle_internal_move(self, source_item) -> None:
        """Handle internal item move."""
        if not source_item:
            return

        stuple = get_tree_tuple(source_item, 0)
        if not stuple:
            return
        source_type, source_id = stuple
        if source_type not in ("section", "category") or not isinstance(source_id, int):
            return
        parent = source_item.parent()
        main_win = self.tree_widget.window()

        # If it's a category between sections — use command
        if source_type == "category" and parent:
            self._handle_category_section_move(source_id, parent, main_win)
            return

        # For sorting within a section or for sections
        self._handle_position_update(source_type, source_id, parent)

    def handle_category_section_move(self, source_id: int, parent, main_win) -> None:
        """Handle moving a category between sections."""
        pdata = get_tree_tuple(parent, 0)
        if not (isinstance(source_id, int)):
            logger.warning("Invalid source_id type for category move")
            return
        if not pdata:
            logger.warning("Invalid target parent data for category move")
            return
        parent_type, parent_id = pdata
        if parent_type != "section" or not isinstance(parent_id, int):
            logger.warning("Invalid target parent data for category move")
            return
        new_section_id = parent_id

        if hasattr(main_win, "undo_stack"):
            main_win.undo_stack.push(
                MoveCategoryCommand(source_id, new_section_id, main_win)
            )
            logger.info("Category moved: %s -> section %s", source_id, new_section_id)
        else:
            self._show_warning(
                self.tr("History is unavailable. Move between sections canceled."),
                self.tr("Undo history unavailable"),
                informative_text=self.tr(
                    "Enable undo/redo support or initialize undo_stack in the main window."
                ),
            )
            logger.warning(
                "Undo stack not found for moving a category between sections"
            )

    def _handle_category_section_move(self, source_id: int, parent, main_win) -> None:
        """Internal method to handle moving a category between sections."""
        self.handle_category_section_move(source_id, parent, main_win)

    def _handle_position_update(self, source_type: str, source_id: int, parent) -> None:
        """Handle items position update."""
        params = self._prepare_position_params(source_type, source_id, parent)
        if not params:
            return

        def internal_move_task():
            main_window = self.tree_widget.window()
            if not (
                hasattr(main_window, "structure_business")
                and main_window.structure_business
            ):
                raise Exception("Structure business logic is not available")

            success = main_window.structure_business.update_item_positions(
                params["table_name"], params["ids_in_order"]
            )
            if not success:
                raise Exception("Failed to update positions via business logic")

        run_db(
            internal_move_task,
            description="update_item_positions",
            on_finished=self._on_internal_move_finished,
            on_error=self._on_db_error,
        )

    def _prepare_position_params(
        self, source_type: str, source_id: int, parent
    ) -> dict[str, Any]:
        """Prepare parameters for position update (QTreeView)."""

        # Use model and business logic
        try:
            model = getattr(self.tree_widget, "model", lambda: None)()
            if not model:
                return {}

            # Sections: top level of the model
            if source_type == "section":
                ids_in_order: list[int] = []
                rows = model.rowCount()
                for r in range(rows):
                    idx = model.index(r, 0)
                    t = get_tree_tuple(idx, 0)
                    if t and t[0] == "section" and isinstance(t[1], int):
                        ids_in_order.append(int(t[1]))
                if not ids_in_order:
                    return {}
                return {"table_name": "section", "ids_in_order": ids_in_order}

            # Categories: determine parent section via business logic
            if source_type == "category" and isinstance(source_id, int):
                try:
                    hierarchy = None
                    main_window = self.tree_widget.window()
                    if (
                        hasattr(main_window, "structure_business")
                        and main_window.structure_business
                    ):
                        hierarchy = (
                            main_window.structure_business.get_category_hierarchy(
                                source_id
                            )
                        )
                except Exception:
                    hierarchy = None
                section_id = None
                if isinstance(hierarchy, dict):
                    section_id = hierarchy.get("section_id")
                if not isinstance(section_id, int):
                    # Fallback: try to take current index and its parent
                    cur = getattr(self.tree_widget, "currentIndex", lambda: None)()
                    if cur and cur.isValid():
                        parent_idx = cur.parent()
                        pt = (
                            get_tree_tuple(parent_idx, 0)
                            if parent_idx and parent_idx.isValid()
                            else None
                        )
                        if pt and pt[0] == "section" and isinstance(pt[1], int):
                            section_id = pt[1]
                if not isinstance(section_id, int):
                    return {}
                # Iterate over the children of the section index
                sec_idx = (
                    model.index_for("section", int(section_id))
                    if hasattr(model, "index_for")
                    else None
                )
                if not (sec_idx and sec_idx.isValid()):
                    return {}
                ids_in_order: list[int] = []
                rows = model.rowCount(sec_idx)
                for r in range(rows):
                    idx = model.index(r, 0, sec_idx)
                    t = get_tree_tuple(idx, 0)
                    if t and t[0] == "category" and isinstance(t[1], int):
                        ids_in_order.append(int(t[1]))
                if not ids_in_order:
                    return {}
                return {"table_name": "category", "ids_in_order": ids_in_order}
        except Exception:
            pass
        return {}

    def _on_internal_move_finished(self, result=None) -> None:
        """Handle successful completion of an internal move."""
        logger.info("Async internal move finished successfully.")

        if result == "duplicate":
            self._show_info(
                self.tr(
                    "A category with the same name already exists in the selected section."
                ),
                self.tr("Category duplicate"),
                informative_text=self.tr(
                    "Rename the category or choose another section."
                ),
            )
            return

        self._refresh_ui_after_move()

    def _on_db_error(self, error) -> None:
        """Database error handler."""
        logger.error("Database operation failed in MoveOperationsHandler: %s", error)
        self._show_error(
            self.tr("Failed to update item positions."),
            self.tr("Database error during move"),
            informative_text=self.tr("Position changes were not saved."),
            details=str(error),
        )

        # Update UI after error
        self._refresh_ui_after_move()

    def _refresh_ui_after_move(self) -> None:
        """Refresh UI after a move."""
        main_win = self.tree_widget.window()

        # After moving, if current sphere doesn't match the target — switch it
        if hasattr(main_win, "structure_business") and main_win.structure_business:
            try:
                sc = getattr(main_win, "spheres_controller", None)
                if sc and hasattr(sc, "switch_sphere"):
                    sc.switch_sphere(main_win.structure_business.current_sphere_id)
            except Exception:
                pass

        try:
            tw = self.tree_widget
            section_id = None
            if hasattr(tw, "currentIndex"):
                index = tw.currentIndex()
                if index and index.isValid():
                    t = get_tree_tuple(index, 0)
                    if t:
                        typ, id_ = t
                        if typ == "section" and isinstance(id_, int):
                            section_id = id_
                        elif typ == "category":
                            parent_index = index.parent()
                            if parent_index and parent_index.isValid():
                                pt = get_tree_tuple(parent_index, 0)
                                if pt and pt[0] == "section" and isinstance(pt[1], int):
                                    section_id = pt[1]
            if (
                section_id
                and hasattr(main_win, "structure_business")
                and main_win.structure_business
            ):
                struct = getattr(main_win, "structure", None)
                selection = getattr(struct, "selection_handler", None)
                tree = getattr(struct, "tree", None)
                try:
                    if selection is not None:
                        try:
                            selection.begin_suppress_selection()
                        except Exception:
                            pass
                    if tree is not None:
                        try:
                            tree.blockSignals(True)
                        except Exception:
                            pass
                    main_win.structure_business.section_selected.emit(section_id)
                finally:
                    if tree is not None:
                        try:
                            tree.blockSignals(False)
                        except Exception:
                            pass
                    if selection is not None:
                        try:
                            selection.end_suppress_selection()
                        except Exception:
                            pass
        except Exception:
            # Do not block the UI thread due to auxiliary tiles refresh
            pass
