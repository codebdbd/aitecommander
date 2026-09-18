"""Menu action creation utilities."""

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QWidget

from app.core.hotkey_manager import HotkeyManager

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
        action = QAction(QCoreApplication.translate("MenuActions", text), self.parent)

        if icon:
            action.setIcon(icon)
        if shortcut:
            # Display shortcut hint, but leave global handling to KeyboardManager
            seq = HotkeyManager.get_sequence(shortcut)
            if not seq.isEmpty():
                action.setShortcut(seq)
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
                self.parent.show_error_message(QCoreApplication.translate("MenuActions", "Error: %1").replace("%1", str(e)))


# Hotkey constants
class Shortcuts:
    EDIT = "global.edit_link"
    ADD_LINK = "global.add_link"
    ADD_SECTION = "global.add_section"
    ADD_CATEGORY = "global.add_category"
    SETTINGS = "global.settings"
    SEARCH_FILES = "global.search_files"
    LAUNCH_MARKED = "global.launch_marked"
    EXIT = "global.exit"
    DELETE = "global.delete"
    ENTER = "global.enter"
    CTRL_D = "table.toggle_favorite"
    CTRL_F = "table.search_focus"
    CTRL_ALT_C = "global.import_browser"
    CTRL_ALT_I = "global.import_icons"
    CTRL_ALT_D = "global.import_db"
    CTRL_ALT_S = "global.save_db"
    CTRL_ALT_E = "global.export_icons"
    CTRL_ALT_H = "global.refresh_icons"
    CTRL_ALT_U = "global.check_bad_urls"
    CTRL_ALT_B = "global.restore_db"
    CTRL_ALT_F = "global.clear_favorites"
    CTRL_C = "edit.copy"
    CTRL_V = "edit.paste"
    CTRL_X = "edit.cut"
    CTRL_A = "edit.select_all"
    CLEAR_SELECTION = "edit.clear_selection"
    CTRL_N = "table.notes"
    CTRL_S = "global.save"


