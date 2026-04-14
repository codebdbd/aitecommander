"""Context menu builder for category tiles."""

import logging
from typing import TYPE_CHECKING, Any, Callable

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QListWidget, QMenu

from app.utils.ui.menu_builders.menu_actions import ActionBuilder, MenuTexts, Shortcuts

from .base import create_context_action, get_menu_icon

if TYPE_CHECKING:
    from app.views.windows.main_window_protocol import MainWindowProtocol

logger = logging.getLogger(__name__)


class CategoryMenuBuilder:
    """Context menu builder for category tiles."""

    def __init__(self, list_widget: QListWidget, main_window: "MainWindowProtocol"):
        self.list_widget = list_widget
        self.main_window = main_window
        self.actions = ActionBuilder(list_widget)
        self.theme = main_window.settings.get_theme()

    def build(
        self,
        item_id: Any,
        edit_cb: Callable,
        delete_cb: Callable,
        add_link_cb: Callable,
    ) -> tuple[QMenu, QAction, QAction, QAction]:
        """Build context menu for a category tile.

        Return values follow visual order:
        (menu, edit_action, add_link_action, delete_action).
        """
        menu = QMenu(self.list_widget)
        try:
            action_controller = getattr(self.main_window, "action_controller", None)
            if action_controller is not None:
                action_controller.update_action_states()
        except Exception:
            logger.debug("[CtxMenu] Failed to update global action states", exc_info=True)

        edit_action = self.actions.create(
            MenuTexts.EDIT_CATEGORY,
            lambda: edit_cb(item_id),
            Shortcuts.EDIT,
            self._get_icon("edit"),
        )
        delete_action = self._create_context_action(
            MenuTexts.DELETE, "delete_current", Shortcuts.DELETE, "delete", "delete_action"
        )

        add_link_action = self.actions.create(
            MenuTexts.ADD_LINK,
            lambda: add_link_cb(item_id),
            Shortcuts.ADD_LINK,
            self._get_icon("add_link"),
        )

        menu.addAction(add_link_action)
        menu.addSeparator()
        menu.addAction(edit_action)
        menu.addAction(
            self.actions.create(
                MenuTexts.SHARE_CATEGORY,
                lambda: self.main_window.share_category(int(item_id)),
                None,
                self._get_icon("share"),
            )
        )
        menu.addSeparator()

        self._add_common_actions(menu, None)

        # Order: add_link, share, [sep], cut/copy/paste, [sep], edit, [sep], delete,
        # [sep], select_all/clear, [sep], undo/redo
        return menu, edit_action, add_link_action, delete_action or edit_action

    def _add_common_actions(self, menu: QMenu, edit_action: QAction | None) -> None:
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
            self._clear_tiles_selection,
            Shortcuts.CLEAR_SELECTION,
            self._get_icon("select_all"),
        )
        clear_action.setVisible(self._tiles_selection_count() > 1)
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
    ) -> QAction | None:
        return create_context_action(
            actions_builder=self.actions,
            main_window=self.main_window,
            text=text,
            handler_name=handler_name,
            shortcut=shortcut,
            icon_name=icon_name,
            state_attr=state_attr,
            icon_getter=self._get_icon,
        )

    def _clear_tiles_selection(self) -> None:
        try:
            sel_model = self.list_widget.selectionModel()
            if sel_model:
                sel_model.clearSelection()
        except Exception:
            logger.debug("[CtxMenu] Failed to clear tiles selection", exc_info=True)

    def _tiles_selection_count(self) -> int:
        try:
            sel_model = self.list_widget.selectionModel()
            if sel_model is None:
                return 0
            try:
                indexes = sel_model.selectedIndexes() or []
                return len(indexes)
            except Exception:
                return 0
        except Exception:
            return 0

    def _get_icon(self, name: str):
        """Get themed menu icon through the shared menu icon pipeline."""
        return get_menu_icon(name, self.theme)

