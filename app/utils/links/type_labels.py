"""Shared descriptors and display labels for supported link types."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

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
        label_source="Web",
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
    """Return structured launcher context tooltip for the Type column."""
    raw_type = str(link.get("type") or "web")
    descriptor = link_type_descriptor(raw_type)
    type_title = translate_link_type_label(descriptor.key)
    url_or_path = str(link.get("url", "") or link.get("path", "")).strip()

    rows: list[str] = [
        f"<tr><td colspan='2' style='font-weight: bold; font-size: 12px; padding-bottom: 4px;'>{html.escape(type_title)}</td></tr>"
    ]

    lbl_action = QCoreApplication.translate("TypeLabels", "Action:")
    lbl_target = QCoreApplication.translate("TypeLabels", "Target:")

    if descriptor.key == "web":
        domain = ""
        if url_or_path:
            try:
                domain = urlsplit(url_or_path).netloc
            except Exception:
                pass
        if domain:
            rows.append(
                f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_target}</td>"
                f"<td>{html.escape(domain)}</td></tr>"
            )
        browser_prof = str(link.get("browser_key") or "").strip()
        if browser_prof:
            lbl_prof = QCoreApplication.translate("TypeLabels", "Profile:")
            rows.append(
                f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_prof}</td>"
                f"<td>{html.escape(browser_prof)}</td></tr>"
            )
        act_text = QCoreApplication.translate("TypeLabels", "Open web page in browser")
        rows.append(
            f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_action}</td>"
            f"<td>{act_text}</td></tr>"
        )
    elif descriptor.key == "file":
        ext = Path(url_or_path).suffix.lower() if url_or_path else ""
        if ext:
            lbl_format = QCoreApplication.translate("TypeLabels", "Format:")
            rows.append(
                f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_format}</td>"
                f"<td>{html.escape(ext)}</td></tr>"
            )
        act_text = QCoreApplication.translate("TypeLabels", "Open in default application")
        rows.append(
            f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_action}</td>"
            f"<td>{act_text}</td></tr>"
        )
    elif descriptor.key == "folder":
        act_text = QCoreApplication.translate("TypeLabels", "Open in Windows Explorer")
        rows.append(
            f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_action}</td>"
            f"<td>{act_text}</td></tr>"
        )
    elif descriptor.key == "program":
        exe_name = Path(url_or_path).name if url_or_path else ""
        if exe_name:
            rows.append(
                f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_target}</td>"
                f"<td>{html.escape(exe_name)}</td></tr>"
            )
        act_text = QCoreApplication.translate("TypeLabels", "Launch executable application")
        rows.append(
            f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_action}</td>"
            f"<td>{act_text}</td></tr>"
        )
    elif descriptor.key == "script":
        act_text = QCoreApplication.translate("TypeLabels", "Execute script file")
        rows.append(
            f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_action}</td>"
            f"<td>{act_text}</td></tr>"
        )

    table_content = "".join(rows)
    return f"<table style='min-width: 240px; max-width: 480px; margin: 2px;'>{table_content}</table>"
