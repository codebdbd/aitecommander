# app/controllers/keyboard/keyboard_manager.py

import logging
import time
from typing import TYPE_CHECKING, Any, Optional, Protocol, TypeVar, cast

if TYPE_CHECKING:
    pass

from PyQt6.QtCore import (
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QObject,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit, QWidget

from app.core.hotkey_manager import HotkeyManager
from app.utils.common import safe_call as _common_safe_call
from app.utils.common import safe_getattr as _common_safe_getattr
from app.utils.ui.focus import WidgetType, get_focus_manager
from app.utils.ui.qt.roles import get_tree_tuple

logger = logging.getLogger(__name__)

# =====================
# Built-in handlers
# =====================
T = TypeVar("T")


class MainWindowProtocol(Protocol):
    """Protocol for main window with required attributes.

    ✅ FIX: Added protocol for strict typing.
    """

    structure: Any  # StructureUIController
    table: Any  # LinksTableView
    links_actions: Any  # LinkOperationsController
    links: Any  # LinksUIController

    def removeEventFilter(self, obj: QObject) -> None:
        ...

    def installEventFilter(self, obj: QObject) -> None:
        ...


class BaseKeyHandler:
    """Base class for key handlers.

    ✅ FIX: Added typing via Protocol.
    """

    def __init__(self, main_window: MainWindowProtocol) -> None:
        """Initializes key handler.

        Args:
            main_window: Main application window
        """
        self.main_window = main_window
        self._focus_manager = get_focus_manager()

    def _is_tree_focused(self, widget: Optional[QWidget]) -> bool:
        """Check if structure tree has focus.
        
        Args:
            widget: Unused, kept for API compatibility
            
        Returns:
            True if structure tree has focus
        """
        return self._focus_manager.is_type_focused(WidgetType.STRUCTURE_TREE)

    def _is_table_focused(self, widget: Optional[QWidget]) -> bool:
        """Check if links table has focus.
        
        Args:
            widget: Unused, kept for API compatibility
            
        Returns:
            True if links table has focus
        """
        return self._focus_manager.is_type_focused(WidgetType.LINKS_TABLE)

    def _is_tiles_focused(self, widget: Optional[QWidget]) -> bool:
        """Check if category tiles have focus.
        
        Args:
            widget: Unused, kept for API compatibility
            
        Returns:
            True if category tiles have focus
        """
        return self._focus_manager.is_type_focused(WidgetType.CATEGORY_TILES)

    def _safe_getattr(self, obj: Any, attr: str, default: Optional[T] = None) -> Any:
        # Delegate to shared common utils
        return _common_safe_getattr(obj, attr, default)

    def _safe_call(
        self,
        obj: Any,
        method_name: str,
        *args: Any,
        default: Optional[T] = None,
        **kwargs: Any,
    ) -> Any:
        # Delegate to shared common utils
        return _common_safe_call(obj, method_name, *args, default=default, **kwargs)


class ClipboardKeyHandler(BaseKeyHandler):
    """Clipboard key handler."""

    def handle_select_all(self) -> None:
        """Handles Ctrl+A depending on context.

        ✅ FIX: Added documentation.

        - Tree: selects all categories of current section
        - Table: selects all rows
        """
        ac = self._safe_getattr(self.main_window, "action_controller")
        if ac:
            self._safe_call(ac, "select_all_current")
            return

    def handle_clear_selection(self) -> None:
        """Handles clear selection depending on context."""
        ac = self._safe_getattr(self.main_window, "action_controller")
        if ac:
            self._safe_call(ac, "clear_selection_current")
            return

    def _handle_tree_select_all(self) -> None:
        """Selects all categories of current section in structure tree."""
        tree = self._get_structure_tree()
        if tree is None:
            return

        self._clear_table_selection()

        parent_idx = self._resolve_parent_index(tree)
        if parent_idx is None:
            return

        model = tree.model() if hasattr(tree, "model") else None
        if model is None:
            return

        self._select_rows_in_parent(tree, model, parent_idx)

    def _get_structure_tree(self):
        structure = self._safe_getattr(self.main_window, "structure")
        if not structure:
            return None
        tree = self._safe_getattr(structure, "tree")
        return tree if tree else None

    def _clear_table_selection(self) -> None:
        try:
            table = self._safe_getattr(self.main_window, "table")
            if table and hasattr(table, "clearSelection"):
                self._safe_call(table, "clearSelection")
        except Exception:
            logger.debug(
                "ClipboardKeyHandler._handle_tree_select_all: failed to clear table selection",
                exc_info=True,
            )

    def _resolve_parent_index(self, tree):
        try:
            if not (hasattr(tree, "currentIndex") and callable(tree.currentIndex)):
                return None
            idx = tree.currentIndex()
            if not (idx and idx.isValid()):
                return None
            try:
                tt = get_tree_tuple(idx, 0)
            except Exception:
                tt = None
            parent_idx = idx.parent() if (tt and tt[0] == "category") else idx
            if not parent_idx or not parent_idx.isValid():
                return None
            return parent_idx
        except Exception:
            logger.debug(
                "ClipboardKeyHandler._handle_tree_select_all: failed to resolve parent index",
                exc_info=True,
            )
            return None

    def _select_rows_in_parent(self, tree, model, parent_idx) -> None:
        try:
            rows = model.rowCount(parent_idx)
            if rows <= 0:
                return
            sel_model = tree.selectionModel()
            if sel_model is None:
                return
            sel_model.clearSelection()
            top_left = model.index(0, 0, parent_idx)
            bottom_right = model.index(rows - 1, 0, parent_idx)
            selection = QItemSelection(top_left, bottom_right)
            sel_model.select(
                selection,
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        except Exception:
            logger.debug(
                "ClipboardKeyHandler._handle_tree_select_all: selection failed",
                exc_info=True,
            )

    def handle_cut(self) -> None:
        """Handles Ctrl+X - cutting selected links.

        ✅ FIX: Added documentation.
        """
        ac = self._safe_getattr(self.main_window, "action_controller")
        if ac:
            self._safe_call(ac, "cut_current")

    def handle_copy(self) -> None:
        """Handles Ctrl+C - copying selected links to clipboard.

        ✅ FIX: Added documentation.
        """
        ac = self._safe_getattr(self.main_window, "action_controller")
        if ac:
            self._safe_call(ac, "copy_current")

    def handle_paste(self) -> None:
        """Handles Ctrl+V - pasting links from clipboard.

        ✅ FIX: Added documentation.
        """
        ac = self._safe_getattr(self.main_window, "action_controller")
        if ac:
            self._safe_call(ac, "paste_current")


class EditingKeyHandler(BaseKeyHandler):
    """Editing key handler."""

    def handle_key(self, event: QKeyEvent, focused_widget: Optional[QWidget]) -> bool:
        key = event.key()
        if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            return self._handle_enter_key(focused_widget)
        elif key == Qt.Key.Key_Escape:
            return self._handle_escape_key(focused_widget)
        return False

    def _handle_enter_key(self, focused_widget: Optional[QWidget]) -> bool:
        # In tree - do nothing
        if self._is_tree_focused(focused_widget):
            return False
        # In tiles - open category
        elif self._is_tiles_focused(focused_widget):
            return self._handle_tiles_enter()
        # In table - open link
        elif self._is_table_focused(focused_widget):
            return self._handle_table_enter()
        return False

    def _handle_escape_key(self, focused_widget: Optional[QWidget]) -> bool:
        # In tiles - clear filter
        if self._is_tiles_focused(focused_widget):
            return self._handle_tiles_escape()
        # Globally - clear search
        return self._handle_global_escape()

    def _handle_table_enter(self) -> bool:
        table = self._safe_getattr(self.main_window, "table")
        if not table:
            return False
        # For QTableView: use current index and model size
        try:
            idx = table.currentIndex() if hasattr(table, "currentIndex") else None
            current_row = idx.row() if idx and idx.isValid() else -1
        except Exception as e:
            logger.debug(
                "EditingKeyHandler._handle_table_enter: failed to read current index",
                exc_info=e,
            )
            current_row = -1
        try:
            model = table.model() if hasattr(table, "model") else None
            row_count = model.rowCount() if model else 0
        except Exception as e:
            logger.debug(
                "EditingKeyHandler._handle_table_enter: failed to read row count",
                exc_info=e,
            )
            row_count = 0

        if 0 <= current_row < row_count:
            # get_link_at(row) unified for QTableView and returns dict
            link = self._safe_call(table, "get_link_at", current_row)
            if link:
                la = self._safe_getattr(self.main_window, "links_actions")
                if la:
                    self._safe_call(la, "open_link", link)
                    return True
                links = self._safe_getattr(self.main_window, "links")
                if links:
                    link_ops = self._safe_getattr(links, "link_ops")
                    if link_ops:
                        self._safe_call(link_ops, "_open_link", link)
                        return True
        return False

    def _handle_tiles_enter(self) -> bool:
        tiles = self._safe_getattr(self.main_window, "tiles")
        if not tiles:
            return False
        list_widget = self._safe_getattr(tiles, "list_widget")
        if list_widget:
            current_item = self._safe_call(list_widget, "currentItem")
            if current_item:
                result = self._safe_call(
                    tiles, "_on_item_clicked", current_item, default=False
                )
                return bool(result)
        return False

    def _handle_tiles_escape(self) -> bool:
        tiles = self._safe_getattr(self.main_window, "tiles")
        if tiles:
            filter_text = self._safe_getattr(tiles, "_filter_text")
            if filter_text:
                result = self._safe_call(tiles, "clear_filter", default=False)
                return bool(result)
        return False

    def _handle_global_escape(self) -> bool:
        search = self._safe_getattr(self.main_window, "search")
        if search and self._safe_call(search, "text", default=""):
            self._safe_call(search, "clear")
            return True
        return False

    def handle_show_note(self) -> None:
        la = self._safe_getattr(self.main_window, "links_actions")
        if la:
            selected_links = self._safe_call(la, "get_selected_links")
            if selected_links:
                self._safe_call(la, "show_note_dialog", selected_links[0])
            return
        links = self._safe_getattr(self.main_window, "links")
        if links:
            selected_links = self._safe_call(links, "get_selected_links")
            if selected_links:
                self._safe_call(links, "show_note_dialog", selected_links[0])

    def handle_toggle_favorite(self) -> None:
        la = self._safe_getattr(self.main_window, "links_actions")
        if la:
            selected_links = self._safe_call(la, "get_selected_links")
            if selected_links:
                self._safe_call(la, "toggle_link_favorite", selected_links[0])
            return
        links = self._safe_getattr(self.main_window, "links")
        if links:
            selected_links = self._safe_call(links, "get_selected_links")
            if selected_links:
                self._safe_call(
                    self.main_window, "toggle_link_favorite", selected_links[0]
                )


class GlobalKeyHandler(BaseKeyHandler):
    """Global hotkey handler."""

    def _handle_text_undo_redo(self, redo: bool = False) -> bool:
        widget = QApplication.focusWidget()
        if not isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return False
        method = "redo" if redo else "undo"
        handler = getattr(widget, method, None)
        if not callable(handler):
            return False
        try:
            handler()
        except Exception:
            return False
        return True

    def handle_f1(self) -> None:
        logger.debug("KeyboardManager: F1 pressed")
        self._safe_call(self.main_window, "show_link_dialog")

    def handle_f2(self) -> None:
        logger.debug("KeyboardManager: F2 pressed")
        self._safe_call(self.main_window, "edit_current")

    def handle_f3(self) -> None:
        logger.debug("KeyboardManager: F3 pressed")
        self._safe_call(self.main_window, "show_section_dialog")

    def handle_f4(self) -> None:
        # Add category (previously method was called show_category_dialog)
        logger.debug("KeyboardManager: F4 pressed")
        self._safe_call(self.main_window, "add_new_category")

    def handle_f6(self) -> None:
        action = self._safe_getattr(self.main_window, "switch_sphere_action")
        if action:
            logger.debug("KeyboardManager: F6 pressed")
            self._safe_call(action, "trigger")

    def handle_file_search(self) -> None:
        logger.debug("KeyboardManager: F8 pressed")
        self._safe_call(self.main_window, "show_file_search_dialog")

    def handle_settings(self) -> None:
        logger.debug("KeyboardManager: F7 pressed")
        self._safe_call(self.main_window, "show_settings_dialog")

    def handle_import_from_browser(self) -> None:
        logger.debug("KeyboardManager: Ctrl+Alt+C pressed")
        self._safe_call(self.main_window, "handle_import_browser_bookmarks")

    def handle_import_icons(self) -> None:
        logger.debug("KeyboardManager: Ctrl+Alt+I pressed")
        db = self._safe_getattr(self.main_window, "database_controller")
        if db:
            self._safe_call(db, "handle_load_icons")

    def handle_connect_database(self) -> None:
        logger.debug("KeyboardManager: Ctrl+Alt+D pressed")
        db = self._safe_getattr(self.main_window, "database_controller")
        if db:
            self._safe_call(db, "handle_connect_database")

    def handle_save_database(self) -> None:
        logger.debug("KeyboardManager: Ctrl+Alt+S pressed")
        db = self._safe_getattr(self.main_window, "database_controller")
        if db:
            self._safe_call(db, "handle_save_database")

    def handle_export_icons(self) -> None:
        logger.debug("KeyboardManager: Ctrl+Alt+E pressed")
        db = self._safe_getattr(self.main_window, "database_controller")
        if db:
            self._safe_call(db, "handle_save_icons")

    def handle_refresh_icons(self) -> None:
        logger.debug("KeyboardManager: Ctrl+Alt+H pressed")
        dialogs = self._safe_getattr(self.main_window, "system_dialogs")
        if dialogs:
            self._safe_call(dialogs, "handle_refresh_icons")

    def handle_check_bad_urls(self) -> None:
        logger.debug("KeyboardManager: Ctrl+Alt+U pressed")
        dialogs = self._safe_getattr(self.main_window, "system_dialogs")
        if dialogs:
            self._safe_call(dialogs, "handle_check_bad_urls")

    def handle_restore_database(self) -> None:
        logger.debug("KeyboardManager: Ctrl+Alt+B pressed")
        db = self._safe_getattr(self.main_window, "database_controller")
        if db:
            self._safe_call(db, "handle_restore_database")

    def handle_clear_favorites(self) -> None:
        logger.debug("KeyboardManager: Ctrl+Alt+F pressed")
        db = self._safe_getattr(self.main_window, "database_controller")
        if db:
            self._safe_call(db, "handle_clear_favorites")

    def handle_delete(self) -> None:
        action = self._safe_getattr(self.main_window, "delete_action")
        if action and self._safe_call(action, "isEnabled", default=False):
            self._safe_call(action, "trigger")
            return
        self._safe_call(self.main_window, "delete_current")

    def handle_undo(self) -> None:
        logger.debug("KeyboardManager: Undo pressed")
        ac = self._safe_getattr(self.main_window, "action_controller")
        if ac:
            self._safe_call(ac, "undo_current")

    def handle_redo(self) -> None:
        logger.debug("KeyboardManager: Redo pressed")
        ac = self._safe_getattr(self.main_window, "action_controller")
        if ac:
            self._safe_call(ac, "redo_current")


class SearchKeyHandler(BaseKeyHandler):
    """Search key handler."""

    SEARCH_TIMEOUT = 1000

    def __init__(self, main_window: Any) -> None:
        super().__init__(main_window)
        self._search_text: str = ""
        self._search_timer: QTimer = QTimer(
            parent=main_window
        )  # ✅ Fixed: parent=main_window
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._reset_search)

    def handle_focus_search(self) -> None:
        search = self._safe_getattr(self.main_window, "search")
        if search:
            self._safe_call(search, "setFocus")

    def handle_clear_search(self) -> None:
        search = self._safe_getattr(self.main_window, "search")
        if search:
            self._safe_call(search, "clear")

    def handle_quick_search(
        self, event: QKeyEvent, focused_widget: Optional[QWidget]
    ) -> bool:
        if not self._is_tiles_focused(focused_widget):
            return False
        char = event.text().lower()
        self._search_timer.stop()
        self._search_text += char
        self._search_timer.start(self.SEARCH_TIMEOUT)
        tiles = self._safe_getattr(self.main_window, "tiles")
        if tiles:
            result = self._safe_call(
                tiles, "_quick_search", self._search_text, default=False
            )
            return bool(result)
        return False

    def _reset_search(self) -> None:
        self._search_text = ""


class KeyboardManager(QObject):
    """Centralized hotkey manager."""

    ENTER_COOLDOWN = 150

    def __init__(self, main_window: QWidget):
        super().__init__(parent=main_window)  # ✅ Fixed: added parent
        self._parent_widget: QWidget = main_window
        self.main_window: MainWindowProtocol = cast(MainWindowProtocol, main_window)
        self.shortcuts: list = []

        self.global_handler = GlobalKeyHandler(self.main_window)
        self.editing_handler = EditingKeyHandler(self.main_window)
        self.clipboard_handler = ClipboardKeyHandler(self.main_window)
        self.search_handler = SearchKeyHandler(self.main_window)

        self._last_enter_time = 0

        self._parent_widget.installEventFilter(self)
        self._setup_shortcuts()

    def _setup_shortcuts(self) -> None:
        """Setup QShortcut for key combinations."""

        global_shortcuts = [
            ("global.add_link", self.global_handler.handle_f1),
            ("global.edit_link", self.global_handler.handle_f2),
            ("global.add_section", self.global_handler.handle_f3),
            ("global.add_category", self.global_handler.handle_f4),
            ("global.switch_sphere", self.global_handler.handle_f6),
            ("global.search_files", self.global_handler.handle_file_search),
            ("global.settings", self.global_handler.handle_settings),
            ("global.import_browser", self.global_handler.handle_import_from_browser),
            ("global.import_icons", self.global_handler.handle_import_icons),
            ("global.import_db", self.global_handler.handle_connect_database),
            ("global.save_db", self.global_handler.handle_save_database),
            ("global.export_icons", self.global_handler.handle_export_icons),
            ("global.refresh_icons", self.global_handler.handle_refresh_icons),
            ("global.check_bad_urls", self.global_handler.handle_check_bad_urls),
            ("global.restore_db", self.global_handler.handle_restore_database),
            ("global.clear_favorites", self.global_handler.handle_clear_favorites),
            ("global.undo", self.global_handler.handle_undo),
            ("global.redo", self.global_handler.handle_redo),
            ("global.redo_alt", self.global_handler.handle_redo),
        ]

        for action_id, handler in global_shortcuts:
            context = (
                Qt.ShortcutContext.WindowShortcut
                if action_id
                in ("global.undo", "global.redo", "global.redo_alt", "global.delete")
                else Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            try:
                shortcut = HotkeyManager.bind(
                    action_id, self._parent_widget, handler, context=context
                )
            except Exception as e:
                logger.debug(
                    "KeyboardManager._setup_shortcuts: failed to bind %s",
                    action_id,
                    exc_info=e,
                )
                continue
            self.shortcuts.append(shortcut)

        table_shortcuts = [
            ("table.search_focus", self.search_handler.handle_focus_search),
            ("table.search_clear", self.search_handler.handle_clear_search),
            ("table.notes", self.editing_handler.handle_show_note),
            ("table.toggle_favorite", self.editing_handler.handle_toggle_favorite),
        ]

        # Register on main window so it works even if table is not yet created
        for action_id, handler in table_shortcuts:
            try:
                shortcut = HotkeyManager.bind(
                    action_id,
                    self._parent_widget,
                    handler,
                    context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
                )
            except Exception as e:
                logger.debug(
                    "KeyboardManager._setup_shortcuts: failed to bind %s",
                    action_id,
                    exc_info=e,
                )
                continue
            self.shortcuts.append(shortcut)

        edit_shortcuts = [
            ("edit.cut", self.clipboard_handler.handle_cut),
            ("edit.copy", self.clipboard_handler.handle_copy),
            ("edit.paste", self.clipboard_handler.handle_paste),
            ("edit.select_all", self.clipboard_handler.handle_select_all),
            ("edit.clear_selection", self.clipboard_handler.handle_clear_selection),
        ]
        for action_id, handler in edit_shortcuts:
            try:
                shortcut = HotkeyManager.bind(
                    action_id,
                    self._parent_widget,
                    handler,
                    context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
                )
            except Exception as e:
                logger.debug(
                    "KeyboardManager._setup_shortcuts: failed to bind %s",
                    action_id,
                    exc_info=e,
                )
                continue
            self.shortcuts.append(shortcut)

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        """Event filter for intercepting keys."""
        if event is None or obj is None:
            return False
        if event.type() == event.Type.KeyPress:
            if self._is_enter_duplicate(event):
                return True

            focused_widget = QApplication.focusWidget()

            if self._handle_editing_keys(event, focused_widget):
                return True
            elif self._handle_search_keys(event, focused_widget):
                return True

        return super().eventFilter(obj, event)

    def _is_enter_duplicate(self, event):
        """Check for double Enter press."""
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            current_time = int(time.time() * 1000)

            if current_time - self._last_enter_time < self.ENTER_COOLDOWN:
                return True

            self._last_enter_time = current_time

        return False

    def _handle_editing_keys(self, event, focused_widget):
        """Handle editing keys."""
        key = event.key()

        if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape):
            return self.editing_handler.handle_key(event, focused_widget)

        return False

    def _handle_search_keys(self, event, focused_widget):
        """Handle search keys."""
        if (
            event.text().isalnum()
            and len(event.text()) == 1
            and self.search_handler._is_tiles_focused(focused_widget)
        ):
            return self.search_handler.handle_quick_search(event, focused_widget)

        return False

    def cleanup(self):
        """Resource cleanup."""
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts.clear()

        # Remove event filter
        self.main_window.removeEventFilter(self)
