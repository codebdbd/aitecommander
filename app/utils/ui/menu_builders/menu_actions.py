"""Menu action creation utilities."""

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import QWidget

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
            # Display shortcut hint, but leave global handling to KeyboardManager
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
    ADD_SECTION = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Add section")
    ADD_CATEGORY = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Add category")
    ADD_LINK = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Add link")
    CLEAR_FAVORITES = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Clear favorites")
    EXIT = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Exit")
    SETTINGS = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Settings")
    SAVE_DATABASE = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Save database")
    RESTORE_DATABASE = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Restore database")
    CONNECT_DATABASE = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Connect database")
    IMPORT_BROWSER = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Import from browser")
    EXPORT_ICONS = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Export icons")
    IMPORT_ICONS = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Import icons")
    SEARCH_FILES = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Search files")
    ABOUT = QT_TRANSLATE_NOOP(_TR_CONTEXT, "About")
    EDIT_SECTION = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Edit section")
    EDIT_CATEGORY = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Edit category")
    PASTE_CATEGORY = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Paste")
    DELETE_SECTION = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Delete section")
    COPY_CATEGORY = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Copy")
    CUT_CATEGORY = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Cut")
    PASTE_LINK = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Paste")
    DELETE_CATEGORY = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Delete category")
    DELETE_SELECTED = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Delete selected")
    SELECT_ALL_CATEGORIES = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Select all")
    SORT_CATEGORIES = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Sort categories")
    # Undo/Redo
    UNDO = QT_TRANSLATE_NOOP(_TR_CONTEXT, "&Undo")
    REDO = QT_TRANSLATE_NOOP(_TR_CONTEXT, "&Redo")
    # Links context menu
    OPEN = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Open")
    EDIT = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Edit")
    DELETE = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Delete")
    COPY = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Copy")
    PASTE = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Paste")
    CUT = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Cut")
    ADD_LINK = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Add link")
    SELECT_ALL = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Select all")
    EDIT_NOTE = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Edit note")
    # Favorites toggle
    ADD_TO_FAVORITES = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Add to favorites")
    REMOVE_FROM_FAVORITES = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Remove from favorites")
    # Share submenu and items
    SHARE = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Share")
    EMAIL = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Email")
    SHARE_TELEGRAM = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Telegram")
    SHARE_WHATSAPP = QT_TRANSLATE_NOOP(_TR_CONTEXT, "WhatsApp")
    SHARE_VIBER = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Viber")
    SHARE_X = QT_TRANSLATE_NOOP(_TR_CONTEXT, "X (Twitter)")
    SHARE_FACEBOOK = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Facebook")
    SHARE_LINKEDIN = QT_TRANSLATE_NOOP(_TR_CONTEXT, "LinkedIn")
    SHARE_PINTEREST = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Pinterest")
    EMAIL_VIA_GMAIL = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Via Gmail")
    EMAIL_VIA_CLIENT = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Via default client (mailto)")
    EMAIL_COPY_AS_MESSAGE = QT_TRANSLATE_NOOP(_TR_CONTEXT, "Copy as email message")


class StructureItemType:
    """Item types in the structure tree."""

    SECTION = "section"
    CATEGORY = "category"