class MenuTexts:
    ADD_SECTION = QT_TRANSLATE_NOOP("MenuActions", "Add section")
    ADD_CATEGORY = QT_TRANSLATE_NOOP("MenuActions", "Add category")
    ADD_LINK = QT_TRANSLATE_NOOP("MenuActions", "Add link")
    CLEAR_FAVORITES = QT_TRANSLATE_NOOP("MenuActions", "Clear favorites")
    EXIT = QT_TRANSLATE_NOOP("MenuActions", "Exit")
    SETTINGS = QT_TRANSLATE_NOOP("MenuActions", "Settings")
    SAVE_DATABASE = QT_TRANSLATE_NOOP("MenuActions", "Export Database")
    RESTORE_DATABASE = QT_TRANSLATE_NOOP("MenuActions", "Restore Database")
    CONNECT_DATABASE = QT_TRANSLATE_NOOP("MenuActions", "Import Database")
    IMPORT_BROWSER = QT_TRANSLATE_NOOP("MenuActions", "Import Bookmarks")
    EXPORT_ICONS = QT_TRANSLATE_NOOP("MenuActions", "Export icons")
    IMPORT_ICONS = QT_TRANSLATE_NOOP("MenuActions", "Import icons")
    SEARCH_FILES = QT_TRANSLATE_NOOP("MenuActions", "Search files")
    ABOUT = QT_TRANSLATE_NOOP("MenuActions", "About")
    EDIT_SECTION = QT_TRANSLATE_NOOP("MenuActions", "Edit section")
    EDIT_CATEGORY = QT_TRANSLATE_NOOP("MenuActions", "Edit category")
    PASTE_CATEGORY = QT_TRANSLATE_NOOP("MenuActions", "Paste")
    PASTE_SECTION = QT_TRANSLATE_NOOP("MenuActions", "Paste section")
    DELETE_SECTION = QT_TRANSLATE_NOOP("MenuActions", "Delete section")
    COPY_CATEGORY = QT_TRANSLATE_NOOP("MenuActions", "Copy category")
    COPY_SECTION = QT_TRANSLATE_NOOP("MenuActions", "Copy section")
    CUT_CATEGORY = QT_TRANSLATE_NOOP("MenuActions", "Cut")
    PASTE_LINK = QT_TRANSLATE_NOOP("MenuActions", "Paste")
    DELETE_CATEGORY = QT_TRANSLATE_NOOP("MenuActions", "Delete category")
    DELETE_SELECTED = QT_TRANSLATE_NOOP("MenuActions", "Delete selected")
    SELECT_ALL_CATEGORIES = QT_TRANSLATE_NOOP("MenuActions", "Select all")
    CLEAR_SELECTION = QT_TRANSLATE_NOOP("MenuActions", "Clear selection")
    # Undo/Redo
    UNDO = QT_TRANSLATE_NOOP("MenuActions", "&Undo")
    REDO = QT_TRANSLATE_NOOP("MenuActions", "&Redo")
    # Links context menu
    OPEN = QT_TRANSLATE_NOOP("MenuActions", "Open")
    LAUNCH_MARKED = QT_TRANSLATE_NOOP("MenuActions", "Launch marked")
    EDIT = QT_TRANSLATE_NOOP("MenuActions", "Edit")
    DELETE = QT_TRANSLATE_NOOP("MenuActions", "Delete")
    COPY = QT_TRANSLATE_NOOP("MenuActions", "Copy")
    PASTE = QT_TRANSLATE_NOOP("MenuActions", "Paste")
    CUT = QT_TRANSLATE_NOOP("MenuActions", "Cut")
    ADD_LINK = QT_TRANSLATE_NOOP("MenuActions", "Add link")
    SELECT_ALL = QT_TRANSLATE_NOOP("MenuActions", "Select all")
    CLEAR_SELECTION = QT_TRANSLATE_NOOP("MenuActions", "Clear selection")
    EDIT_NOTE = QT_TRANSLATE_NOOP("MenuActions", "Edit note")
    ADD_NOTE = QT_TRANSLATE_NOOP("MenuActions", "Add note")
    # Favorites toggle
    ADD_TO_FAVORITES = QT_TRANSLATE_NOOP("MenuActions", "Add to favorites")
    REMOVE_FROM_FAVORITES = QT_TRANSLATE_NOOP("MenuActions", "Remove from favorites")
    # Share submenu and items
    SHARE = QT_TRANSLATE_NOOP("MenuActions", "Share")
    EMAIL = QT_TRANSLATE_NOOP("MenuActions", "Email")
    SHARE_TELEGRAM = QT_TRANSLATE_NOOP("MenuActions", "Telegram")
    SHARE_WHATSAPP = QT_TRANSLATE_NOOP("MenuActions", "WhatsApp")
    SHARE_VIBER = QT_TRANSLATE_NOOP("MenuActions", "Viber")
    SHARE_X = QT_TRANSLATE_NOOP("MenuActions", "X (Twitter)")
    SHARE_FACEBOOK = QT_TRANSLATE_NOOP("MenuActions", "Facebook")
    SHARE_LINKEDIN = QT_TRANSLATE_NOOP("MenuActions", "LinkedIn")
    SHARE_PINTEREST = QT_TRANSLATE_NOOP("MenuActions", "Pinterest")
    EMAIL_VIA_GMAIL = QT_TRANSLATE_NOOP("MenuActions", "Via Gmail")
    EMAIL_VIA_CLIENT = QT_TRANSLATE_NOOP("MenuActions", "Via default client (mailto)")
    EMAIL_COPY_AS_MESSAGE = QT_TRANSLATE_NOOP("MenuActions", "Copy as email message")
    SHARE_CATEGORY = QT_TRANSLATE_NOOP("MenuActions", "Share category")
    SHARE_SECTION = QT_TRANSLATE_NOOP("MenuActions", "Share section")
    IMPORT_CATEGORY = QT_TRANSLATE_NOOP("MenuActions", "Import category")
    IMPORT_SECTION = QT_TRANSLATE_NOOP("MenuActions", "Import section")

