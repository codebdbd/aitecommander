"""Context menu builder for the structure tree."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtWidgets import QMenu

# Context operations service for structure
from app.utils.ui.menu_builders.menu_actions import (
    ActionBuilder,
    MenuTexts,
    Shortcuts,
    StructureItemType,
)
from app.utils.ui.qt.roles import get_tree_tuple

from .base import create_context_action, get_menu_icon

if TYPE_CHECKING:
    from app.views.windows.main_window_protocol import MainWindowProtocol

logger = logging.getLogger(__name__)


class StructureMenuBuilder:
    """Context menu builder for the structure tree."""

    def __init__(self, tree_widget, main_window: "MainWindowProtocol"):
        self.tree_widget = tree_widget
        self.main_window = main_window
        self.actions = ActionBuilder(tree_widget)
        self.theme = main_window.settings.get_theme()
    def build(
        self,
        item: Optional[Any],
        delete_item_cb: Callable,
        add_new_section_cb: Callable,
    ) -> QMenu:
        """Build context menu for the structure tree."""
        menu = QMenu(self.tree_widget)
        try:
            action_controller = getattr(self.main_window, "action_controller", None)
            if action_controller is not None:
                action_controller.update_action_states()
        except Exception:
            logger.debug("[CtxMenu] Failed to update global action states", exc_info=True)

        if item:
            self._add_item_actions(menu, item, delete_item_cb)
        else:
            self._add_root_actions(menu, add_new_section_cb)

        return menu

    def _add_item_actions(self, menu: QMenu, item: Any, delete_item_cb: Callable):
        """Add actions for the selected item."""
        t = get_tree_tuple(item, 0)
        if not t:
            logger.warning("Invalid item data in context menu: None")
            return
        typ, id_ = t
        if typ not in (StructureItemType.SECTION, StructureItemType.CATEGORY):
            logger.warning("Unknown item type in context menu: %s", typ)
            return

        if typ == StructureItemType.SECTION:
            self._add_section_actions(menu, item, id_, delete_item_cb)
        elif typ == StructureItemType.CATEGORY:
            self._add_category_actions(menu, item, id_, delete_item_cb)

    def _add_section_actions(
        self, menu: QMenu, item: Any, section_id: Any, delete_item_cb: Callable
    ):
        """Actions for the selected section."""
        menu.addAction(
            self.actions.create(
                MenuTexts.ADD_CATEGORY,
                self.main_window.add_new_category,
                Shortcuts.ADD_CATEGORY,
                get_menu_icon("add_category", self.theme),
            )
        )
        menu.addAction(
            self.actions.create(
                MenuTexts.IMPORT_CATEGORY,
                lambda: self.main_window.import_category_to_section(int(section_id)),
                None,
                get_menu_icon("import_category", self.theme),
            )
        )
        menu.addSeparator()

        menu.addAction(
            self.actions.create(
                MenuTexts.EDIT_SECTION,
                lambda: self.main_window.edit_structure_item(item),
                Shortcuts.EDIT,
                get_menu_icon("edit", self.theme),
            )
        )
        menu.addAction(
            self.actions.create(
                MenuTexts.SHARE_SECTION,
                lambda: self.main_window.share_section(int(section_id)),
                None,
                get_menu_icon("share", self.theme),
            )
        )

        menu.addSeparator()

        self._add_common_actions(menu, edit_action=None)

    def _add_category_actions(
        self, menu: QMenu, item: Any, category_id: Any, delete_item_cb: Callable
    ):
        """Actions for the selected category."""
        def _add_link_to_category():
            handler = getattr(self.main_window, "show_link_dialog_for_category", None)
            if callable(handler):
                try:
                    handler(int(category_id) if category_id is not None else None)
                except Exception:
                    logger.exception(
                        "[CtxMenu] Failed to open link dialog for category %s",
                        category_id,
                    )

        menu.addAction(
            self.actions.create(
                MenuTexts.ADD_LINK,
                _add_link_to_category,
                Shortcuts.ADD_LINK,
                get_menu_icon("add_link", self.theme),
            )
        )
        menu.addSeparator()
        menu.addAction(
            self.actions.create(
                MenuTexts.EDIT_CATEGORY,
                lambda: self.main_window.edit_structure_item(item),
                Shortcuts.EDIT,
                get_menu_icon("edit", self.theme),
            )
        )
        menu.addAction(
            self.actions.create(
                MenuTexts.SHARE_CATEGORY,
                lambda: self.main_window.share_category(int(category_id)),
                None,
                get_menu_icon("share", self.theme),
            )
        )
        menu.addSeparator()

        # Select all categories in the section where this category is located
        self._add_common_actions(menu, edit_action=None)

    def _add_root_actions(self, menu: QMenu, add_new_section_cb: Callable):
        """Add actions for the root level."""
        menu.addAction(
            self.actions.create(
                MenuTexts.ADD_SECTION,
                add_new_section_cb,
                Shortcuts.ADD_SECTION,
                get_menu_icon("add_section", self.theme),
            )
        )
        menu.addSeparator()

        menu.addAction(
            self.actions.create(
                MenuTexts.IMPORT_SECTION,
                self.main_window.import_section_to_current_sphere,
                None,
                get_menu_icon("import_sections", self.theme),
            )
        )

        menu.addSeparator()

        self._add_common_actions(menu, edit_action=None)

    def _clear_tree_selection(self) -> None:
        try:
            sel = (
                self.tree_widget.selectionModel()
                if hasattr(self.tree_widget, "selectionModel")
                else None
            )
            if sel is not None:
                sel.clearSelection()
        except Exception:
            logger.debug("[CtxMenu] Failed to clear tree selection", exc_info=True)

    def _tree_selection_count(self) -> int:
        try:
            sel = (
                self.tree_widget.selectionModel()
                if hasattr(self.tree_widget, "selectionModel")
                else None
            )
            if sel is None:
                return 0
            try:
                rows = sel.selectedRows(0)
                return len(rows or [])
            except Exception:
                return 0
        except Exception:
            return 0

    def _add_common_actions(self, menu: QMenu, edit_action):
        cut_action = self._create_context_action(
            MenuTexts.CUT, "cut_current", Shortcuts.CTRL_X, "cut", "cut_action"
        )
        copy_action = self._create_context_action(
            MenuTexts.COPY, "copy_current", Shortcuts.CTRL_C, "copy", "copy_action"
        )
        paste_action = self._create_context_action(
            MenuTexts.PASTE, "paste_current", Shortcuts.CTRL_V, "paste", "paste_action"
        )
        delete_action = self._create_context_action(
            MenuTexts.DELETE, "delete_current", Shortcuts.DELETE, "delete", "delete_action"
        )

        for action in (cut_action, copy_action, paste_action, delete_action):
            if action is not None:
                menu.addAction(action)

        menu.addSeparator()

        if edit_action is not None:
            menu.addAction(edit_action)

        menu.addSeparator()

        select_all_action = self._create_context_action(
            MenuTexts.SELECT_ALL,
            "select_all_current",
            Shortcuts.CTRL_A,
            "select_all",
            "select_all_action",
        )
        if select_all_action is not None:
            menu.addAction(select_all_action)
        clear_action = self.actions.create(
            MenuTexts.CLEAR_SELECTION,
            self._clear_tree_selection,
            Shortcuts.CLEAR_SELECTION,
            get_menu_icon("select_all", self.theme),
        )
        clear_action.setVisible(self._tree_selection_count() > 1)
        menu.addAction(clear_action)

        menu.addSeparator()

        undo_action = self._create_context_action(
            MenuTexts.UNDO, "undo_current", "edit.undo", "undo", "undo_action"
        )
        redo_action = self._create_context_action(
            MenuTexts.REDO, "redo_current", "edit.redo", "redo", "redo_action"
        )
        if undo_action is not None:
            menu.addAction(undo_action)
        if redo_action is not None:
            menu.addAction(redo_action)

    def _create_context_action(
        self,
        text: str,
        handler_name: str,
        shortcut: str | None,
        icon_name: str,
        state_attr: str,
    ):
        return create_context_action(
            actions_builder=self.actions,
            main_window=self.main_window,
            text=text,
            handler_name=handler_name,
            shortcut=shortcut,
            icon_name=icon_name,
            state_attr=state_attr,
            icon_getter=lambda name: get_menu_icon(name, self.theme),
        )
