"""Facade to simplify access to main window functionality.

This module provides centralized access to core main window operations,
hiding the complexity of interactions between controllers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from typing import Any, Dict
    
    LinkDict = Dict[str, Any]
    
    from app.controllers.ui.links.links_actions import LinksActions
    from app.controllers.ui.menu_controller import ActionController
    from app.controllers.ui.structure.structure_ui_controller import StructureUIController
    from app.controllers.ui.state.ui_state_manager import UIStateManager
    from app.controllers.ui.theme_controller import ThemeController

logger = logging.getLogger(__name__)


class WindowFacade:
    """Facade for main window operations.

    Encapsulates delegation logic to specialized controllers.
    Simplifies MainWindow by moving coordination logic here.

    Attributes:
        structure: Structure controller (tree, sections, categories)
        links_actions: Links actions controller
        ui_state: UI state manager
        action_controller: Actions controller (edit, delete)
        theme_ctrl: Theme controller
    """
    
    def __init__(
        self,
        structure: "StructureUIController",
        links_actions: "LinksActions",
        ui_state: "UIStateManager",
        action_controller: "ActionController",
        theme_ctrl: "ThemeController",
    ):
        """Initialize facade with required controllers.

        Args:
            structure: Structure controller
            links_actions: Links controller
            ui_state: UI state manager
            action_controller: Actions controller
            theme_ctrl: Theme controller
        """
        self.structure = structure
        self.links_actions = links_actions
        self.ui_state = ui_state
        self.action_controller = action_controller
        self.theme_ctrl = theme_ctrl
        
        logger.debug("WindowFacade initialized")
    
    # === Structure operations ===
    
    def get_current_category_id(self) -> Optional[int]:
        """Return ID of the currently selected category.

        Returns:
            Category ID or None if no category is selected
        """
        return self.structure.get_current_category_id()
    
    def reload_structure(self) -> None:
        """Reload the entire structure (tree)."""
        self.structure.load()
    
    def reload_current_category(self) -> None:
        """Reload the current category.

        Uses UIStateManager to preserve state.
        """
        category_id = self.get_current_category_id()
        if category_id:
            self.ui_state.load_category(category_id, source="reload_current_category")
        else:
            logger.debug("reload_current_category: no category selected")
    
    def add_new_section(self) -> None:
        """Open dialog to create a new section."""
        self.structure.add_new_section()
    
    def add_new_category(self) -> None:
        """Open dialog to create a new category."""
        try:
            self.structure.add_new_category()
        except Exception:
            logger.exception("WindowFacade.add_new_category failed")
            raise
    
    # === Link operations ===
    
    def get_link_at_row(self, row: int) -> "LinkDict | None":
        """Return link by table row number.

        Args:
            row: Row number (0-indexed)

        Returns:
            Dict with link data or None
        """
        return self.links_actions.get_link_at(row)
    
    def get_selected_links(self) -> list["LinkDict"]:
        """Return list of selected links.

        Returns:
            List of dicts with link data
        """
        return self.links_actions.get_selected_links()
    
    def get_selected_rows(self) -> list[int]:
        """Return indices of selected rows.

        Returns:
            List of row indices
        """
        return self.links_actions.get_selected_rows()
    
    def show_link_dialog(
        self,
        link: "LinkDict | None" = None,
        category_id: int | None = None,
    ) -> bool:
        """Show create/edit link dialog.

        Args:
            link: Existing link to edit (None to create new)
            category_id: Category ID for new link

        Returns:
            True if dialog accepted, False if cancelled
        """
        selected_link_id = link.get("id") if link else None
        
        result = self.links_actions.show_link_dialog(link, category_id)
        
        if result and selected_link_id:
            # Schedule selection restore
            self.links_actions.schedule_restore_selection(selected_link_id)
        
        return bool(result)
    
    def edit_selected_link(self) -> bool:
        """Редактирует выбранную ссылку.
        
        Returns:
            True если редактирование прошло успешно
        """
        return bool(self.links_actions.edit_selected_link())
    
    # === Universal actions ===
    
    def edit_current(self) -> None:
        """Edit currently selected item (link or structure item).

        ActionController automatically determines what to edit.
        """
        try:
            self.action_controller.edit_current()
        except Exception:
            logger.exception("WindowFacade.edit_current failed")
            raise
    
    def delete_current(self) -> None:
        """Delete currently selected item (link or structure item).

        ActionController automatically determines what to delete and asks for confirmation.
        """
        self.action_controller.delete_current()
    
    # === Theme operations ===
    
    def get_available_themes(self) -> list[tuple[str, str]]:
        """Return list of available themes.

        Returns:
            List of tuples (theme_id, theme_display_name)
        """
        return self.theme_ctrl.available()
    
    def apply_theme(self, theme_name: str) -> None:
        """Apply a theme.

        Args:
            theme_name: Theme identifier (e.g., 'light', 'dark')
        """
        self.theme_ctrl.apply(theme_name)
    
    def update_theme(self) -> None:
        """Update current theme and refresh UI."""
        self.theme_ctrl.apply_and_refresh_ui()
    
    # === Service methods ===
    
    def on_structure_item_added(
        self, item_type: str, parent_id: int, data: dict
    ) -> None:
        """Handle structure item addition.

        Args:
            item_type: Item type ('section', 'category')
            parent_id: Parent item ID
            data: Item data
        """
        self.structure.on_structure_item_added(item_type, parent_id, data)
    
    def on_structure_item_changed(
        self, item_type: str, item_id: int, data: dict
    ) -> None:
        """Handle structure item change.

        Args:
            item_type: Item type ('section', 'category')
            item_id: Item ID
            data: New item data
        """
        self.structure.on_structure_item_changed(item_type, item_id, data)
