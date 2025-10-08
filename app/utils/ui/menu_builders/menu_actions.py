"""Menu action creation utilities."""

import logging
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import QWidget

from PyQt6.QtCore import QCoreApplication

_TR_CONTEXT = "MenuActions"


def _tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)

logger = logging.getLogger(__name__)


class ActionBuilder:
    """Menu action builder with error handling."""

    def __init__(self, parent: QWidget):
        self.parent = parent

    def create(
        self,
        text: str,
        callback: Optional[Callable] = None,
        shortcut: Optional[str] = None,
        icon: Optional[QIcon] = None,
    ) -> QAction:
        """Create a menu action."""
        action = QAction(_tr(text), self.parent)

        if icon:
            action.setIcon(icon)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutVisibleInContextMenu(True)
            action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        if callback:
            action.triggered.connect(lambda checked=False: self._safe_call(callback))

        return action

    def _safe_call(self, callback: Callable):
        """Safely call a callback with error handling."""
        try:
            callback()
        except Exception as e:
            logger.exception("Menu action execution failed")
            if hasattr(self.parent, "show_error_message"):
                self.parent.show_error_message(_tr("Error: %1").replace("%1", str(e)))


# Hotkey constants
class Shortcuts:
    EDIT = "F2"
    ADD_LINK = "F1"
    ADD_SECTION = "F3"
    ADD_CATEGORY = "F4"
    SORT = "F5"
    DELETE = "Del"
    ENTER = "Enter"
    CTRL_D = "Ctrl+D"
    CTRL_F = "Ctrl+F"
    CTRL_C = "Ctrl+C"
    CTRL_V = "Ctrl+V"
    CTRL_X = "Ctrl+X"
    CTRL_A = "Ctrl+A"
    CTRL_N = "Ctrl+N"
    CTRL_S = "Ctrl+S"


class MenuTexts:
    ADD_SECTION = "Add section"
    ADD_CATEGORY = "Add category"
    ADD_LINK = "Add link"
    CLEAR_FAVORITES = "Clear favorites"
    EXIT = "Exit"
    SETTINGS = "Settings"
    SAVE_DATABASE = "Save database"
    RESTORE_DATABASE = "Restore database"
    CONNECT_DATABASE = "Connect database"
    IMPORT_BROWSER = "Import from browser"
    EXPORT_ICONS = "Export icons"
    IMPORT_ICONS = "Import icons"
    SEARCH_FILES = "Search files"
    ABOUT = "About"
    EDIT_SECTION = "Edit section"
    EDIT_CATEGORY = "Edit category"
    PASTE_CATEGORY = "Paste"
    DELETE_SECTION = "Delete section"
    COPY_CATEGORY = "Copy"
    CUT_CATEGORY = "Cut"
    PASTE_LINK = "Paste"
    DELETE_CATEGORY = "Delete category"
    DELETE_SELECTED = "Delete selected"
    SELECT_ALL_CATEGORIES = "Select all"
    SORT_CATEGORIES = "Sort categories"
    # Undo/Redo
    UNDO = "&Undo"
    REDO = "&Redo"
    # Links context menu
    OPEN = "Open"
    EDIT = "Edit"
    DELETE = "Delete"
    COPY = "Copy"
    PASTE = "Paste"
    CUT = "Cut"
    ADD_LINK = "Add link"  # duplicate key kept for consistency
    SELECT_ALL = "Select all"
    EDIT_NOTE = "Edit note"
    # Favorites toggle
    ADD_TO_FAVORITES = "Add to favorites"
    REMOVE_FROM_FAVORITES = "Remove from favorites"
    # Share submenu and items
    SHARE = "Share"
    EMAIL = "Email"
    SHARE_TELEGRAM = "Telegram"
    SHARE_WHATSAPP = "WhatsApp"
    SHARE_VIBER = "Viber"
    SHARE_X = "X (Twitter)"
    SHARE_FACEBOOK = "Facebook"
    SHARE_LINKEDIN = "LinkedIn"
    SHARE_PINTEREST = "Pinterest"
    EMAIL_VIA_GMAIL = "Via Gmail"
    EMAIL_VIA_CLIENT = "Via default client (mailto)"
    EMAIL_COPY_AS_MESSAGE = "Copy as email message"


class StructureItemType:
    """Item types in the structure tree."""

    SECTION = "section"
    CATEGORY = "category"