# NOTE: The block below is never executed; it only exists so that pylupdate6 can
# discover all menu action texts even though we resolve them dynamically at runtime.
if False:  # pragma: no cover
    QCoreApplication.translate("MenuActions", "Add section")
    QCoreApplication.translate("MenuActions", "Add category")
    QCoreApplication.translate("MenuActions", "Add link")
    QCoreApplication.translate("MenuActions", "Clear favorites")
    QCoreApplication.translate("MenuActions", "Exit")
    QCoreApplication.translate("MenuActions", "Settings")
    QCoreApplication.translate("MenuActions", "Export Database")
    QCoreApplication.translate("MenuActions", "Restore Database")
    QCoreApplication.translate("MenuActions", "Import Database")
    QCoreApplication.translate("MenuActions", "Import Bookmarks")
    QCoreApplication.translate("MenuActions", "Export icons")
    QCoreApplication.translate("MenuActions", "Import icons")
    QCoreApplication.translate("MenuActions", "Search files")
    QCoreApplication.translate("MenuActions", "About")
    QCoreApplication.translate("MenuActions", "Edit section")
    QCoreApplication.translate("MenuActions", "Edit category")
    QCoreApplication.translate("MenuActions", "Paste")
    QCoreApplication.translate("MenuActions", "Paste section")
    QCoreApplication.translate("MenuActions", "Delete section")
    QCoreApplication.translate("MenuActions", "Copy category")
    QCoreApplication.translate("MenuActions", "Copy section")
    QCoreApplication.translate("MenuActions", "Cut")
    QCoreApplication.translate("MenuActions", "Delete category")
    QCoreApplication.translate("MenuActions", "Delete selected")
    QCoreApplication.translate("MenuActions", "Select all")
    QCoreApplication.translate("MenuActions", "Clear selection")
    QCoreApplication.translate("MenuActions", "&Undo")
    QCoreApplication.translate("MenuActions", "&Redo")
    QCoreApplication.translate("MenuActions", "Open")
    QCoreApplication.translate("MenuActions", "Edit")
    QCoreApplication.translate("MenuActions", "Delete")
    QCoreApplication.translate("MenuActions", "Copy")
    QCoreApplication.translate("MenuActions", "Edit note")
    QCoreApplication.translate("MenuActions", "Add note")
    QCoreApplication.translate("MenuActions", "Add to favorites")
    QCoreApplication.translate("MenuActions", "Remove from favorites")
    QCoreApplication.translate("MenuActions", "Share")
    QCoreApplication.translate("MenuActions", "Email")
    QCoreApplication.translate("MenuActions", "Telegram")
    QCoreApplication.translate("MenuActions", "WhatsApp")
    QCoreApplication.translate("MenuActions", "Viber")
    QCoreApplication.translate("MenuActions", "X (Twitter)")
    QCoreApplication.translate("MenuActions", "Facebook")
    QCoreApplication.translate("MenuActions", "LinkedIn")
    QCoreApplication.translate("MenuActions", "Pinterest")
    QCoreApplication.translate("MenuActions", "Via Gmail")
    QCoreApplication.translate("MenuActions", "Via default client (mailto)")
    QCoreApplication.translate("MenuActions", "Copy as email message")
    QCoreApplication.translate("MenuActions", "Share category")
    QCoreApplication.translate("MenuActions", "Share section")
    QCoreApplication.translate("MenuActions", "Import category")
    QCoreApplication.translate("MenuActions", "Import section")
    QCoreApplication.translate("MenuActions", "Error: %1")


class StructureItemType:
    """Item types in the structure tree."""

    SECTION = "section"
    CATEGORY = "category"
