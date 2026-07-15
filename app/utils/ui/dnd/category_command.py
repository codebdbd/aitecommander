"""Команда перемещения категории с использованием нового базового класса."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from app.utils.ui.dnd.base_bulk_command import BaseBulkCommand
from app.utils.ui.dnd.error_handler import BulkOperationErrorHandler

if TYPE_CHECKING:
    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.views.windows.main_window_protocol import MainWindowProtocol

import logging

logger = logging.getLogger(__name__)
error_handler = BulkOperationErrorHandler()


def _require_main(main: object | None) -> MainWindowProtocol:
    if main is None:
        raise RuntimeError("Command requires an attached main window")
    return cast("MainWindowProtocol", main)


def _require_structure_business(main: object | None) -> StructureBusinessLogic:
    main_window = _require_main(main)
    structure_business = getattr(main_window, "structure_business", None)
    if structure_business is None:
        raise RuntimeError("Main window is missing structure_business")
    return cast("StructureBusinessLogic", structure_business)


def _get_structure_business(main: object | None) -> StructureBusinessLogic | None:
    try:
        return _require_structure_business(main)
    except RuntimeError:
        return None


class MoveCategoryCommand(BaseBulkCommand):
    """Moving category between sections."""

    def __init__(self, category_id, new_section_id, main_window) -> None:
        super().__init__("Moving category", main_window, "category")
        self.category_id = category_id
        self.new_section_id = new_section_id
        self.old_section_id = None
        self.cat_name = None
        self._prepared = False

    def _prepare_data(self) -> None:
        """Prepares data for operation."""
        if self._prepared:
            return

        # Get category data via business logic
        structure_business = _require_structure_business(self.main)

        category_data = structure_business.get_category_data(self.category_id)

        if category_data is None:
            raise ValueError(f"Category {self.category_id} not found")

        self.old_section_id = category_data["section_id"]
        self.cat_name = category_data["name"]

        self._prepared = True

    def _execute_operation(self) -> bool:
        """Выполнение перемещения категории."""
        try:
            self._prepare_data()

            if self.old_section_id == self.new_section_id:
                return True  # Nothing to do

            # Check duplicates via business logic
            structure_business = _require_structure_business(self.main)

            if structure_business.has_duplicate_category(
                self.new_section_id, self.cat_name, self.category_id
            ):
                # Silently ignore duplicates - don't show error to user
                logger.debug(
                    "Duplicate category '%s' found in target section %s, ignoring move",
                    self.cat_name,
                    self.new_section_id,
                )
                self.set_obsolete(True)
                return True

            self._set_section(self.new_section_id)
            return True
        except Exception as e:
            context = {
                "operation": "move_category",
                "category_id": self.category_id,
                "target_section": self.new_section_id
            }
            error_handler.handle_error(e, context)
            return False

    def _restore_original_state(self) -> bool:
        """Восстановление исходного состояния категории."""
        try:
            self._set_section(self.old_section_id)
            return True
        except Exception as e:
            context = {
                "operation": "undo_move_category",
                "category_id": self.category_id,
                "original_section": self.old_section_id
            }
            error_handler.handle_error(e, context)
            return False

    def _set_section(self, section_id):
        """Sets section for category via business logic."""
        structure_business = _require_structure_business(self.main)

        # Get full category data for update
        current_category = structure_business.get_category_data(self.category_id)

        if current_category is None:
            raise ValueError(f"Category {self.category_id} not found")

        # Update only section_id, keeping other data
        category_data = {
            "name": current_category["name"],
            "section_id": section_id,
            "icon_path": current_category.get("icon_path", ""),
            "position": current_category.get("position", 0),
        }

        # Now update is delegated to business layer which calls StructureService
        updated = structure_business.update_category(self.category_id, category_data)

        if updated is None:
            raise ValueError(f"Failed to update category {self.category_id}")

    def _refresh_ui(self, affected_items: list = None) -> None:
        """Updates structure UI after operation."""
        # Full tree reload no longer required — model updates incrementally
        # through business logic signals (item_updated etc.). Focus needed category.
        structure_business = _get_structure_business(self.main)
        if structure_business:
            try:
                structure_business.select_category(self.category_id)
                logger.info("Switched focus to moved category %s", self.category_id)
            except Exception as e:
                logger.warning(
                    "Failed to switch focus to category %s: %s",
                    self.category_id,
                    e,
                )

        # Set tree selection to the category for visual focus
        self._set_tree_selection_to_category(self.category_id)

    def _set_tree_selection_to_category(self, category_id: int) -> None:
        """Set tree widget selection to the specified category."""
        try:
            struct = getattr(self.main, "structure", None)
            if not struct:
                return
            tree = getattr(struct, "tree", None)
            if not tree:
                return
            model = tree.model()
            if not model or not hasattr(model, "index_for"):
                return
            cat_index = model.index_for("category", category_id)
            if cat_index and cat_index.isValid():
                tree.setCurrentIndex(cat_index)
        except Exception as e:
            logger.debug(
                "Failed to set tree selection to category %s: %s", category_id, e
            )
