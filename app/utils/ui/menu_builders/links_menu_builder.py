"""Context menu builder for the links table."""

import json
import logging
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QCoreApplication, QModelIndex
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from app.utils.ui.menu_builders.menu_actions import ActionBuilder, MenuTexts, Shortcuts

from .base import create_context_action, get_menu_icon

if TYPE_CHECKING:
    from app.views.windows.main_window_protocol import MainWindowProtocol

logger = logging.getLogger(__name__)


class LinksMenuBuilder:
    """Context menu builder for the links table."""

    def __init__(self, table_widget: QWidget, main_window: "MainWindowProtocol"):
        self.table_widget = table_widget
        self.main_window = main_window
        self.actions = ActionBuilder(table_widget)
        self.theme = main_window.settings.get_theme()

    def build(self, idx: QModelIndex, paste_link_cb: Callable) -> QMenu:
        """Build context menu for the links table."""
        menu = QMenu(self.table_widget)
        try:
            action_controller = getattr(self.main_window, "action_controller", None)
            if action_controller is not None:
                action_controller.update_action_states()
        except Exception:
            logger.debug("[CtxMenu] Failed to update global action states", exc_info=True)

        if idx.isValid():
            link = self.main_window.get_link_at_row(idx.row())
            if link is not None:
                self._add_link_item_actions(menu, link)  # type: ignore[arg-type]
                menu.addSeparator()
                self._add_common_actions(menu, link)  # type: ignore[arg-type]
        else:
            self._add_empty_area_actions(menu, paste_link_cb)
        return menu

    def _add_link_item_actions(self, menu: QMenu, link: dict) -> None:
        """Add actions for the selected link."""
        logger.debug("LinksMenuBuilder._add_link_item_actions: link=%s", link)
        menu.addAction(
            self.actions.create(
                MenuTexts.ADD_LINK,
                lambda: self.main_window.links_actions.show_link_dialog(
                    category_id=self.main_window.get_current_category_id()
                ),
                Shortcuts.ADD_LINK,
                get_menu_icon("add_link", self.theme),
            )
        )
        menu.addAction(
            self.actions.create(
                MenuTexts.EDIT,
                lambda: self.main_window.links_actions.show_link_dialog(link=link),
                Shortcuts.EDIT,
                get_menu_icon("edit", self.theme),
            )
        )
        menu.addSeparator()

        menu.addAction(
            self.actions.create(
                MenuTexts.OPEN,
                self.main_window.links_actions.open_selected_links,
                Shortcuts.ENTER,
                get_menu_icon("run", self.theme),
            )
        )

        is_favorite = link and link.get("is_favorite")
        fav_text = (
            MenuTexts.REMOVE_FROM_FAVORITES
            if is_favorite
            else MenuTexts.ADD_TO_FAVORITES
        )
        fav_icon = (
            get_menu_icon("delete_favorites", self.theme)
            if is_favorite
            else get_menu_icon("add_favorites", self.theme)
        )

        menu.addAction(
            self.actions.create(
                fav_text,
                lambda: self.main_window.links_actions.toggle_link_favorite(link),
                Shortcuts.CTRL_D,
                fav_icon,
            )
        )

        has_notes = bool(str(link.get("notes", "") or "").strip())
        note_text = MenuTexts.EDIT_NOTE if has_notes else MenuTexts.ADD_NOTE
        menu.addAction(
            self.actions.create(
                note_text,
                lambda: self.main_window.links_actions.show_note_dialog(link),
                Shortcuts.CTRL_N,
                get_menu_icon("edit_note", self.theme),
            )
        )

        if self._is_web_link(link):
            menu.addSeparator()
            self._add_share_submenu(menu, link)
            menu.addSeparator()

    def _add_common_actions(self, menu: QMenu, link: dict) -> None:
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
        select_all_action = self._create_context_action(
            MenuTexts.SELECT_ALL,
            "select_all_current",
            Shortcuts.CTRL_A,
            "select_all",
            "select_all_action",
        )

        for action in (cut_action, copy_action, paste_action, delete_action):
            if action is not None:
                menu.addAction(action)

        menu.addSeparator()

        menu.addSeparator()

        if select_all_action is not None:
            menu.addAction(select_all_action)
        clear_action = self.actions.create(
            MenuTexts.CLEAR_SELECTION,
            self._clear_table_selection,
            Shortcuts.CLEAR_SELECTION,
            get_menu_icon("select_all", self.theme),
        )
        clear_action.setVisible(self._table_selection_count() > 1)
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

    def _add_share_submenu(self, menu: QMenu, link: dict) -> None:
        """Add "Share" submenu for a single link."""
        try:
            # Guard against non-web links
            if not self._is_web_link(link):
                return
            share_menu = QMenu(
                QCoreApplication.translate("MenuActions", MenuTexts.SHARE), menu
            )
            share_menu.setIcon(get_menu_icon("share", self.theme))

            share_menu.addAction(
                self.actions.create(
                    MenuTexts.SHARE_TELEGRAM,
                    lambda: self.main_window.links_actions.share_via_telegram(link),
                    None,
                    get_menu_icon("telegram", self.theme),
                )
            )
            share_menu.addAction(
                self.actions.create(
                    MenuTexts.SHARE_WHATSAPP,
                    lambda: self.main_window.links_actions.share_via_whatsapp(link),
                    None,
                    get_menu_icon("whatsapp", self.theme),
                )
            )
            share_menu.addAction(
                self.actions.create(
                    MenuTexts.SHARE_VIBER,
                    lambda: self.main_window.links_actions.share_via_viber(link),
                    None,
                    get_menu_icon("viber", self.theme),
                )
            )
            share_menu.addAction(
                self.actions.create(
                    MenuTexts.SHARE_X,
                    lambda: self.main_window.links_actions.share_via_x(link),
                    None,
                    get_menu_icon("x", self.theme),
                )
            )
            share_menu.addAction(
                self.actions.create(
                    MenuTexts.SHARE_FACEBOOK,
                    lambda: self.main_window.links_actions.share_via_facebook(link),
                    None,
                    get_menu_icon("facebook", self.theme),
                )
            )
            share_menu.addAction(
                self.actions.create(
                    MenuTexts.SHARE_LINKEDIN,
                    lambda: self.main_window.links_actions.share_via_linkedin(link),
                    None,
                    get_menu_icon("linkedin", self.theme),
                )
            )
            share_menu.addAction(
                self.actions.create(
                    MenuTexts.SHARE_PINTEREST,
                    lambda: self.main_window.links_actions.share_via_pinterest(link),
                    None,
                    get_menu_icon("pinterest", self.theme),
                )
            )
            email_menu = QMenu(
                QCoreApplication.translate("MenuActions", MenuTexts.EMAIL), share_menu
            )
            email_menu.setIcon(get_menu_icon("email", self.theme))
            email_menu.addAction(
                self.actions.create(
                    MenuTexts.EMAIL_VIA_GMAIL,
                    lambda: self.main_window.links_actions.share_via_email_gmail(link),
                    None,
                    get_menu_icon("gmail", self.theme),
                )
            )
            email_menu.addAction(
                self.actions.create(
                    MenuTexts.EMAIL_VIA_CLIENT,
                    lambda: self.main_window.links_actions.share_via_email_client(link),
                    None,
                    get_menu_icon("email_client", self.theme),
                )
            )
            email_menu.addAction(
                self.actions.create(
                    MenuTexts.EMAIL_COPY_AS_MESSAGE,
                    lambda: self.main_window.links_actions.copy_email_template(link),
                    None,
                    get_menu_icon("copy", self.theme),
                )
            )

            share_menu.addMenu(email_menu)

            menu.addMenu(share_menu)
        except Exception as e:
            logger.warning("Failed to build Share submenu: %s", e, exc_info=True)

    def _is_web_link(self, link: dict) -> bool:
        """Check if link is a web link (http/https)."""
        if not isinstance(link, dict):
            return False
        try:
            url = link.get("url") or link.get("href")
            if not isinstance(url, str):
                return False
            low = url.strip().lower()
            return low.startswith("http://") or low.startswith("https://")
        except Exception:
            return False

    def _add_empty_area_actions(self, menu: QMenu, paste_link_cb: Callable):
        """Add actions for empty area of the table."""
        current_category_id = self.main_window.get_current_category_id()
        if current_category_id is not None:
            menu.addAction(
                self.actions.create(
                    MenuTexts.ADD_LINK,
                    lambda: self.main_window.links_actions.show_link_dialog(
                        category_id=current_category_id
                    ),
                    Shortcuts.ADD_LINK,
                    get_menu_icon("add_link", self.theme),
                )
            )
            menu.addSeparator()

        if self._clipboard_has_links():
            paste_action = self._create_context_action(
                MenuTexts.PASTE, "paste_current", Shortcuts.CTRL_V, "paste", "paste_action"
            )
            if paste_action is not None:
                menu.addAction(paste_action)

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
            self._clear_table_selection,
            Shortcuts.CLEAR_SELECTION,
            get_menu_icon("select_all", self.theme),
        )
        clear_action.setVisible(self._table_selection_count() > 1)
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

    def _clear_table_selection(self) -> None:
        try:
            if hasattr(self.table_widget, "clearSelection"):
                self.table_widget.clearSelection()
        except Exception:
            logger.debug("[CtxMenu] Failed to clear table selection", exc_info=True)

    def _table_selection_count(self) -> int:
        try:
            if hasattr(self.table_widget, "selectionModel"):
                sel = self.table_widget.selectionModel()
                if sel is None:
                    return 0
                try:
                    rows = sel.selectedRows()
                    return len(rows or [])
                except Exception:
                    return 0
        except Exception:
            pass
        return 0

    def _clipboard_has_links(self) -> bool:
        """Check if clipboard contains links."""
        try:
            app = QApplication.instance()
            if app is None:
                return False

            clipboard = app.clipboard()  # type: ignore[attr-defined]
            if clipboard is None:
                return False

            text = clipboard.text() or ""
            if not text.strip():
                return False

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                logger.debug(
                    "[LinksMenu] Clipboard does not contain valid JSON for links"
                )
                return False

            if isinstance(data, dict) and "name" in data:
                return True
            if isinstance(data, list) and any(
                isinstance(link, dict) and "name" in link for link in data
            ):
                return True
        except Exception as e:
            logger.warning("[LinksMenu] Clipboard check failed: %s", e)
        return False
