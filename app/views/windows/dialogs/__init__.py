"""Application dialogs package.

Collects dialog classes grouped by module:
- ``link_dialog/`` — link-related dialogs split into components
- ``base_dialog.py`` — base dialog implementation
- ``entity_dialogs.py`` — entity dialogs (section, category)
- ``system_dialogs.py`` — system dialogs
"""

# Base dialogs
from .base_dialog import BaseDialog
from .browser_profile_dialog import BrowserProfileDialog

# Entity dialogs
from .entity_dialogs import (
    BaseEntityDialog,
    CategoryDialog,
    ChromeProfileDialog,
    NoteDialog,
    SectionDialog,
    SettingsDialog,
)
from .file_search_dialog.file_search_dialog import FileSearchDialog

# System dialogs
from .import_browser_dialog import ImportBrowserDialog

# Link dialog (modular)
from .link_dialog.link_dialog import LinkDialog
from .restore_db_dialog import RestoreDbDialog

__all__ = [
    "BaseDialog",
    "BaseEntityDialog",
    "SectionDialog",
    "CategoryDialog",
    "NoteDialog",
    "SettingsDialog",
    "ChromeProfileDialog",
    "BrowserProfileDialog",
    "LinkDialog",
    "ImportBrowserDialog",
    "RestoreDbDialog",
    "FileSearchDialog",
]
