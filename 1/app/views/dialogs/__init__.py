"""
Модуль диалогов приложения.

Содержит все диалоги, организованные по модульному принципу:
- link_dialog/ - диалог ссылок (разделен на компоненты)
- base_dialog.py - базовый диалог
- entity_dialogs.py - диалоги сущностей (Section, Category)
- system_dialogs.py - системные диалоги
"""

# Базовые диалоги
from .base_dialog import BaseDialog
from .browser_profile_dialog import BrowserProfileDialog

# Диалоги сущностей
from .entity_dialogs import (
    BaseEntityDialog,
    CategoryDialog,
    ChromeProfileDialog,
    NoteDialog,
    SectionDialog,
    SettingsDialog,
)
from .file_search_dialog.file_search_dialog import FileSearchDialog

# Системные диалоги
from .import_browser_dialog import ImportBrowserDialog

# Диалог ссылок (модульный)
from .link_dialog.link_dialog import LinkDialog
from .restore_db_dialog import RestoreDbDialog

__all__ = [
    'BaseDialog',
    'BaseEntityDialog',
    'SectionDialog',
    'CategoryDialog',
    'NoteDialog',
    'SettingsDialog',
    'ChromeProfileDialog',
    'BrowserProfileDialog',
    'LinkDialog',
    'ImportBrowserDialog',
    'RestoreDbDialog',
    'FileSearchDialog',
]
