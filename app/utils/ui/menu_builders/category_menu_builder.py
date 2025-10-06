"""Context menu builder for category tiles."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Tuple

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QListWidget, QMenu

from app.utils.ui.icon.icon_operations.creators import themed_icon
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.menu_builders.menu_actions import ActionBuilder, Shortcuts, MenuTexts

if TYPE_CHECKING:
    from app.main_window import MainWindow

logger = logging.getLogger(__name__)


class CategoryMenuBuilder:
    """Context menu builder for category tiles."""

    def __init__(self, list_widget: QListWidget, main_window: "MainWindow"):
        self.list_widget = list_widget
        self.main_window = main_window
        self.actions = ActionBuilder(list_widget)

    def build(
        self,
        item_id: Any,
        edit_cb: Callable,
        delete_cb: Callable,
        add_link_cb: Callable,
    ) -> Tuple[QMenu, QAction, QAction, QAction]:
        """Build context menu for a category tile.

        Return values follow visual order:
        (menu, edit_action, add_link_action, delete_action).
        """
        menu = QMenu(self.list_widget)

        edit_action = self.actions.create(
            MenuTexts.EDIT_CATEGORY,
            lambda: edit_cb(item_id),
            Shortcuts.EDIT,
            self._get_icon("edit"),
        )

        add_link_action = self.actions.create(
            MenuTexts.ADD_LINK,
            lambda: add_link_cb(item_id),
            Shortcuts.ADD_LINK,
            self._get_icon("add_link"),
        )

        delete_action = self.actions.create(
            MenuTexts.DELETE_CATEGORY,
            lambda: delete_cb(item_id),
            Shortcuts.DELETE,
            self._get_icon("delete"),
        )

        menu.addAction(edit_action)
        menu.addAction(add_link_action)
        menu.addSeparator()
        menu.addAction(delete_action)

        # Order: edit, add_link, [sep], delete
        return menu, edit_action, add_link_action, delete_action

    def _get_icon(self, name: str):
        """Get themed icon for current theme."""
        theme = get_current_theme()
        # Icon name to file mapping (unified with structure tree)
        icon_files = {
            "edit": "edit.svg",
            "add_link": "add_link.svg",
            "delete": "delete.svg",
        }
        icon_file = icon_files.get(name, f"{name}.svg")
        return themed_icon(icon_file, theme, "context_menu")
