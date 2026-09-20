"""Shared display labels for supported link types."""

from PyQt6.QtCore import QCoreApplication

LINK_TYPE_LABELS: dict[str, str] = {
    "web": "Web link",
    "file": "File",
    "program": "Application",
    "script": "Script",
    "folder": "Folder",
}


def link_type_label_source(link_type: str | None) -> str:
    """Return the untranslated source label for a stored link type."""
    normalized = str(link_type or "web").strip().lower()
    return LINK_TYPE_LABELS.get(normalized, LINK_TYPE_LABELS["web"])


def translate_link_type_label(link_type: str | None) -> str:
    """Return the localized label used by both the link dialog and table."""
    return QCoreApplication.translate("LinkDialogUI", link_type_label_source(link_type))
