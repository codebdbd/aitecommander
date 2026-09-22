"""Shared descriptors and display labels for supported link types."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QCoreApplication


@dataclass(frozen=True)
class LinkTypeDescriptor:
    key: str
    label_source: str
    default_icon: str
    browse_enabled: bool = False
    args_enabled: bool = False
    profile_enabled: bool = False


LINK_TYPE_DESCRIPTORS: tuple[LinkTypeDescriptor, ...] = (
    LinkTypeDescriptor(
        key="web",
        label_source="Web link",
        default_icon="web_icon.png",
        args_enabled=True,
        profile_enabled=True,
    ),
    LinkTypeDescriptor(
        key="file",
        label_source="File",
        default_icon="documents_icon.png",
        browse_enabled=True,
    ),
    LinkTypeDescriptor(
        key="folder",
        label_source="Folder",
        default_icon="folder_icon.png",
        browse_enabled=True,
    ),
    LinkTypeDescriptor(
        key="program",
        label_source="Application",
        default_icon="program_icon.png",
        browse_enabled=True,
        args_enabled=True,
    ),
    LinkTypeDescriptor(
        key="script",
        label_source="Script",
        default_icon="script_icon.png",
        browse_enabled=True,
        args_enabled=True,
    ),
    LinkTypeDescriptor(
        key="note",
        label_source="Note",
        default_icon="documents_icon.png",
    ),
)

LINK_TYPE_LABELS: dict[str, str] = {
    descriptor.key: descriptor.label_source for descriptor in LINK_TYPE_DESCRIPTORS
}
LINK_TYPE_DEFAULT_ICONS: dict[str, str] = {
    descriptor.key: descriptor.default_icon for descriptor in LINK_TYPE_DESCRIPTORS
}
_LINK_TYPE_BY_KEY = {descriptor.key: descriptor for descriptor in LINK_TYPE_DESCRIPTORS}


def normalize_link_type_key(link_type: str | None) -> str:
    """Return a supported stored link type key."""
    normalized = str(link_type or "web").strip().lower()
    return normalized if normalized in _LINK_TYPE_BY_KEY else "web"


def link_type_descriptor(link_type: str | None) -> LinkTypeDescriptor:
    """Return the descriptor for a stored link type."""
    return _LINK_TYPE_BY_KEY[normalize_link_type_key(link_type)]


def link_type_choices() -> list[list[str]]:
    """Return dialog/table link type choices as `[key, label_source]` rows."""
    return [[descriptor.key, descriptor.label_source] for descriptor in LINK_TYPE_DESCRIPTORS]


def link_type_label_source(link_type: str | None) -> str:
    """Return the untranslated source label for a stored link type."""
    return link_type_descriptor(link_type).label_source


def translate_link_type_label(link_type: str | None) -> str:
    """Return the localized label used by both the link dialog and table."""
    return QCoreApplication.translate("LinkDialogUI", link_type_label_source(link_type))


def link_type_address_tooltip(link: dict) -> str:
    """Return the resource address/details shown by the Type column tooltip."""
    descriptor = link_type_descriptor(str(link.get("type") or "web"))
    if descriptor.key == "note":
        return str(link.get("notes") or link.get("url") or link.get("path") or "").strip()[:200]
    value = str(link.get("url") or link.get("path") or "").strip()
    if value:
        return value
    return str(link.get("notes") or "").strip()[:200]
