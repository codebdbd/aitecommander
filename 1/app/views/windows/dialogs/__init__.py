"""Application dialogs package.

Collects dialog classes grouped by module:
- ``link_dialog/`` — link-related dialogs split into components
- ``base_dialog.py`` — base dialog implementation
- ``entity_dialogs.py`` — entity dialogs (section, category)
- ``system_dialogs.py`` — system dialogs
"""

from importlib import import_module
from typing import Any

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


def __getattr__(name: str) -> Any:
    module_map = {
        "BaseDialog": ".base_dialog",
        "BrowserProfileDialog": ".browser_profile_dialog",
        "LinkDialog": ".link_dialog.link_dialog",
        "ImportBrowserDialog": ".import_browser_dialog",
        "RestoreDbDialog": ".restore_db_dialog",
        "FileSearchDialog": ".file_search_dialog.file_search_dialog",
        "BaseEntityDialog": ".entity_dialogs",
        "SectionDialog": ".entity_dialogs",
        "CategoryDialog": ".entity_dialogs",
        "NoteDialog": ".entity_dialogs",
        "SettingsDialog": ".entity_dialogs",
        "ChromeProfileDialog": ".entity_dialogs",
    }

    target = module_map.get(name)
    if not target:
        raise AttributeError(name)

    module = import_module(f"{__name__}{target}")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
